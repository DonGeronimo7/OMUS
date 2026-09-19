"""State-driven setup TUI controller.

The controller contains session/navigation state only. Hardware discovery and
capability logic remain in their own services; curses is only a presentation
adapter. This makes Back/Cancel/device-switch/review-edit behavior deterministic
and unit-testable.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass, field
from enum import Enum, auto
import io
from typing import Any, Callable

from .calibrated_profiles import find_calibrated_profile
from .guided_discovery import GuidedDiscoveryOutcome, load_known_device_state
from .hardware import HardwareError, get_backend
from .hardware.capabilities import LightingMode, LightingState
from .lighting import validate_lighting_state
from .discovery_models import DiscoveryProgress
from .setup_flow import SetupChoices, discover_choices, restore_dpi
from .performance import timed
from .lab_orchestrator import initial_lab_hypotheses, plan_next_experiment


def _format_timing_ns(value: int | None) -> str:
    if value is None:
        return "unknown"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} ms"
    if value >= 1_000:
        return f"{value / 1_000:.1f} µs"
    return f"{value} ns"


class SetupSection(Enum):
    DEVICE = "Device"
    HARDWARE = "Hardware Discovery"
    LAB = "Discovery Lab"
    DPI = "DPI"
    POLLING = "Polling"
    BUTTONS = "Buttons"
    LIGHTING = "Lighting"
    SERVICE = "Service"
    UPDATE = "Updates"
    TOOLS = "Tools / Advanced"
    ABOUT = "About"
    REVIEW = "Review / Save"


SECTIONS = tuple(SetupSection)


class ActionKind(Enum):
    NONE = auto()
    HELP = auto()
    CANCEL = auto()
    AUTOMATIC_DISCOVERY = auto()
    RETRY_DISCOVERY = auto()
    GUIDED_DISCOVERY = auto()
    RUN_DISCOVERY_LAB = auto()
    OPEN_ADVANCED_TOOLS = auto()
    IMPORT_VENDOR_CAPTURE = auto()
    MEASURE_POLLING = auto()
    EDIT_DPI = auto()
    CAPTURE_BUTTONS = auto()
    EDIT_LIGHTING = auto()
    CHECK_UPDATE = auto()
    START_UPDATE = auto()
    OPEN_PRODUCT_TOOL = auto()
    SERVICE_ACTION = auto()
    SAVE = auto()


@dataclass(frozen=True)
class ControllerAction:
    kind: ActionKind = ActionKind.NONE
    payload: Any = None


@dataclass(frozen=True)
class DisplayRow:
    text: str
    cursor_index: int | None = None
    dim: bool = False
    role: str = "normal"


@dataclass(frozen=True)
class SetupTuiResult:
    finished: bool
    selected: Any
    backend: Any
    choices: SetupChoices


@dataclass(frozen=True)
class ObservedHardwareState:
    """Read-only exact-device evidence, separate from user preferences."""

    calibrated_dpi_cycle: tuple[int, ...] = ()
    calibration_confidence: str | None = None
    measured_polling_rate: int | None = None
    measured_polling_confidence: str | None = None
    transition_source_kinds: tuple[str, ...] = ()
    profile_path: Any | None = None

    @property
    def has_physical_calibration(self) -> bool:
        return bool(self.calibrated_dpi_cycle)

    @property
    def has_runtime_source(self) -> bool:
        return bool(self.transition_source_kinds)


@dataclass
class NavigationState:
    """Explicit logical navigation with review-edit return semantics."""
    current: SetupSection = SetupSection.DEVICE
    history: list[SetupSection] = field(default_factory=list)
    return_to: SetupSection | None = None

    def go(self, target: SetupSection, *, remember: bool = True) -> None:
        if target is self.current:
            return
        if remember:
            self.history.append(self.current)
        self.current = target

    def sequential(self, direction: int) -> None:
        index = SECTIONS.index(self.current)
        target_index = max(0, min(len(SECTIONS) - 1, index + direction))
        target = SECTIONS[target_index]
        if self.return_to is SetupSection.REVIEW and self.current in {
            SetupSection.DPI,
            SetupSection.POLLING,
            SetupSection.BUTTONS,
            SetupSection.LIGHTING,
        } and direction > 0:
            target = SetupSection.REVIEW
            self.return_to = None
        self.go(target)

    def back(self) -> None:
        if self.return_to is SetupSection.REVIEW and self.current in {
            SetupSection.DPI,
            SetupSection.POLLING,
            SetupSection.BUTTONS,
            SetupSection.LIGHTING,
        }:
            self.current = SetupSection.REVIEW
            self.return_to = None
            return
        if self.history:
            self.current = self.history.pop()
            return
        index = SECTIONS.index(self.current)
        if index > 0:
            previous = SECTIONS[index - 1]
            # The Lab is an instrument launched from Hardware Discovery, not a
            # required configuration step between Hardware and DPI.
            self.current = SetupSection.HARDWARE if previous is SetupSection.LAB else previous

    def edit_from_review(self, target: SetupSection) -> None:
        self.return_to = SetupSection.REVIEW
        self.go(target)

    def reset_for_device(self) -> None:
        self.current = SetupSection.DEVICE
        self.history.clear()
        self.return_to = None


class SetupController:
    """Pure setup session/navigation model with injected hardware factories."""

    def __init__(
        self,
        devices: list[Any] | tuple[Any, ...],
        existing_config: dict[str, object],
        *,
        choices_factory: Callable[[dict[str, object]], SetupChoices],
        backend_factory: Callable[[Any], Any] = get_backend,
        known_device_loader: Callable[[Any], Any | None] = load_known_device_state,
        initialize_backend: bool = True,
        selected_index: int | None = None,
    ) -> None:
        self.devices = tuple(devices)
        self.existing_config = existing_config
        self._choices_factory = choices_factory
        self._backend_factory = backend_factory
        self._known_device_loader = known_device_loader

        self.nav = NavigationState()
        self.row_cursor = 0
        self.discovery_skipped = False
        self.discovery_complete = False
        self.discovery_result: Any | None = None
        self.discovery_error: str | None = None
        self.discovery_progress: list[DiscoveryProgress] = []
        self.guided_outcome: GuidedDiscoveryOutcome | None = None
        self.deep_learning_outcome: Any | None = None
        self.research_plan: Any | None = None
        self.research_probe_outcome: Any | None = None
        self.discovery_engine: Any | None = None
        self.lab_experiment: Any | None = None
        self.vendor_capture_import: Any | None = None
        self.polling_measurement: Any | None = None
        self.battery_state: Any | None = None
        self.battery_error: str | None = None
        self.update_status: Any | None = None
        self.observed_hardware = ObservedHardwareState()
        self.status = "Choose a mouse. Automatic hardware discovery runs before configuration."
        self.notice = ""

        self.choices = self._choices_factory(self.existing_config)
        if not self.devices:
            self.selected_index = 0
            self.device_cursor = 0
            self.selected = None
            self.backend = None
            self.status = (
                "No mouse detected. Check input permissions or reconnect a device, then reopen setup."
            )
            return

        self.selected_index = (
            self._configured_device_index() if selected_index is None else selected_index
        )
        if not 0 <= self.selected_index < len(self.devices):
            raise ValueError("selected device index is out of range")
        self.device_cursor = self.selected_index
        self.selected = self.devices[self.selected_index]
        self.backend: Any = None
        if initialize_backend:
            self._bind_device(self.selected_index, restore_old=False, reset_choices=True)
        else:
            self.status = (
                f"Selected {self.selected.name}; preparing live hardware capabilities."
            )

    @property
    def backend_ready(self) -> bool:
        return self.backend is not None

    def initialized_copy(self, selected_index: int) -> "SetupController":
        """Build live hardware state without mutating the displayed controller."""
        from .foreground_session import complete_pending_suspension

        complete_pending_suspension()
        return type(self)(
            self.devices,
            self.existing_config,
            choices_factory=self._choices_factory,
            backend_factory=self._backend_factory,
            known_device_loader=self._known_device_loader,
            selected_index=selected_index,
        )

    @property
    def section(self) -> SetupSection:
        return self.nav.current

    # Compatibility for existing controller-level tests and external helpers.
    @property
    def section_index(self) -> int:
        return SECTIONS.index(self.nav.current)

    @section_index.setter
    def section_index(self, value: int) -> None:
        self.nav.current = SECTIONS[int(value)]
        self.nav.return_to = None
        self.nav.history.clear()
        self.row_cursor = 0

    def _configured_device_index(self) -> int:
        configured = self.existing_config.get("device", {})
        if not isinstance(configured, dict):
            return 0
        vendor = configured.get("vendor")
        product = configured.get("product")
        phys = configured.get("phys")
        candidates = [
            index
            for index, device in enumerate(self.devices)
            if device.vendor == vendor and device.product == product
        ]
        if phys:
            exact = [index for index in candidates if self.devices[index].phys == phys]
            if len(exact) == 1:
                return exact[0]
        return candidates[0] if len(candidates) == 1 else 0

    def _discover_into_choices(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            discover_choices(self.backend, self.selected, self.choices)
        lines = [line.strip() for line in output.getvalue().splitlines() if line.strip()]
        self.notice = lines[-1] if lines else ""
        self._refresh_battery_snapshot()

    def _refresh_battery_snapshot(self) -> None:
        """Read battery once during initialization, never in the redraw path."""

        self.battery_state = None
        self.battery_error = None
        try:
            if not self.backend.supports_battery(self.selected):
                return
            self.battery_state = self.backend.get_battery_state(self.selected)
        except (HardwareError, AttributeError, OSError, TypeError, ValueError) as exc:
            self.battery_error = str(exc)

    def _configured_identity_matches(self, device: Any) -> bool:
        configured = self.existing_config.get("device", {})
        if not isinstance(configured, dict) or not configured:
            return True
        if configured.get("vendor") != device.vendor or configured.get("product") != device.product:
            return False
        configured_phys = configured.get("phys")
        return not (configured_phys and device.phys and configured_phys != device.phys)

    def _has_configured_identity(self) -> bool:
        configured = self.existing_config.get("device", {})
        return bool(
            isinstance(configured, dict)
            and isinstance(configured.get("vendor"), int)
            and isinstance(configured.get("product"), int)
        )

    def _bind_device(
        self,
        index: int,
        *,
        restore_old: bool = True,
        reset_choices: bool = True,
    ) -> None:
        """Bind one physical device after rolling back/closing the prior one."""
        if restore_old and self.backend is not None:
            try:
                restore_dpi(self.backend, self.selected, self.choices.original_dpi)
            except Exception:
                # A disconnected old mouse cannot be restored; do not carry any
                # of its discovery/runtime state into the replacement.
                pass
            try:
                self.backend.close()
            except Exception:
                pass

        self.selected_index = index
        self.device_cursor = index
        self.selected = self.devices[index]
        if reset_choices:
            self.choices = self._choices_factory(self.existing_config)
        else:
            self.choices.reset_device_state()

        self.backend = self._backend_factory(self.selected)
        self._discover_into_choices()
        self.discovery_skipped = False
        self.discovery_complete = False
        self.discovery_result = None
        self.discovery_error = None
        self.discovery_progress.clear()
        self.guided_outcome = None
        self.deep_learning_outcome = None
        self.research_plan = None
        self.research_probe_outcome = None
        self.discovery_engine = None
        self.lab_experiment = None
        self.vendor_capture_import = None
        self.polling_measurement = None
        self.observed_hardware = ObservedHardwareState()
        self.status = f"Selected {self.selected.name}; ready for Automatic Discovery."

        if self._has_configured_identity() and self._configured_identity_matches(self.selected):
            try:
                known = self._known_device_loader(self.selected)
            except Exception:
                # Cached state is optional. Any topology, schema, corruption, or
                # binding failure falls back to the normal explicit discovery
                # path without trusting partial evidence.
                known = None
            if known is not None:
                self._apply_discovery_outcome(known, rebind_backend=False)

        # Never silently apply a different mouse's persisted hardware rate. The
        # stage list/remaps remain reusable; live hardware preferences require a
        # deliberate selection for the newly selected physical device.
        if not self._configured_identity_matches(self.selected):
            self.choices.polling_rate = self.choices.current_polling_rate
            self.choices.polling_changed = self.choices.current_polling_rate is not None
            if self.choices.current_dpi is not None:
                self.choices.active_dpi = self.choices.current_dpi

    def restore_temporary_state(self) -> None:
        try:
            restore_dpi(self.backend, self.selected, self.choices.original_dpi)
        except Exception:
            pass

    def refresh_discovery_backend(self, *, status: str | None = None) -> None:
        """Rebuild the selected device backend after temporary input ownership."""
        try:
            if self.backend is not None:
                self.backend.close()
        except Exception:
            pass
        self.backend = self._backend_factory(self.selected)
        self._discover_into_choices()
        if status is not None:
            self.status = status

    @property
    def protocol_adapter_name(self) -> str | None:
        if self.discovery_result is not None and getattr(self.discovery_result, "protocol", None):
            protocol = self.discovery_result.protocol
            version = f" {protocol.version}" if getattr(protocol, "version", None) else ""
            return f"{protocol.name}{version}".strip()
        return getattr(self.backend, "protocol_adapter_name", None)

    @property
    def has_proven_learned_adapter(self) -> bool:
        return bool(getattr(self.backend, "has_proven_learned_adapter", False))

    def _supports_dpi_events(self) -> bool:
        try:
            return bool(self.backend.supports_dpi_events(self.selected))
        except (HardwareError, AttributeError, OSError):
            return False

    def record_discovery_progress(self, event: DiscoveryProgress) -> None:
        if not isinstance(event, DiscoveryProgress):
            return
        self.discovery_progress.append(event)
        self.status = event.message

    def _refresh_observed_profile(self) -> None:
        """Load validated read-only evidence for the discovered physical device."""
        self.observed_hardware = ObservedHardwareState()
        device = getattr(self.discovery_result, "device", None)
        if device is None:
            return
        found = find_calibrated_profile(device)
        if found is None:
            return
        path, profile = found
        cycle = profile.get("dpi_cycle", {})
        states = cycle.get("states", ()) if isinstance(cycle, dict) else ()
        measured_cycle = tuple(
            int(round(float(state["measured_cpi"])))
            for state in states[:-1]
            if isinstance(state, dict) and state.get("measured_cpi") is not None
        )
        polling_values = [
            int(state["polling_hz"])
            for state in states
            if isinstance(state, dict) and state.get("polling_hz") is not None
        ]
        state_confidences = {
            str(state.get("confidence"))
            for state in states
            if isinstance(state, dict) and state.get("confidence")
        }
        sources = profile.get("transition_sources", ())
        self.observed_hardware = ObservedHardwareState(
            calibrated_dpi_cycle=measured_cycle,
            calibration_confidence=str(cycle.get("confidence", "unknown")),
            measured_polling_rate=(
                max(set(polling_values), key=polling_values.count) if polling_values else None
            ),
            measured_polling_confidence=(
                next(iter(state_confidences)) if len(state_confidences) == 1 else "mixed"
            ) if polling_values else None,
            transition_source_kinds=tuple(
                str(source["kind"])
                for source in sources
                if isinstance(source, dict) and source.get("kind")
            ),
            profile_path=path,
        )

    def _apply_discovery_outcome(self, outcome: Any, *, rebind_backend: bool) -> None:
        self.discovery_result = outcome.result if hasattr(outcome, "result") else outcome
        self.discovery_engine = getattr(outcome, "engine", None)
        self.research_plan = getattr(outcome, "research_plan", None)
        self.discovery_complete = True
        self.discovery_error = None
        cached = bool(getattr(outcome, "cached_profile_used", False))
        # A discovery pass may have exposed an already-PROVEN exact-model store.
        # Rebind through the production registry so setup and runtime share the
        # exact same backend policy.
        if rebind_backend:
            try:
                self.backend.close()
            except Exception:
                pass
            self.backend = self._backend_factory(self.selected)
            self._discover_into_choices()
        self._refresh_observed_profile()
        if cached:
            self.discovery_progress.clear()
            self.status = "Known device ready; learned discovery evidence was reused."
        else:
            self.status = (
                "Automatic Discovery complete. No verified host-accessible DPI/polling write path; "
                "continue with DPI-stage observation and button remapping."
                if self.no_write_path
                else "Automatic Discovery complete. Review capabilities before configuration."
            )

    def apply_automatic_discovery(self, outcome: Any) -> None:
        """Consume fresh DiscoveryEngine output and rebind the production backend."""
        self._apply_discovery_outcome(outcome, rebind_backend=True)

    def apply_discovery_error(self, message: str) -> None:
        self.discovery_error = message
        self.discovery_complete = False
        self.discovery_progress.clear()
        self.status = message

    def apply_lab_experiment(self, experiment: Any) -> None:
        """Retain one canonical Lab result for progressive TUI inspection."""

        self.lab_experiment = experiment
        analysis = getattr(experiment, "analysis", None)
        correlated = 0
        if analysis is not None:
            correlated = sum(
                1 for item in analysis.ranked_fields
                if any(signal.value == "action_correlated" for signal in item.signals)
            )
        self.status = (
            f"Differential analysis retained {correlated} action-correlated field(s); "
            "write authority remains unchanged."
        )

    def apply_vendor_capture_import(self, imported: Any) -> None:
        """Retain an offline import summary without changing runtime capabilities."""

        self.vendor_capture_import = imported
        manifest = imported.manifest
        self.status = (
            f"Imported {manifest.accepted_records} offline evidence record(s); "
            "review state is unreviewed and write authority remains unchanged."
        )

    def cancel_vendor_capture_import(self) -> None:
        """Cancellation changes no previously staged evidence or runtime state."""

        self.status = "Vendor capture import cancelled; existing evidence is unchanged."

    @property
    def guided_discovery_available(self) -> bool:
        # Deeper learning is specifically the fallback for an unknown protocol
        # when Automatic Discovery has no executable generic write probe.
        return bool(
            self.discovery_complete
            and not self.discovery_skipped
            and self.research_plan is not None
            and getattr(self.research_plan, "deeper_learning_recommended", False)
            and not self.observed_hardware.has_runtime_source
        )

    @property
    def deep_learning_label(self) -> str:
        if (
            self.observed_hardware.has_physical_calibration
            and not self.observed_hardware.has_runtime_source
        ):
            return "Learn runtime DPI transition source"
        return "Run deeper protocol / DPI-stage learning"

    def _discovered_capability(self, name: str):
        if self.discovery_result is None:
            return None
        return getattr(self.discovery_result, "capabilities", {}).get(name)

    @staticmethod
    def _capability_values(capability: Any) -> list[int]:
        return list(getattr(capability, "values", ()) or ())

    def hardware_lines(self) -> list[str]:
        """Render factual, independent capability state without collapsing failures."""
        identity = "unknown"
        if self.selected.vendor is not None and self.selected.product is not None:
            identity = f"{self.selected.vendor:04x}:{self.selected.product:04x}"
        lines: list[str] = [
            f"• Device: {self.selected.name}  [{identity}]",
            f"• Connection: {self.selected.phys or self.selected.path or 'unknown'}",
        ]
        result = self.discovery_result
        if result is not None:
            device = result.device
            lines.append("✓ Physical mouse identified")
            lines.append(f"✓ {len(device.hidraw_nodes)} HID interface(s) correlated")
            if getattr(device, "ambiguous", False):
                lines.append("? Physical binding is ambiguous; hardware writes are disabled")
            if self.protocol_adapter_name:
                lines.append(f"✓ Protocol/backend: {self.protocol_adapter_name}")
            elif self.has_proven_learned_adapter:
                lines.append("✓ Proven exact-model learned backend")
            else:
                lines.append("• Known protocol repertoire checked")
        else:
            lines.append("• Automatic Discovery has not completed")
            if self.protocol_adapter_name:
                lines.append(f"✓ Runtime backend: {self.protocol_adapter_name}")
            if self.has_proven_learned_adapter:
                lines.append("✓ Learned exact-model support")

        if self.choices.dpi_readable or self.choices.dpi_writable:
            mode = "read/write" if self.choices.dpi_writable else "read-only"
            detail = f"✓ DPI capability: {mode}"
            if self.choices.dpi_minimum is not None and self.choices.dpi_maximum is not None:
                detail += f" — {self.choices.dpi_minimum}–{self.choices.dpi_maximum} DPI"
                if self.choices.dpi_increment:
                    detail += f", step {self.choices.dpi_increment}"
            elif self.choices.dpi_values:
                detail += " — " + "/".join(map(str, self.choices.dpi_values))
            lines.append(detail)
        else:
            lines.append(
                "— DPI write path unavailable; no verified host-accessible DPI protocol"
                if self.discovery_complete
                else "? DPI capability not yet discovered"
            )

        if self.choices.polling_readable or self.choices.polling_writable:
            mode = "read/write" if self.choices.polling_writable else "read-only"
            detail = f"✓ Polling capability: {mode}"
            if self.choices.polling_rates:
                detail += " — " + " / ".join(f"{hz} Hz" for hz in self.choices.polling_rates)
            lines.append(detail)
        else:
            lines.append(
                "— Polling write path unavailable; no verified host-accessible polling protocol"
                if self.discovery_complete
                else "? Polling capability not yet discovered"
            )

        if self.research_plan is not None:
            lines.append(f"• DPI research state: {self.research_plan.dpi.status.value}")
            lines.append(f"• Polling research state: {self.research_plan.polling.status.value}")
            if self.research_plan.reversible_probe_available:
                lines.append("! A bounded reversible learned write probe is available before deeper learning")
            elif self.research_plan.deeper_learning_recommended:
                if self.observed_hardware.has_physical_calibration:
                    lines.append("✓ Physical DPI cycle already calibrated")
                    if self.observed_hardware.has_runtime_source:
                        lines.append("✓ Runtime DPI transition source learned")
                    else:
                        lines.append("? Runtime DPI transition source unresolved")
                        lines.append("→ Learn runtime transition source (ruler calibration will be reused)")
                else:
                    lines.append("✓ Deeper protocol learning is available for physical DPI-stage/event adaptation")

        if self.no_write_path:
            lines.append("✓ Discovery complete: no verified host-accessible DPI/polling write path")
            lines.append("✓ Button remapping remains available through evdev")

        if self._supports_dpi_events():
            lines.append("✓ Physical DPI events / stage notifications available")
        if self.battery_state is not None:
            battery = self.battery_state
            parts = []
            if getattr(battery, "percentage", None) is not None:
                parts.append(f"{battery.percentage}%")
            if getattr(battery, "voltage_mv", None) is not None:
                parts.append(f"{battery.voltage_mv} mV")
            if getattr(battery, "status", None):
                parts.append(str(battery.status).replace("_", " "))
            lines.append("✓ Battery / power: " + (", ".join(parts) or "state unknown"))
        elif self.battery_error:
            lines.append("? Battery / power: temporarily unavailable")
        else:
            lines.append("— Battery / power: unsupported or not reported")
        if self.guided_outcome and self.guided_outcome.dpi_action_identified:
            lines.append("✓ DPI button behavior identified")
            if not self.choices.dpi_writable:
                lines.append("? DPI write command not yet proven; hardware remains read-only")
        if self.guided_outcome and self.guided_outcome.learning_skipped_reason:
            lines.append(self.guided_outcome.learning_skipped_reason)
        if self.discovery_error:
            lines.append(f"? Discovery issue: {self.discovery_error}")
        return lines

    @property
    def no_write_path(self) -> bool:
        """True after discovery completes without DPI or polling write authority."""
        return (
            self.discovery_complete
            and not self.choices.dpi_writable
            and not self.choices.polling_writable
        )

    def _next_configuration_section(self, section: SetupSection | None = None) -> SetupSection:
        """Skip configuration pages that cannot change the selected hardware."""
        section = self.section if section is None else section
        if section is SetupSection.HARDWARE:
            if self.choices.dpi_writable:
                return SetupSection.DPI
            if self.choices.polling_writable:
                return SetupSection.POLLING
            return SetupSection.BUTTONS
        if section is SetupSection.LAB:
            return self._next_configuration_section(SetupSection.HARDWARE)
        if section is SetupSection.DPI:
            return SetupSection.POLLING if self.choices.polling_writable else SetupSection.BUTTONS
        if section is SetupSection.POLLING:
            return SetupSection.BUTTONS
        return SECTIONS[min(SECTIONS.index(section) + 1, len(SECTIONS) - 1)]

    def _previous_configuration_section(self, section: SetupSection | None = None) -> SetupSection:
        """Reverse navigation mirrors capability-driven forward navigation."""
        section = self.section if section is None else section
        if section is SetupSection.BUTTONS:
            if self.choices.polling_writable:
                return SetupSection.POLLING
            if self.choices.dpi_writable:
                return SetupSection.DPI
            return SetupSection.HARDWARE
        if section is SetupSection.LAB:
            return SetupSection.HARDWARE
        if section is SetupSection.POLLING:
            return SetupSection.DPI if self.choices.dpi_writable else SetupSection.HARDWARE
        if section is SetupSection.DPI:
            return SetupSection.HARDWARE
        return SECTIONS[max(SECTIONS.index(section) - 1, 0)]

    def row_count(self) -> int:
        if self.section is SetupSection.DEVICE:
            return len(self.devices)
        if self.section is SetupSection.HARDWARE:
            # Automatic/retry, Discovery Lab, optional deeper discovery, continue.
            return 4 if self.guided_discovery_available else 3
        if self.section is SetupSection.LAB:
            return 4
        if self.section is SetupSection.DPI:
            return len(self.choices.stages) if self.choices.dpi_writable else 1
        if self.section is SetupSection.POLLING:
            # Proven rates plus a read-only physical measurement action.
            return (len(self.choices.polling_rates) + 1) if (
                self.choices.polling_writable and self.choices.polling_rates
            ) else 1
        if self.section is SetupSection.BUTTONS:
            return 1
        if self.section is SetupSection.LIGHTING:
            return max(1, len(self.choices.lighting_zones))
        if self.section is SetupSection.SERVICE:
            return 6
        if self.section is SetupSection.UPDATE:
            return 2
        if self.section is SetupSection.TOOLS:
            return 8
        if self.section is SetupSection.ABOUT:
            return 1
        if self.section is SetupSection.REVIEW:
            return 5
        return 1

    def _clamp_cursor(self) -> None:
        self.row_cursor = max(0, min(self.row_cursor, self.row_count() - 1))

    def _go(self, target: SetupSection, *, remember: bool = True) -> None:
        self.nav.go(target, remember=remember)
        self.row_cursor = self.device_cursor if target is SetupSection.DEVICE else 0
        self._clamp_cursor()

    def handle_key(self, key: str) -> ControllerAction:
        key = key.upper()
        if self.section is SetupSection.DEVICE and not self.devices:
            if key == "HELP":
                return ControllerAction(ActionKind.HELP)
            if key == "QUIT":
                return ControllerAction(ActionKind.CANCEL)
            if key == "ENTER":
                self.status = "No mouse is available to select; reconnect one and reopen setup."
            return ControllerAction()
        if key == "FIRST":
            if self.section is SetupSection.DEVICE:
                self.device_cursor = 0
                self.row_cursor = 0
            else:
                self.row_cursor = 0
            return ControllerAction()
        if key == "LAST":
            if self.section is SetupSection.DEVICE:
                self.device_cursor = len(self.devices) - 1
                self.row_cursor = self.device_cursor
            else:
                self.row_cursor = self.row_count() - 1
            return ControllerAction()
        if key == "UP":
            if self.section is SetupSection.DEVICE:
                self.device_cursor = (self.device_cursor - 1) % len(self.devices)
                self.row_cursor = self.device_cursor
            else:
                self.row_cursor = (self.row_cursor - 1) % self.row_count()
            return ControllerAction()
        if key == "DOWN":
            if self.section is SetupSection.DEVICE:
                self.device_cursor = (self.device_cursor + 1) % len(self.devices)
                self.row_cursor = self.device_cursor
            else:
                self.row_cursor = (self.row_cursor + 1) % self.row_count()
            return ControllerAction()
        if key == "LEFT":
            if self.nav.return_to is SetupSection.REVIEW and self.section in {
                SetupSection.DPI, SetupSection.POLLING, SetupSection.BUTTONS,
                SetupSection.LIGHTING,
            }:
                self.nav.back()
            elif self.section in {SetupSection.DPI, SetupSection.POLLING, SetupSection.BUTTONS,
                                  SetupSection.LIGHTING}:
                self._go(self._previous_configuration_section(), remember=False)
            else:
                self.nav.sequential(-1)
            self.row_cursor = self.device_cursor if self.section is SetupSection.DEVICE else 0
            self._clamp_cursor()
            return ControllerAction()
        if key == "RIGHT":
            if self.nav.return_to is SetupSection.REVIEW and self.section in {
                SetupSection.DPI, SetupSection.POLLING, SetupSection.BUTTONS,
                SetupSection.LIGHTING,
            }:
                self.nav.current = SetupSection.REVIEW
                self.nav.return_to = None
            elif self.section in {SetupSection.HARDWARE, SetupSection.LAB, SetupSection.DPI, SetupSection.POLLING}:
                self._go(self._next_configuration_section())
            else:
                self.nav.sequential(1)
            self.row_cursor = self.device_cursor if self.section is SetupSection.DEVICE else 0
            self._clamp_cursor()
            return ControllerAction()
        if key in {"BACK", "ESC"}:
            self.nav.back()
            self.row_cursor = self.device_cursor if self.section is SetupSection.DEVICE else 0
            self._clamp_cursor()
            return ControllerAction()
        if key == "HELP":
            return ControllerAction(ActionKind.HELP)
        if key == "QUIT":
            return ControllerAction(ActionKind.CANCEL)
        if key != "ENTER":
            return ControllerAction()
        return self.activate()

    def activate(self) -> ControllerAction:
        if self.section is SetupSection.DEVICE:
            if not self.devices:
                self.status = "No mouse is available to select; reconnect one and reopen setup."
                return ControllerAction()
            if self.device_cursor != self.selected_index:
                self._bind_device(self.device_cursor)
            self._go(SetupSection.HARDWARE)
            return ControllerAction(
                ActionKind.NONE if self.discovery_complete else ActionKind.AUTOMATIC_DISCOVERY
            )

        if self.section is SetupSection.HARDWARE:
            # Row 0 always runs/retries the comprehensive safe pass.
            if self.row_cursor == 0:
                return ControllerAction(
                    ActionKind.RETRY_DISCOVERY if self.discovery_complete else ActionKind.AUTOMATIC_DISCOVERY
                )
            if self.row_cursor == 1:
                self._go(SetupSection.LAB)
                return ControllerAction()
            if self.guided_discovery_available:
                if self.row_cursor == 2:
                    return ControllerAction(ActionKind.GUIDED_DISCOVERY)
                self._go(self._next_configuration_section(SetupSection.HARDWARE))
                return ControllerAction()
            self._go(self._next_configuration_section(SetupSection.HARDWARE))
            return ControllerAction()

        if self.section is SetupSection.LAB:
            if self.row_cursor == 0:
                if not self.discovery_complete or self.discovery_result is None:
                    self.status = "Run Automatic Discovery before starting a Lab experiment."
                    return ControllerAction()
                return ControllerAction(ActionKind.RUN_DISCOVERY_LAB)
            if self.row_cursor == 1:
                return ControllerAction(ActionKind.OPEN_ADVANCED_TOOLS)
            if self.row_cursor == 2:
                return ControllerAction(ActionKind.IMPORT_VENDOR_CAPTURE)
            self._go(self._next_configuration_section(SetupSection.LAB))
            return ControllerAction()

        if self.section is SetupSection.DPI:
            if not self.choices.dpi_writable:
                self.status = "DPI is read-only or not yet discovered; configured stages remain unchanged."
                return ControllerAction()
            return ControllerAction(ActionKind.EDIT_DPI, self.row_cursor)

        if self.section is SetupSection.POLLING:
            if self.choices.polling_writable and self.choices.polling_rates:
                if self.row_cursor < len(self.choices.polling_rates):
                    self.choices.polling_rate = self.choices.polling_rates[self.row_cursor]
                    self.choices.polling_changed = True
                    self.status = (
                        f"Polling preference set to {self.choices.polling_rate} Hz; "
                        "final apply requires readback verification."
                    )
                    return ControllerAction()
            return ControllerAction(ActionKind.MEASURE_POLLING)

        if self.section is SetupSection.BUTTONS:
            return ControllerAction(ActionKind.CAPTURE_BUTTONS)

        if self.section is SetupSection.LIGHTING:
            if not self.choices.lighting_zones:
                self.status = "Lighting is unsupported or unknown for this mouse; core support is unaffected."
                return ControllerAction()
            return ControllerAction(ActionKind.EDIT_LIGHTING, self.row_cursor)

        if self.section is SetupSection.SERVICE:
            if self.row_cursor < 2:
                self.choices.enable_service = self.row_cursor == 0
                self.status = (
                    "Background service will be enabled."
                    if self.choices.enable_service
                    else "Background service will remain disabled."
                )
                return ControllerAction()
            return ControllerAction(ActionKind.SERVICE_ACTION,
                                    ("status", "start", "stop", "restart")[self.row_cursor - 2])

        if self.section is SetupSection.UPDATE:
            return ControllerAction(
                ActionKind.CHECK_UPDATE if self.row_cursor == 0 else ActionKind.START_UPDATE
            )

        if self.section is SetupSection.TOOLS:
            return ControllerAction(ActionKind.OPEN_PRODUCT_TOOL, self.row_cursor)

        if self.section is SetupSection.ABOUT:
            return ControllerAction()

        if self.section is SetupSection.REVIEW:
            if self.row_cursor == 0:
                return ControllerAction(ActionKind.SAVE)
            target = {
                1: SetupSection.DPI,
                2: SetupSection.POLLING,
                3: SetupSection.BUTTONS,
                4: SetupSection.LIGHTING,
            }[self.row_cursor]
            self.nav.edit_from_review(target)
            self.row_cursor = 0
            return ControllerAction()
        return ControllerAction()

    def set_lighting_state(self, state: LightingState) -> bool:
        capability = next(
            (item for item in self.choices.lighting_zones if item.zone_id == state.zone_id),
            None,
        )
        if capability is None:
            self.status = "The selected lighting zone is unavailable."
            return False
        if not capability.writable:
            self.status = "Lighting knowledge is read-only; no write authority is available."
            return False
        try:
            normalized = validate_lighting_state(state, capability)
        except ValueError as exc:
            self.status = f"Lighting value rejected: {exc}"
            return False
        self.choices.lighting[state.zone_id] = normalized
        self.choices.lighting_changed = True
        self.status = f"{capability.name} lighting staged as {normalized.mode.value}."
        return True

    def set_dpi_value(self, index: int, requested: int) -> bool:
        """Compatibility helper used by controller tests; curses uses DpiEditSession."""
        if not self.choices.dpi_writable:
            self.status = "Live DPI tuning is unavailable for this mouse."
            return False
        if not self.choices.accepts_dpi(requested):
            self.status = f"{requested} DPI is outside the discovered hardware capability."
            return False
        try:
            result = self.backend.set_dpi(self.selected, requested)
            confirmed = getattr(result, "display_value", None)
            if not getattr(result, "confirmed", False):
                readback = self.backend.get_dpi(self.selected)
                confirmed = getattr(readback, "display_value", readback)
            if isinstance(confirmed, tuple):
                confirmed = confirmed[0]
            confirmed = int(confirmed)
            if confirmed != requested:
                self.status = f"Mouse reported {confirmed} DPI; requested value was not accepted."
                return False
        except (HardwareError, TypeError, ValueError, OSError, AttributeError) as exc:
            self.status = f"Could not test DPI: {exc}"
            return False
        self.choices.stages[index] = confirmed
        if index == 0:
            self.choices.active_dpi = confirmed
        self.choices.current_dpi = confirmed
        self.choices.verified_dpi_values.add(confirmed)
        self.choices.dpi_changed = True
        self.status = f"Stage {index + 1} verified at {confirmed} DPI."
        return True

    def apply_button_mapping(self, button: str, action: str) -> None:
        self.choices.mappings[button] = action
        self.status = f"{button} → {action}"

    def apply_polling_measurement(self, measurement: Any) -> None:
        self.polling_measurement = measurement
        if getattr(measurement, "standard_hz", None) is not None:
            self.choices.measured_polling_rate = int(measurement.standard_hz)
        self.choices.measured_polling_confidence = str(
            getattr(measurement, "confidence", "unknown")
        )
        if self.choices.measured_polling_rate is not None:
            self.status = (
                f"Measured approximately {self.choices.measured_polling_rate} Hz "
                f"({self.choices.measured_polling_confidence} confidence)."
            )
        else:
            self.status = (
                "Polling measurement was inconclusive: "
                + str(getattr(measurement, "rejection_reason", "insufficient evidence"))
            )

    def apply_guided_outcome(self, outcome: GuidedDiscoveryOutcome) -> None:
        self.guided_outcome = outcome
        self.discovery_result = outcome.result
        self.discovery_complete = True
        if outcome.dpi_writable or outcome.polling_writable:
            try:
                self.backend.close()
            except Exception:
                pass
            self.backend = self._backend_factory(self.selected)
            self._discover_into_choices()
        if outcome.dpi_action_identified and not self.choices.dpi_writable:
            self.status = (
                "DPI button behavior identified; DPI writes remain disabled until safely proven."
            )
        elif outcome.learning_skipped_reason:
            self.status = outcome.learning_skipped_reason
        else:
            self.status = "Guided observation finished; no speculative write authority was added."

    def apply_research_probe_outcome(self, outcome: Any) -> None:
        self.research_probe_outcome = outcome
        if getattr(outcome, "any_possible", False):
            self.status = (
                "Generic reversible write possibility physically validated; runtime write authority remains unchanged."
            )
        else:
            self.status = "Reversible research probe did not validate a generic write path."

    def apply_deep_learning_outcome(self, outcome: Any) -> None:
        self.deep_learning_outcome = outcome
        if getattr(outcome, "profile_path", None) is not None:
            self.refresh_discovery_backend(
                status="Calibrated DPI-stage behavior learned."
            )
            self._refresh_observed_profile()
            kinds = set(self.observed_hardware.transition_source_kinds)
            if kinds & {"hid_state", "feature_state", "evdev_absolute_stage"}:
                self.status = (
                    "Physical DPI cycle calibrated; absolute runtime notifications can "
                    "synchronize and resynchronize safely."
                )
            elif kinds & {"hid_cycle_trigger", "evdev_cycle_trigger"}:
                self.status = (
                    "Physical DPI cycle calibrated; trigger notifications remain "
                    "unsynchronized at startup and after reconnect."
                )
            else:
                self.status = (
                    "Physical DPI cycle calibrated; runtime transition source remains unresolved."
                )
        elif getattr(outcome, "wrap_confirmed", False):
            self.status = (
                "Physical DPI cycle was observed, but no unambiguous persistent HID stage field was promoted."
            )
        else:
            self.status = "Deeper DPI-stage learning finished without a complete validated cycle."

    @timed("tui_frame_preparation")
    def detail_rows(self) -> list[DisplayRow]:
        if self.section is SetupSection.DEVICE:
            return [
                DisplayRow("Select the mouse to configure."),
                DisplayRow(f"Current: {self.selected.name}"),
                DisplayRow("Press Enter to bind it and begin Automatic Discovery."),
            ]

        if self.section is SetupSection.HARDWARE:
            rows = [DisplayRow("Mouse Control Hardware Discovery", role="heading")]
            rows.extend(
                DisplayRow(
                    line,
                    dim=index == 1 or line.startswith(("•", "—")),
                    role="primary" if index == 0 else "normal",
                )
                for index, line in enumerate(self.hardware_lines())
            )
            if self.discovery_progress:
                rows.extend((DisplayRow(""), DisplayRow("Recent discovery progress", dim=True)))
                for event in self.discovery_progress[-4:]:
                    if event.determinate:
                        width = 20
                        filled = min(width, round(width * event.completed / event.total))
                        indicator = "[" + "█" * filled + "░" * (width - filled) + "]"
                    else:
                        indicator = "⠋"
                    rows.append(DisplayRow(f"{indicator} {event.message}", dim=True))
            rows.append(DisplayRow(""))
            rows.append(
                DisplayRow(
                    "Retry Automatic Discovery" if self.discovery_complete else "Run Automatic Discovery",
                    0,
                    role="action",
                )
            )
            next_section = self._next_configuration_section(SetupSection.HARDWARE)
            next_label = f"Continue to {next_section.value.lower()} configuration"
            rows.append(DisplayRow("Open Discovery Lab", 1, role="action"))
            if self.guided_discovery_available:
                rows.append(DisplayRow(self.deep_learning_label, 2, role="action"))
                rows.append(DisplayRow(next_label, 3, role="action"))
            else:
                rows.append(DisplayRow(next_label, 2, role="action"))
            rows.append(
                DisplayRow(
                    "Unknown hardware remains read-only until exact write semantics are PROVEN.",
                    dim=True,
                )
            )
            return rows

        if self.section is SetupSection.LAB:
            experiment = self.lab_experiment
            plan = (
                getattr(experiment, "next_plan", None)
                or getattr(experiment, "plan", None)
                or plan_next_experiment(initial_lab_hypotheses())
            )
            rows = [
                DisplayRow("Discovery Lab — Automatic Experiment Planner", role="heading"),
                DisplayRow("Selected-device capture is local, bounded, and read-only.", dim=True),
                DisplayRow(f"Current question: {plan.purpose}", role="primary"),
            ]
            repertoire = tuple(
                getattr(self.discovery_engine, "repertoire_candidates", ())
                if self.discovery_engine is not None else ()
            )
            lamzu = next((
                item for item in repertoire
                if item.family.name == "lamzu-aurora-feature64"
            ), None)
            if lamzu is not None:
                rows.extend((
                    DisplayRow("Known protocol family candidate: LAMZU Aurora  [RECOGNIZED]"),
                    DisplayRow("Vendor knowledge: available  [VENDOR EVIDENCE]", dim=True),
                    DisplayRow("Exact hardware proof: incomplete; physical qualification [UNVERIFIED]", dim=True),
                    DisplayRow(
                        "Writes: disabled pending verification; write authority [READ-ONLY]",
                        dim=True,
                    ),
                ))
            imported = self.vendor_capture_import
            if imported is not None:
                manifest = imported.manifest
                rows.extend((
                    DisplayRow("Vendor capture import", dim=True),
                    DisplayRow(
                        f"Format: {manifest.parser_selected}; "
                        f"accepted {manifest.accepted_records}/{manifest.total_records} records"
                    ),
                    DisplayRow(f"Source digest: {manifest.source_digest[:12]}…"),
                    DisplayRow(
                        "Families: " + (
                            ", ".join(manifest.protocol_families_recognized) or "unrecognized"
                        )
                    ),
                    DisplayRow(
                        f"Warnings: {len(manifest.warnings)}; conflicts: {len(manifest.conflicts)}; "
                        f"dangerous/suppressed: {manifest.dangerous_suppressed_records}"
                    ),
                    DisplayRow(
                        f"Review state: {manifest.review_status.value.replace('_', ' ')}"
                    ),
                    DisplayRow(
                        "Imported evidence does not enable writes or grant hardware write authority."
                    ),
                ))
            if plan.selected_action is not None:
                rows.extend([
                    DisplayRow(f"Best experiment: {plan.selected_action.label}"),
                    DisplayRow(
                        f"Why: expected information gain {plan.expected_information_gain_bits:.2f} bits; "
                        f"{plan.safety_class.value.replace('_', ' ')}.",
                        dim=True,
                    ),
                    DisplayRow(
                        "Automatic: capture baseline/action/control, compare fields, and update hypotheses.",
                        dim=True,
                    ),
                    DisplayRow(f"Your part: {plan.human_instructions[0]}"),
                ])
            analysis = getattr(experiment, "analysis", None)
            if analysis is None:
                rows.extend([
                    DisplayRow("What is known: no Lab experiment has been run yet.", dim=True),
                    DisplayRow("What is uncertain: action-specific protocol fields.", dim=True),
                ])
            else:
                fields = analysis.ranked_fields
                correlated = [
                    item for item in fields
                    if any(signal.value == "action_correlated" for signal in item.signals)
                ]
                rows.append(DisplayRow(
                    f"Just learned: {len(correlated)} action-correlated field(s) across "
                    f"{len(experiment.observations)} protocol observation(s)."
                ))
                for item in fields[:4]:
                    labels = ", ".join(signal.value.replace("_", " ") for signal in item.signals)
                    rows.append(DisplayRow(
                        f"{item.stream_id[-12:]} byte {item.offset}: {labels} (rank {item.score:g})"
                    ))
                timing = getattr(experiment, "timing_profile", None)
                rows.append(DisplayRow("Protocol timing", dim=True))
                if timing is None or not timing.summaries:
                    rows.append(DisplayRow(
                        "No established temporal relationship was present in this capture.",
                        dim=True,
                    ))
                else:
                    for summary in timing.summaries[:4]:
                        label = summary.relationship.value.replace("_", " → ", 1).replace("_", " ")
                        detail = f"median {_format_timing_ns(summary.median_ns)}"
                        if summary.accepted_count >= 2:
                            stable = (
                                summary.spread_ns is not None
                                and summary.median_ns not in {None, 0}
                                and summary.spread_ns / summary.median_ns <= 0.25
                            )
                            if stable:
                                detail += f", stable across {summary.accepted_count} samples"
                            else:
                                detail += (
                                    f", variable {_format_timing_ns(summary.minimum_ns)}–"
                                    f"{_format_timing_ns(summary.maximum_ns)}"
                                )
                        else:
                            detail += ", insufficient repeated evidence"
                        rows.append(DisplayRow(f"{label}: {detail}"))
                    stale = [
                        item for item in timing.summaries
                        if item.relationship.value == "read_to_fresh_state_latency"
                    ]
                    if stale:
                        rows.append(DisplayRow(
                            "Immediate readable state was superseded; freshness is questionable "
                            f"for about {_format_timing_ns(stale[0].median_ns)}."
                        ))
                    for delta in timing.differentials[:2]:
                        rows.append(DisplayRow(
                            f"Timing delta: baseline {_format_timing_ns(delta.baseline_median_ns)} "
                            f"→ action {_format_timing_ns(delta.action_median_ns)}"
                        ))
                recommendation = analysis.next_recommended_experiment
                if recommendation is not None:
                    rows.append(DisplayRow(
                        f"Next: {recommendation.experiment.replace('_', ' ')} — "
                        f"{recommendation.reason}"
                    ))
                    rows.append(DisplayRow(
                        "Hardware write required: yes" if recommendation.requires_hardware_write
                        else "Hardware write required: no"
                    ))
                if analysis.contradictions:
                    rows.append(DisplayRow(
                        f"Uncertain: {len(analysis.contradictions)} negative-control contradiction(s)."
                    ))
                updates = getattr(experiment, "hypothesis_updates", ())
                strengthened = [item for item in updates if item.after.value in {"supported", "strengthened"}]
                rejected = [item for item in updates if item.after.value in {"rejected", "weakened"}]
                if strengthened:
                    rows.append(DisplayRow(
                        "Result: " + ", ".join(item.hypothesis_id for item in strengthened)
                        + " gained evidence."
                    ))
                if rejected:
                    rows.append(DisplayRow(
                        "Rejected or weakened: " + ", ".join(item.hypothesis_id for item in rejected)
                    ))
                next_plan = getattr(experiment, "next_plan", None)
                if next_plan is not None and next_plan.selected_action is not None:
                    rows.append(DisplayRow(
                        f"Next uncertainty: {next_plan.purpose}; try {next_plan.selected_action.label}."
                    ))
                assessment = getattr(experiment, "persistence_assessment", None)
                if assessment is not None:
                    rows.append(DisplayRow("Effect / persistence", dim=True))
                    rows.append(DisplayRow(
                        "Effect: " + assessment.effective_state.value.replace("_", " ")
                    ))
                    persistence = ", ".join(
                        item.value.replace("_", " ") for item in assessment.classifications
                    )
                    rows.append(DisplayRow(f"Persistence: {persistence or 'unknown'}"))
                    if assessment.strongest_confirmed_level is not None:
                        rows.append(DisplayRow(
                            "Strongest tested level: "
                            + assessment.strongest_confirmed_level.name.lower().replace("_", " ")
                        ))
                    if assessment.contradictions:
                        rows.append(DisplayRow(
                            f"Contradictions retained: {len(assessment.contradictions)}"
                        ))
                    if assessment.restoration.required:
                        rows.append(DisplayRow(
                            "Restore original state manually, then verify restoration."
                        ))
                routing = getattr(experiment, "routing_analysis", None)
                if routing is not None:
                    rows.append(DisplayRow("Receiver / Device Routing", dim=True))
                    for finding in routing.summary[:4]:
                        rows.append(DisplayRow(finding))
                    confirmed_routes = [
                        item for item in routing.evidence
                        if item.status.value == "confirmed_route"
                    ]
                    rows.append(DisplayRow(
                        f"Confirmed logical routes: {len(confirmed_routes)}"
                    ))
                    if routing.ambiguities:
                        rows.append(DisplayRow(
                            f"Unresolved routing questions: {len(routing.ambiguities)}"
                        ))
                    if routing.next_plan is not None and routing.next_plan.selected_action is not None:
                        rows.append(DisplayRow(
                            "Best next routing experiment: "
                            + routing.next_plan.selected_action.label
                        ))
                power = getattr(experiment, "power_analysis", None)
                if power is not None:
                    rows.append(DisplayRow("Battery / Power", dim=True))
                    for finding in power.summary[:8]:
                        rows.append(DisplayRow(finding))
                    if power.contradictions:
                        rows.append(DisplayRow(
                            f"Power contradictions retained: {len(power.contradictions)}"
                        ))
                    if power.pending_natural_observation:
                        rows.append(DisplayRow(
                            "Passive follow-up: retain this candidate during normal future use."
                        ))
                    if power.next_plan is not None and power.next_plan.selected_action is not None:
                        rows.append(DisplayRow(
                            "Best next power experiment: "
                            + power.next_plan.selected_action.label
                        ))
            rows.extend([
                DisplayRow("Run Full Automatic Lab", 0, role="action"),
                DisplayRow("Advanced Tools", 1, role="action"),
                DisplayRow("Import Vendor Capture", 2, role="action"),
                DisplayRow(
                    f"Continue to {self._next_configuration_section(SetupSection.LAB).value} configuration",
                    3,
                    role="action",
                ),
                DisplayRow("Recognition and correlation never grant hardware write authority.", dim=True),
            ])
            return rows

        if self.section is SetupSection.DPI:
            mode = (
                "read/write" if self.choices.dpi_writable
                else "read-only" if self.choices.dpi_readable
                else "not yet discovered"
            )
            current = self.choices.current_dpi or self.choices.active_dpi
            primary = f"{current} DPI" if current is not None else "DPI unknown"
            rows = [DisplayRow(f"{primary:<14} {mode.upper()}", role="primary")]
            if self.choices.dpi_minimum is not None and self.choices.dpi_maximum is not None:
                text = f"Range {self.choices.dpi_minimum}–{self.choices.dpi_maximum} DPI"
                if self.choices.dpi_increment:
                    text += f"  ·  Step {self.choices.dpi_increment}"
                text += f"  ·  {len(self.choices.stages)} stages"
                rows.append(DisplayRow(text, dim=True))
            elif self.choices.dpi_values:
                rows.append(DisplayRow(
                    "Values " + " · ".join(map(str, self.choices.dpi_values))
                    + f"  ·  {len(self.choices.stages)} stages",
                    dim=True,
                ))
            rows.append(DisplayRow("Configured stages", role="heading"))
            if not self.choices.dpi_writable:
                rows.append(
                    DisplayRow(
                        "Hardware DPI cannot be safely written yet; stages are preserved.",
                        0,
                        dim=True,
                    )
                )
                return rows
            for index, value in enumerate(self.choices.stages):
                marker = "  ✓ verified" if value in self.choices.verified_dpi_values else ""
                active = "  active" if value == self.choices.active_dpi else ""
                rows.append(DisplayRow(
                    f"{index + 1:>2}.  {value:>5} DPI{active}{marker}",
                    index,
                    role="action",
                ))
            rows.append(DisplayRow("Enter opens a reversible live-test/readback editor.", dim=True))
            return rows

        if self.section is SetupSection.POLLING:
            mode = (
                "read/write" if self.choices.polling_writable
                else "read-only" if self.choices.polling_readable
                else "not yet discovered"
            )
            current = (
                self.choices.current_polling_rate
                or self.choices.measured_polling_rate
                or self.choices.polling_rate
            )
            primary = f"{current} Hz" if current is not None else "Rate unknown"
            rows = [DisplayRow(f"{primary:<14} {mode.upper()}", role="primary")]
            if self.choices.polling_rates:
                rows.append(DisplayRow(
                    "Supported " + " · ".join(f"{hz} Hz" for hz in self.choices.polling_rates),
                    dim=True,
                ))
            if self.choices.measured_polling_rate is not None:
                rows.append(
                    DisplayRow(
                        f"Motion measurement {self.choices.measured_polling_rate} Hz "
                        f"· {self.choices.measured_polling_confidence}",
                        dim=True,
                    )
                )
            if self.choices.polling_writable and self.choices.polling_rates:
                rows.append(DisplayRow("Available rates", role="heading"))
                for index, hz in enumerate(self.choices.polling_rates):
                    selected = "  ✓ configured" if hz == self.choices.polling_rate else ""
                    rows.append(DisplayRow(
                        f"{hz:>5} Hz{selected}", index, role="action"
                    ))
                rows.append(
                    DisplayRow("Measure current rate from motion timing (read-only)",
                               len(self.choices.polling_rates), role="action")
                )
                rows.append(
                    DisplayRow("Selected writes are verified only during final apply.", dim=True)
                )
            else:
                rows.append(DisplayRow(
                    "Measure current rate from motion timing (read-only)", 0, role="action"
                ))
                rows.append(
                    DisplayRow("No unproven polling write will be attempted.", dim=True)
                )
            return rows

        if self.section is SetupSection.BUTTONS:
            rows = [
                DisplayRow("Button mappings", role="heading"),
                DisplayRow(f"{len(self.choices.mappings)} mapping(s) configured.", dim=True),
                DisplayRow("Configure / edit mouse buttons", 0, role="action"),
            ]
            for button, action in sorted(self.choices.mappings.items()):
                rows.append(DisplayRow(f"{button:<18} → {action}"))
            rows.extend((
                DisplayRow(
                    "Keyboard capture is exclusive; shortcuts are suppressed while recording.",
                    dim=True,
                ),
                DisplayRow(
                    "Existing mappings are preserved unless you change a button.", dim=True
                ),
            ))
            return rows

        if self.section is SetupSection.LIGHTING:
            rows = [
                DisplayRow("Hardware lighting", role="heading"),
                DisplayRow(
                    "Optional capability · native device effects only · no host animation",
                    dim=True,
                ),
            ]
            if not self.choices.lighting_zones:
                rows.extend((
                    DisplayRow("Lighting unsupported or not yet qualified", 0, dim=True),
                    DisplayRow("DPI, polling, buttons, remapping, and service remain supported.", dim=True),
                ))
                return rows
            for index, zone in enumerate(self.choices.lighting_zones):
                state = self.choices.lighting.get(zone.zone_id)
                mode = state.mode.value if state else "unchanged"
                color = f" · {state.color}" if state and state.color else ""
                authority = "writable" if zone.writable else "read-only"
                rows.append(DisplayRow(
                    f"{zone.name}: {mode}{color}  [{authority}]", index, role="action"
                ))
                rows.append(DisplayRow(
                    "Modes: " + ", ".join(item.value for item in zone.modes)
                    + " · persistence: " + ", ".join(item.value for item in zone.persistence),
                    dim=True,
                ))
            rows.append(DisplayRow("Colors use full #RRGGBB input where RGB24 is proven.", dim=True))
            return rows

        if self.section is SetupSection.SERVICE:
            return [
                DisplayRow("Background service", role="heading"),
                DisplayRow("Enable at login" + ("  ✓" if self.choices.enable_service else ""), 0, role="action"),
                DisplayRow("Keep disabled" + ("  ✓" if not self.choices.enable_service else ""), 1, role="action"),
                DisplayRow("Show current status", 2, role="action"),
                DisplayRow("Start now", 3, role="action"),
                DisplayRow("Stop now", 4, role="action"),
                DisplayRow("Restart now", 5, role="action"),
            ]

        if self.section is SetupSection.UPDATE:
            from . import __version__
            latest = (
                getattr(self.update_status, "available_version", None) or "not checked"
            )
            return [
                DisplayRow("Mouse Control Updates", role="heading"),
                DisplayRow(f"Installed version: {__version__}", role="primary"),
                DisplayRow(f"Available version: {latest}"),
                DisplayRow("Check for updates", 0, role="action"),
                DisplayRow("Start verified update", 1, role="action"),
                DisplayRow("Uses the canonical signed-source/checksum updater path.", dim=True),
            ]

        if self.section is SetupSection.TOOLS:
            labels = (
                "Diagnostics / doctor", "Permissions", "Support bundle",
                "Configuration path", "Read-only HID inspection",
                "Protocol / evidence inspection", "Discovery export / rediscovery",
                "Logs and recovery guidance",
            )
            return [
                DisplayRow("Tools / Advanced", role="heading"),
                DisplayRow("Ordinary diagnostics and advanced research routes", dim=True),
                *[DisplayRow(label, index, role="action") for index, label in enumerate(labels)],
                DisplayRow("Hardware-writing research remains behind its existing authority gates.", dim=True),
            ]

        if self.section is SetupSection.ABOUT:
            from . import __version__
            backend = getattr(self.backend, "name", "unavailable")
            return [
                DisplayRow("About Mouse Control", role="heading"),
                DisplayRow(f"Version {__version__}", role="primary"),
                DisplayRow(f"Selected backend: {backend}"),
                DisplayRow("Linux evdev/uinput remapping with evidence-gated hardware control."),
                DisplayRow("Project: github.com/DonGeronimo7/mouse-control", dim=True),
            ]

        rows = [
            DisplayRow("Final review", role="heading"),
            DisplayRow(f"Mouse:       {self.selected.name}", role="primary"),
        ]
        if self.selected.vendor is not None and self.selected.product is not None:
            rows.append(DisplayRow(
                f"Identity:    {self.selected.vendor:04x}:{self.selected.product:04x}"
            ))
        rows.append(DisplayRow(
            f"Connection:  {self.selected.phys or self.selected.path or 'unknown'}"
        ))
        if self.observed_hardware.calibrated_dpi_cycle:
            rows.append(DisplayRow(
                "Measured physical DPI cycle: ~"
                + " → ~".join(map(str, self.observed_hardware.calibrated_dpi_cycle))
                + f" ({self.observed_hardware.calibration_confidence} confidence)"
            ))
        else:
            rows.append(DisplayRow("Measured physical DPI cycle: unavailable"))
        measured_rate = (
            self.choices.measured_polling_rate
            if self.choices.measured_polling_rate is not None
            else self.observed_hardware.measured_polling_rate
        )
        measured_confidence = (
            self.choices.measured_polling_confidence
            if self.choices.measured_polling_rate is not None
            else self.observed_hardware.measured_polling_confidence
        )
        rows.extend([
            DisplayRow(
                (
                    f"Measured polling: ~{measured_rate} Hz "
                    f"({measured_confidence or 'unknown'} confidence)"
                )
                if measured_rate is not None
                else "Measured polling: unavailable"
            ),
            DisplayRow(
                "Configured software stages: "
                + " → ".join(map(str, self.choices.stages))
            ),
            DisplayRow(
                f"Configured polling preference: {self.choices.polling_rate} Hz"
                if self.choices.polling_rate is not None
                else "Configured polling preference: unchanged"
            ),
            DisplayRow(
                "DPI write control: available (proven)"
                if self.choices.dpi_writable else "DPI write control: unavailable / unproven"
            ),
            DisplayRow(
                "Polling write control: available (proven)"
                if self.choices.polling_writable else "Polling write control: unavailable / unproven"
            ),
            DisplayRow(f"Buttons:     {len(self.choices.mappings)} mappings"),
            DisplayRow(f"Lighting:    {len(self.choices.lighting)} zone preference(s)"),
            DisplayRow(f"Service:     {'enabled' if self.choices.enable_service else 'disabled'}"),
            DisplayRow(
                "Capability limitation: hardware writes require exact-device PROVEN evidence."
                if not (self.choices.dpi_writable and self.choices.polling_writable)
                else "Capability limitation: none for reviewed DPI and polling controls."
            ),
            DisplayRow(""),
            *[DisplayRow(line) for line in self.hardware_lines()],
            DisplayRow(""),
            DisplayRow("Save and Finish", 0, role="action"),
            DisplayRow("Edit DPI", 1, role="action"),
            DisplayRow("Edit polling", 2, role="action"),
            DisplayRow("Edit buttons", 3, role="action"),
            DisplayRow("Edit lighting", 4, role="action"),
        ])
        return rows


def run_setup_tui(
    devices: list[Any] | tuple[Any, ...],
    existing_config: dict[str, object],
    *,
    choices_factory: Callable[[dict[str, object]], SetupChoices],
    backend_factory: Callable[[Any], Any] = get_backend,
) -> SetupTuiResult:
    """Run the full-screen setup interface and always restore terminal state."""
    from .setup_tui_curses import CursesSetupApp, run_curses

    controller = SetupController(
        devices,
        existing_config,
        choices_factory=choices_factory,
        backend_factory=backend_factory,
        initialize_backend=False,
    )
    app = CursesSetupApp(controller)
    try:
        finished = run_curses(app)
    except BaseException:
        if app.controller.backend_ready:
            app.controller.restore_temporary_state()
        raise
    controller = app.controller
    return SetupTuiResult(
        finished=bool(finished),
        selected=controller.selected,
        backend=controller.backend,
        choices=controller.choices,
    )
