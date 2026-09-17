"""State-driven, dependency-free setup TUI for Mouse Control.

The controller is deliberately independent of curses so navigation and state
transitions can be unit-tested without a real terminal. Curses is only the
presentation/input adapter; existing setup choices, hardware backends, and
Automatic Discovery remain the source of truth.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass
from enum import Enum, auto
import io
from typing import Any, Callable

from .discovery_lab import DiscoveryTool, discovery_tool_specs
from .guided_discovery import GuidedDiscoveryOutcome
from .hardware import HardwareError, get_backend
from .setup_flow import SetupChoices, discover_choices, restore_dpi


class SetupSection(Enum):
    DEVICE = "Device"
    HARDWARE = "Hardware / Discovery"
    BUTTONS = "Buttons"
    DPI = "DPI"
    POLLING = "Polling"
    SERVICE = "Service"
    REVIEW = "Review / Save"


SECTIONS = tuple(SetupSection)


class ActionKind(Enum):
    NONE = auto()
    HELP = auto()
    CANCEL = auto()
    EDIT_DPI = auto()
    CAPTURE_BUTTONS = auto()
    GUIDED_DISCOVERY = auto()
    RUN_DISCOVERY_TOOL = auto()
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


@dataclass(frozen=True)
class SetupTuiResult:
    finished: bool
    selected: Any
    backend: Any
    choices: SetupChoices


class SetupController:
    """Pure setup navigation/state model with injected hardware factories."""

    def __init__(
        self,
        devices: list[Any] | tuple[Any, ...],
        existing_config: dict[str, object],
        *,
        choices_factory: Callable[[dict[str, object]], SetupChoices],
        backend_factory: Callable[[Any], Any] = get_backend,
    ) -> None:
        if not devices:
            raise ValueError("setup requires at least one mouse")
        self.devices = tuple(devices)
        self.existing_config = existing_config
        self._choices_factory = choices_factory
        self._backend_factory = backend_factory
        self.section_index = 0
        self.row_cursor = 0
        self.discovery_skipped = False
        self.guided_outcome: GuidedDiscoveryOutcome | None = None
        self.status = "Choose a mouse, then use ←/→ to move through setup."
        self.notice = ""
        self.selected_index = self._configured_device_index()
        self.device_cursor = self.selected_index
        self.selected = self.devices[self.selected_index]
        self.backend: Any = None
        self.choices = self._choices_factory(self.existing_config)
        self._bind_device(self.selected_index, restore_old=False, reset_choices=True)

    @property
    def section(self) -> SetupSection:
        return SECTIONS[self.section_index]

    def _configured_device_index(self) -> int:
        configured = self.existing_config.get("device", {})
        if not isinstance(configured, dict):
            return 0
        vendor = configured.get("vendor")
        product = configured.get("product")
        phys = configured.get("phys")
        candidates = [
            index for index, device in enumerate(self.devices)
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

    def _bind_device(
        self,
        index: int,
        *,
        restore_old: bool = True,
        reset_choices: bool = True,
    ) -> None:
        if restore_old and self.backend is not None:
            try:
                restore_dpi(self.backend, self.selected, self.choices.original_dpi)
            except OSError:
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
        self.backend = self._backend_factory(self.selected)
        self._discover_into_choices()
        self.discovery_skipped = False
        self.guided_outcome = None
        self.status = f"Selected {self.selected.name}."

    def restore_temporary_state(self) -> None:
        try:
            restore_dpi(self.backend, self.selected, self.choices.original_dpi)
        except OSError:
            pass

    @property
    def protocol_adapter_name(self) -> str | None:
        return getattr(self.backend, "protocol_adapter_name", None)

    @property
    def has_proven_learned_adapter(self) -> bool:
        return bool(getattr(self.backend, "has_proven_learned_adapter", False))

    def _supports_dpi_events(self) -> bool:
        try:
            return bool(self.backend.supports_dpi_events(self.selected))
        except (HardwareError, AttributeError, OSError):
            return False

    @property
    def guided_discovery_available(self) -> bool:
        return not self.choices.dpi_writable and not self.discovery_skipped

    def hardware_actions(self) -> tuple[tuple[str, str, Any], ...]:
        """Return the complete evidence ladder exposed by the discovery screen."""
        actions: list[tuple[str, str, Any]] = []
        if self.guided_discovery_available:
            actions.append((
                "guided",
                "Observe / learn DPI-button behavior (read-only)",
                None,
            ))
        for spec in discovery_tool_specs():
            prefix = "PROVE" if spec.promotion else "LAB"
            actions.append(("tool", f"{prefix}: {spec.label}", spec.tool))
        actions.append(("continue", "Continue to button mapping", None))
        return tuple(actions)

    def hardware_lines(self) -> list[str]:
        lines = [
            "✓ Automatic Discovery",
            "✓ Physical topology + descriptor grammar",
            "✓ Physical CPI / polling measurement",
            "✓ Reversible exact-model write promotion pipeline",
            "✓ Stateful polling promotion pipeline",
            "✓ Mouse detected",
            "✓ Button remapping available",
        ]
        if self.protocol_adapter_name:
            lines.insert(2, f"✓ {self.protocol_adapter_name}")
        elif self.has_proven_learned_adapter:
            lines.insert(2, "✓ Learned exact-model support")

        if self.choices.dpi_writable:
            lines.append("✓ DPI control")
        elif self.guided_outcome and self.guided_outcome.dpi_action_identified:
            lines.append("✓ DPI button behavior identified")
            lines.append("? DPI write command not yet proven")
        else:
            lines.append("? DPI control not yet learned")

        if self.choices.polling_writable:
            lines.append("✓ Polling-rate control")
        else:
            lines.append("? Polling control not yet learned")

        if self._supports_dpi_events():
            lines.append("✓ Physical DPI events")
        if self.guided_outcome and self.guided_outcome.learning_skipped_reason:
            lines.append(self.guided_outcome.learning_skipped_reason)
        return lines

    def row_count(self) -> int:
        if self.section is SetupSection.DEVICE:
            return len(self.devices)
        if self.section is SetupSection.HARDWARE:
            return len(self.hardware_actions())
        if self.section is SetupSection.BUTTONS:
            return 1
        if self.section is SetupSection.DPI:
            return len(self.choices.stages) if self.choices.dpi_writable else 1
        if self.section is SetupSection.POLLING:
            return len(self.choices.polling_rates) if (
                self.choices.polling_writable and self.choices.polling_rates
            ) else 1
        if self.section is SetupSection.SERVICE:
            return 2
        return 1

    def _clamp_cursor(self) -> None:
        self.row_cursor = max(0, min(self.row_cursor, self.row_count() - 1))

    def handle_key(self, key: str) -> ControllerAction:
        key = key.upper()
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
            self.section_index = max(0, self.section_index - 1)
            self.row_cursor = self.device_cursor if self.section is SetupSection.DEVICE else 0
            self._clamp_cursor()
            return ControllerAction()
        if key == "RIGHT":
            self.section_index = min(len(SECTIONS) - 1, self.section_index + 1)
            self.row_cursor = self.device_cursor if self.section is SetupSection.DEVICE else 0
            self._clamp_cursor()
            return ControllerAction()
        if key in {"BACK", "ESC"}:
            if self.section_index > 0:
                self.section_index -= 1
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
            if self.device_cursor != self.selected_index:
                self._bind_device(self.device_cursor)
            self.section_index = SECTIONS.index(SetupSection.HARDWARE)
            self.row_cursor = 0
            return ControllerAction()
        if self.section is SetupSection.HARDWARE:
            kind, _label, payload = self.hardware_actions()[self.row_cursor]
            if kind == "guided":
                return ControllerAction(ActionKind.GUIDED_DISCOVERY)
            if kind == "tool":
                return ControllerAction(ActionKind.RUN_DISCOVERY_TOOL, payload)
            self.section_index = SECTIONS.index(SetupSection.BUTTONS)
            self.row_cursor = 0
            return ControllerAction()
        if self.section is SetupSection.BUTTONS:
            return ControllerAction(ActionKind.CAPTURE_BUTTONS)
        if self.section is SetupSection.DPI:
            if not self.choices.dpi_writable:
                self.status = "DPI hardware control is not yet learned for this mouse."
                return ControllerAction()
            return ControllerAction(ActionKind.EDIT_DPI, self.row_cursor)
        if self.section is SetupSection.POLLING:
            if self.choices.polling_writable and self.choices.polling_rates:
                self.choices.polling_rate = self.choices.polling_rates[self.row_cursor]
                self.choices.polling_changed = True
                self.status = f"Polling preference set to {self.choices.polling_rate} Hz."
            else:
                self.status = "Polling-rate control is not yet safely proven; hardware remains unchanged."
            return ControllerAction()
        if self.section is SetupSection.SERVICE:
            self.choices.enable_service = self.row_cursor == 0
            self.status = (
                "Background service will be enabled."
                if self.choices.enable_service
                else "Background service will remain disabled."
            )
            return ControllerAction()
        if self.section is SetupSection.REVIEW:
            return ControllerAction(ActionKind.SAVE)
        return ControllerAction()

    def set_dpi_value(self, index: int, requested: int) -> bool:
        values = self.choices.dpi_values
        if not self.choices.dpi_writable:
            self.status = "Live DPI tuning is unavailable for this mouse."
            return False
        if not values or requested not in values:
            if values:
                self.status = f"{requested} DPI is unsupported; choose {values[0]}–{values[-1]} from reported values."
            else:
                self.status = "The mouse did not report safe DPI values for live tuning."
            return False
        try:
            result = self.backend.set_dpi(self.selected, requested)
            confirmed = result
            if confirmed is None:
                confirmed = self.backend.get_dpi(self.selected)
            if hasattr(confirmed, "display_value"):
                confirmed = confirmed.display_value
            if isinstance(confirmed, tuple):
                confirmed = confirmed[0]
            confirmed = int(confirmed)
            if confirmed != requested:
                self.status = f"Mouse reported {confirmed} DPI; requested value was not accepted."
                return False
        except (HardwareError, TypeError, ValueError, OSError) as exc:
            self.status = f"Could not test DPI: {exc}"
            return False
        self.choices.stages[index] = confirmed
        if index == 0:
            self.choices.active_dpi = confirmed
        self.choices.dpi_changed = True
        self.status = f"Stage {index + 1} verified at {confirmed} DPI."
        return True

    def apply_button_mapping(self, button: str, action: str) -> None:
        self.choices.mappings[button] = action
        self.status = f"{button} → {action}"

    def apply_guided_outcome(self, outcome: GuidedDiscoveryOutcome) -> None:
        self.guided_outcome = outcome
        if outcome.dpi_writable or outcome.polling_writable:
            self.refresh_discovery_backend(status="Guided discovery completed.")
        if outcome.dpi_action_identified and not self.choices.dpi_writable:
            self.status = "DPI button behavior identified; DPI writes remain disabled until safely proven."
        elif outcome.learning_skipped_reason:
            self.status = outcome.learning_skipped_reason
        else:
            self.status = "Guided observation finished; no write authority was added."

    def refresh_discovery_backend(self, *, status: str = "Discovery evidence refreshed.") -> None:
        """Rebind capability stores after a laboratory without discarding setup choices."""
        try:
            self.backend.close()
        except Exception:
            pass
        self.backend = self._backend_factory(self.selected)
        self._discover_into_choices()
        self.status = status

    def detail_rows(self) -> list[DisplayRow]:
        if self.section is SetupSection.DEVICE:
            return [
                DisplayRow("Select the mouse to configure."),
                DisplayRow(f"Current: {self.selected.name}"),
                DisplayRow("Press Enter on a device in the left pane to bind it."),
            ]
        if self.section is SetupSection.HARDWARE:
            rows = [DisplayRow("OBSERVE → CORRELATE → VALIDATE → PROVE", dim=True)]
            for index, (_kind, label, _payload) in enumerate(self.hardware_actions()):
                rows.append(DisplayRow(label, index))
            rows.extend((DisplayRow(""), DisplayRow("Detected capabilities", dim=True)))
            rows.extend(DisplayRow(line) for line in self.hardware_lines())
            return rows
        if self.section is SetupSection.BUTTONS:
            return [
                DisplayRow("Button mappings"),
                DisplayRow(f"{len(self.choices.mappings)} mapping(s) configured."),
                DisplayRow("Configure / edit mouse buttons", 0),
                DisplayRow("Existing mappings are preserved unless you change a button.", dim=True),
            ]
        if self.section is SetupSection.DPI:
            rows = [DisplayRow("DPI stages")]
            if not self.choices.dpi_writable:
                rows.extend((
                    DisplayRow("? Hardware DPI control not yet learned"),
                    DisplayRow("Configured stages are preserved and no DPI write will be attempted.", dim=True),
                ))
                return rows
            for index, value in enumerate(self.choices.stages):
                rows.append(DisplayRow(f"Stage {index + 1}: {value} DPI", index))
            rows.append(DisplayRow("Enter edits a stage using hardware-reported safe values.", dim=True))
            return rows
        if self.section is SetupSection.POLLING:
            rows = [DisplayRow("Polling rate")]
            if self.choices.current_polling_rate is not None:
                rows.append(DisplayRow(f"Current hardware rate: {self.choices.current_polling_rate} Hz"))
            if self.choices.polling_writable and self.choices.polling_rates:
                for index, hz in enumerate(self.choices.polling_rates):
                    selected = "  ✓" if hz == self.choices.polling_rate else ""
                    rows.append(DisplayRow(f"{hz} Hz{selected}", index))
            else:
                rows.extend((
                    DisplayRow("? Polling control not yet learned"),
                    DisplayRow("Current polling rate will remain unchanged.", dim=True),
                ))
            return rows
        if self.section is SetupSection.SERVICE:
            return [
                DisplayRow("Background service"),
                DisplayRow("Enable at login" + ("  ✓" if self.choices.enable_service else ""), 0),
                DisplayRow("Keep disabled" + ("  ✓" if not self.choices.enable_service else ""), 1),
            ]
        return [
            DisplayRow("Review"),
            DisplayRow(f"Mouse:       {self.selected.name}"),
            DisplayRow("DPI stages:  " + " → ".join(map(str, self.choices.stages))),
            DisplayRow(
                f"Polling:     {self.choices.polling_rate} Hz"
                if self.choices.polling_rate is not None else "Polling:     unchanged"
            ),
            DisplayRow(f"Buttons:     {len(self.choices.mappings)} mappings"),
            DisplayRow(f"Service:     {'enabled' if self.choices.enable_service else 'disabled'}"),
            DisplayRow(""),
            *[DisplayRow(line) for line in self.hardware_lines()],
            DisplayRow(""),
            DisplayRow("Save and Finish", 0),
        ]


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
    )
    try:
        finished = run_curses(CursesSetupApp(controller))
    except BaseException:
        controller.restore_temporary_state()
        raise
    return SetupTuiResult(
        finished=bool(finished),
        selected=controller.selected,
        backend=controller.backend,
        choices=controller.choices,
    )
