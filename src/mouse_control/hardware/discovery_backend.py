"""Universal mouse hardware backend powered by Automatic Discovery.

Every selected mouse is represented to the rest of Mouse Control through this
backend.  Discovery owns identity, passive evidence, learned read-side grammar,
and capability exposure.  Proven vendor/protocol implementations are internal
adapters: they may provide validated reads/writes, but callers no longer select
a vendor backend directly.

Physically calibrated read profiles are observation authority only and can
never authorize a HID write. Separately promoted exact-model learned operations
may provide writable support after raw readback plus physical verification.
Known vendor/protocol adapters remain optional internal teachers/adapters.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import json
import logging
import os
import queue
from pathlib import Path
import select
import threading
from typing import Any, Mapping

from ..calibrated_profiles import (
    CalibratedProfileError,
    get_calibrated_profile_directory,
    validate_calibrated_profile,
)
from ..device_topology import build_device_graph
from ..learned_actions import (
    LearnedActionStore,
    LearnedActionTrigger,
)
from ..learned_hid_session import (
    LearnedHidSession,
    LearnedHidSessionError,
)
from ..learned_hid_transport import (
    LearnedHidAdapter,
    LearnedHidTransportError,
    learned_dpi_read_spec,
    learned_dpi_transaction_spec,
)
from ..learned_operations import (
    LearnedOperation,
    LearnedOperationError,
    LearnedOperationStore,
    matching_interface_node,
)
from ..learned_polling import (
    LearnedPollingOperation,
    LearnedPollingOperationStore,
)
from ..learned_polling_transport import (
    LearnedPollingTransportError,
    execute_learned_polling,
    learned_polling_write_without_takeover,
    read_learned_polling_rate,
)
from ..protocol_grammar import SemanticBehavior
from ..transaction_engine import (
    TransactionAuthorization,
    TransactionContext,
    TransactionEngine,
    TransactionError,
)
from ..discovery import MouseDevice
from ..discovery_models import DeviceNode, PhysicalDevice
from .base import HardwareBackend, HardwareError
from .capabilities import (
    DpiCapabilities,
    DpiState,
    HardwareCapabilities,
    ReportRateCapabilities,
)

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class _LearnedDpiBinding:
    physical: PhysicalDevice
    node: DeviceNode
    report_length: int
    report_id: int
    offset: int
    raw_to_dpi: Mapping[int, int]


class DiscoveryBackend(HardwareBackend):
    """Universal hardware surface for known and unknown mice."""

    def __init__(
        self,
        *,
        profile_directory: Path | None = None,
        learned_operation_store: LearnedOperationStore | None = None,
        learned_polling_store: LearnedPollingOperationStore | None = None,
        learned_action_store: LearnedActionStore | None = None,
        topology_builder: Callable[[MouseDevice], PhysicalDevice] = build_device_graph,
        protocol_factories: Iterable[Callable[[], HardwareBackend]] = (),
        log_protocol_failures: bool = True,
        learned_session_factory=LearnedHidSession,
    ) -> None:
        self.profile_directory = profile_directory or get_calibrated_profile_directory()
        self._learned_operation_store = learned_operation_store or LearnedOperationStore()
        self._learned_polling_store = (
            learned_polling_store or LearnedPollingOperationStore()
        )
        self._learned_action_store = learned_action_store or LearnedActionStore()
        self._topology_builder = topology_builder
        self._protocol_factories = tuple(protocol_factories)
        self._log_protocol_failures = log_protocol_failures
        self._physical: PhysicalDevice | None = None
        self._binding: _LearnedDpiBinding | None = None
        self._protocol_backend: HardwareBackend | None = None
        self._learned_operation: LearnedOperation | None = None
        self._learned_write_node: DeviceNode | None = None
        self._learned_polling_operation: LearnedPollingOperation | None = None
        self._learned_polling_node: DeviceNode | None = None
        self._learned_action_trigger: LearnedActionTrigger | None = None
        self._learned_action_node: DeviceNode | None = None
        self._learned_adapter: LearnedHidAdapter | None = None
        self._learned_session_factory = learned_session_factory
        self._learned_sessions: dict[Path, LearnedHidSession] = {}
        self._learned_session_lock = threading.RLock()
        self._last_dpi: int | None = None
        self._last_polling_rate: int | None = None

    @property
    def name(self) -> str:
        if self._protocol_backend is not None:
            return f"Automatic Discovery ({self._protocol_backend.name} adapter)"
        if (
            self._learned_operation is not None
            or self._learned_polling_operation is not None
        ):
            return "Automatic Discovery (PROVEN learned exact-model adapter)"
        return "Automatic Discovery"

    @property
    def protocol_adapter_name(self) -> str | None:
        """Human-readable proven protocol adapter, if one was bound."""
        return self._protocol_backend.name if self._protocol_backend is not None else None

    @property
    def has_proven_learned_adapter(self) -> bool:
        return (
            self._learned_operation is not None
            or self._learned_polling_operation is not None
        )

    def _run_passive_discovery(self, device: MouseDevice) -> PhysicalDevice | None:
        """Run read-only Discovery; failure must not disable evdev remapping."""
        try:
            from ..discovery_engine import DiscoveryEngine

            engine = DiscoveryEngine(
                topology_builder=self._topology_builder,
                detectors=(),
                save_profiles=False,
            )
            return engine.discover(device).device
        except Exception:
            return None

    def _bind_protocol_adapter(self, device: MouseDevice) -> None:
        """Bind the first ordered, proven protocol implementation internally."""
        self._protocol_backend = None
        for factory in self._protocol_factories:
            backend: HardwareBackend | None = None
            try:
                backend = factory()
                if backend.supports_device(device):
                    self._protocol_backend = backend
                    return
            except (HardwareError, OSError) as exc:
                if self._log_protocol_failures:
                    LOG.warning("Hardware protocol adapter discovery failed: %s", exc)
            if backend is not None:
                backend.close()

    def _profiles(self) -> tuple[dict[str, Any], ...]:
        if not self.profile_directory.is_dir():
            return ()
        profiles: list[dict[str, Any]] = []
        for path in sorted(self.profile_directory.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    continue
                validate_calibrated_profile(raw)
            except (OSError, json.JSONDecodeError, CalibratedProfileError):
                continue
            profiles.append(raw)
        return tuple(profiles)

    @staticmethod
    def _profile_matches(profile: Mapping[str, Any], physical: PhysicalDevice) -> bool:
        identity = profile.get("identity")
        fingerprints = profile.get("fingerprints")
        if not isinstance(identity, Mapping) or not isinstance(fingerprints, Mapping):
            return False
        if fingerprints.get("model") != physical.model_fingerprint:
            return False
        for key, value in (
            ("vendor_id", physical.vendor_id),
            ("product_id", physical.product_id),
            ("bus", physical.bus),
        ):
            expected = identity.get(key)
            if expected is not None and value is not None and expected != value:
                return False
        instance = fingerprints.get("instance")
        if instance and physical.instance_fingerprint and instance != physical.instance_fingerprint:
            return False
        return True

    @staticmethod
    def _node_matches(node: DeviceNode, report: Mapping[str, Any]) -> bool:
        return all(
            current == expected
            for current, expected in (
                (node.bus, report.get("bus")),
                (node.vendor_id, report.get("vendor_id")),
                (node.product_id, report.get("product_id")),
                (node.interface_number, report.get("interface_number")),
                (node.descriptor_sha256, report.get("descriptor_sha256")),
            )
        )

    def _binding_from_profile(
        self,
        profile: Mapping[str, Any],
        physical: PhysicalDevice,
    ) -> _LearnedDpiBinding | None:
        mappings = profile.get("raw_mappings")
        if not isinstance(mappings, list):
            return None

        candidates: list[_LearnedDpiBinding] = []
        for mapping in mappings:
            if not isinstance(mapping, Mapping) or mapping.get("write_authorized") is not False:
                continue
            report = mapping.get("report")
            lookup = mapping.get("raw_to_configured_dpi")
            if not isinstance(report, Mapping) or not isinstance(lookup, Mapping):
                continue
            if report.get("report_type") != "input":
                continue

            nodes = [node for node in physical.hidraw_nodes if self._node_matches(node, report)]
            if len(nodes) != 1:
                continue
            try:
                raw_to_dpi = {int(raw): int(dpi) for raw, dpi in lookup.items()}
                report_length = int(report["report_length"])
                report_id = int(report["report_id"])
                offset = int(mapping["offset"])
            except (KeyError, TypeError, ValueError):
                continue
            if not raw_to_dpi or report_length <= 0 or offset < 0 or offset >= report_length:
                continue
            candidates.append(
                _LearnedDpiBinding(
                    physical=physical,
                    node=nodes[0],
                    report_length=report_length,
                    report_id=report_id,
                    offset=offset,
                    raw_to_dpi=raw_to_dpi,
                )
            )

        # Multiple independent state-bearing fields are not guessed between.
        return candidates[0] if len(candidates) == 1 else None

    def _session_for_node(self, node: DeviceNode) -> LearnedHidSession:
        path = Path(node.path)
        with self._learned_session_lock:
            session = self._learned_sessions.get(path)
            if session is not None and not session.closed:
                return session
            if session is not None:
                session.close()
                self._learned_sessions.pop(path, None)
            try:
                session = self._learned_session_factory(path)
            except OSError as exc:
                raise HardwareError(
                    f"Automatic Discovery: could not open learned HID transport: {exc}"
                ) from exc
            self._learned_sessions[path] = session
            return session

    def _drop_learned_sessions(self) -> None:
        with self._learned_session_lock:
            sessions = tuple(self._learned_sessions.values())
            self._learned_sessions.clear()
        for session in sessions:
            session.close()

    def _reset_learned_runtime(self) -> None:
        self._drop_learned_adapter()
        self._drop_learned_sessions()

    def _binding_shares_writable_interface(self) -> bool:
        binding = self._binding
        if binding is None:
            return False
        path = Path(binding.node.path)
        return any(
            candidate is not None and Path(candidate.path) == path
            for candidate in (
                self._learned_write_node,
                self._learned_polling_node,
            )
        )

    def _learned_event_stream_is_disjoint(self) -> bool:
        """Refuse shared event/reply routing when report identity can overlap."""

        binding = self._binding
        if binding is None:
            return False
        patterns = []
        if (
            self._learned_operation is not None
            and self._learned_write_node is not None
            and Path(self._learned_write_node.path) == Path(binding.node.path)
        ):
            patterns.extend(
                (
                    self._learned_operation.write_reply,
                    self._learned_operation.read_reply,
                )
            )
        if (
            self._learned_polling_operation is not None
            and self._learned_polling_node is not None
            and Path(self._learned_polling_node.path) == Path(binding.node.path)
        ):
            operation = self._learned_polling_operation
            patterns.append(operation.control_query_response)
            patterns.extend(step.response for step in operation.onboard_steps)
            patterns.extend(step.response for step in operation.host_steps)

        for pattern in patterns:
            values = pattern.bytes_
            if len(values) != binding.report_length:
                continue
            first = values[0] if values else None
            if (
                binding.report_id == 0
                or first is None
                or int(first) == binding.report_id
            ):
                return False
        return True

    def supports_device(self, device: MouseDevice) -> bool:
        if self._protocol_backend is not None:
            self._protocol_backend.close()
        self._reset_learned_runtime()
        self._physical = self._run_passive_discovery(device)
        self._binding = None
        self._learned_operation = None
        self._learned_write_node = None
        self._learned_polling_operation = None
        self._learned_polling_node = None
        self._learned_action_trigger = None
        self._learned_action_node = None
        self._last_dpi = None
        self._last_polling_rate = None

        if self._physical is not None and not self._physical.ambiguous:
            matches = [
                profile
                for profile in self._profiles()
                if self._profile_matches(profile, self._physical)
            ]
            if len(matches) == 1:
                self._binding = self._binding_from_profile(matches[0], self._physical)

            learned = self._learned_operation_store.find_for_physical(
                self._physical,
                proven_only=True,
            )
            if learned is not None:
                _path, operation = learned
                try:
                    node = matching_interface_node(operation, self._physical)
                except LearnedOperationError:
                    pass
                else:
                    self._learned_operation = operation
                    self._learned_write_node = node

            learned_polling = self._learned_polling_store.find_for_physical(
                self._physical,
                proven_only=True,
            )
            if learned_polling is not None:
                _path, polling_operation = learned_polling
                try:
                    polling_node = matching_interface_node(
                        polling_operation,
                        self._physical,
                    )
                except LearnedOperationError:
                    pass
                else:
                    self._learned_polling_operation = polling_operation
                    self._learned_polling_node = polling_node

            learned_action = self._learned_action_store.find_for_physical(
                self._physical,
                behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
            )
            if learned_action is not None and self._learned_operation is not None:
                _path, action_trigger = learned_action
                try:
                    action_node = matching_interface_node(
                        action_trigger,
                        self._physical,
                    )
                except LearnedOperationError:
                    pass
                else:
                    # Initial production scope: the read-only trigger must be
                    # observed on the same exact interface as the independently
                    # PROVEN DPI writer. This guarantees one-reader ownership.
                    if (
                        self._learned_write_node is not None
                        and Path(action_node.path)
                        == Path(self._learned_write_node.path)
                    ):
                        self._learned_action_trigger = action_trigger
                        self._learned_action_node = action_node

        # Proven vendor/protocol support is still an optional internal adapter.
        # A PROVEN learned operation is an independent exact-model adapter.
        self._bind_protocol_adapter(device)
        return True

    def get_device_name(self, device: MouseDevice) -> str | None:
        if self._protocol_backend is not None:
            return self._protocol_backend.get_device_name(device)
        return self._physical.name if self._physical is not None else device.name

    def _learned_dpi_capabilities(self) -> DpiCapabilities:
        values: set[int] = set()
        readable = False
        events = False
        if self._binding is not None:
            values.update(self._binding.raw_to_dpi.values())
            readable = True
            events = True
        if self._learned_operation is not None:
            values.update(self._learned_operation.demonstrated_values)
            readable = True
        if not readable:
            return DpiCapabilities()
        return DpiCapabilities(
            readable=True,
            writable=self._learned_operation is not None,
            values=tuple(sorted(values)) or None,
            stage_count=len(values) if values else None,
            stage_values_readable=self._binding is not None,
            active_stage_readable=False,
            events=events,
        )

    def _learned_polling_capabilities(self) -> ReportRateCapabilities:
        operation = self._learned_polling_operation
        if operation is None:
            return ReportRateCapabilities()
        return ReportRateCapabilities(
            readable=True,
            writable=True,
            values=tuple(sorted(operation.demonstrated_rates)),
        )

    @staticmethod
    def _merge_dpi_capabilities(proven: DpiCapabilities, learned: DpiCapabilities) -> DpiCapabilities:
        if not learned.readable:
            return proven
        values = tuple(sorted(set((proven.values or ()) + (learned.values or ())))) or None
        return DpiCapabilities(
            readable=proven.readable or learned.readable,
            writable=proven.writable or learned.writable,
            values=values,
            ranges=proven.ranges,
            independent_axes=proven.independent_axes,
            stage_count=proven.stage_count or learned.stage_count,
            stage_values_readable=proven.stage_values_readable or learned.stage_values_readable,
            stage_values_writable=proven.stage_values_writable,
            active_stage_readable=proven.active_stage_readable,
            active_stage_writable=proven.active_stage_writable,
            persistent=proven.persistent,
            events=proven.events or learned.events,
        )

    def get_capabilities(self, device: MouseDevice) -> HardwareCapabilities:
        learned_dpi = self._learned_dpi_capabilities()
        learned_polling = self._learned_polling_capabilities()
        if self._protocol_backend is None:
            return HardwareCapabilities(
                dpi=learned_dpi,
                report_rate=learned_polling,
            )
        proven = self._protocol_backend.get_capabilities(device)
        report_rate = (
            proven.report_rate
            if (
                proven.report_rate.readable
                or proven.report_rate.writable
                or proven.report_rate.values
            )
            else learned_polling
        )
        return HardwareCapabilities(
            dpi=self._merge_dpi_capabilities(proven.dpi, learned_dpi),
            report_rate=report_rate,
            battery=proven.battery,
        )

    def supports_battery(self, device: MouseDevice) -> bool:
        return bool(self._protocol_backend and self._protocol_backend.supports_battery(device))

    def get_battery_state(self, device: MouseDevice):
        if self._protocol_backend is None:
            return None
        return self._protocol_backend.get_battery_state(device)

    def supports_dpi(self, device: MouseDevice) -> bool:
        # Historical contract: this means a proven writable DPI control path.
        return self._learned_operation is not None or bool(
            self._protocol_backend and self._protocol_backend.supports_dpi(device)
        )

    def supports_dpi_monitoring(self, device: MouseDevice) -> bool:
        return self._learned_operation is not None or bool(
            self._protocol_backend and self._protocol_backend.supports_dpi_monitoring(device)
        )

    @staticmethod
    def _patterns_overlap(left, right) -> bool:
        if len(left.bytes_) != len(right.bytes_):
            return False
        return all(
            a is None or b is None or int(a) == int(b)
            for a, b in zip(left.bytes_, right.bytes_)
        )

    def _learned_action_is_disjoint(self) -> bool:
        trigger = self._learned_action_trigger
        node = self._learned_action_node
        if trigger is None or node is None:
            return False
        patterns = []
        if (
            self._learned_operation is not None
            and self._learned_write_node is not None
            and Path(self._learned_write_node.path) == Path(node.path)
        ):
            patterns.extend(
                (
                    self._learned_operation.write_reply,
                    self._learned_operation.read_reply,
                )
            )
        if (
            self._learned_polling_operation is not None
            and self._learned_polling_node is not None
            and Path(self._learned_polling_node.path) == Path(node.path)
        ):
            operation = self._learned_polling_operation
            patterns.append(operation.control_query_response)
            patterns.extend(step.response for step in operation.onboard_steps)
            patterns.extend(step.response for step in operation.host_steps)
        return all(
            not self._patterns_overlap(trigger.press_pattern, pattern)
            and not self._patterns_overlap(trigger.release_pattern, pattern)
            for pattern in patterns
        )

    def supports_dpi_cycle_trigger(self, device: MouseDevice) -> bool:
        return (
            self._learned_operation is not None
            and self._learned_action_trigger is not None
            and self._learned_action_node is not None
            and self._learned_action_is_disjoint()
        )

    def supports_dpi_events(self, device: MouseDevice) -> bool:
        if (
            self._protocol_backend is not None
            and self._protocol_backend.supports_dpi_events(device)
        ):
            return True
        if self.supports_dpi_cycle_trigger(device):
            return True
        if self._binding is None:
            return False
        if not self._binding_shares_writable_interface():
            return True
        return self._learned_event_stream_is_disjoint()

    def _bound_learned_adapter(self) -> LearnedHidAdapter:
        if self._learned_operation is None or self._learned_write_node is None:
            raise HardwareError("Automatic Discovery: no PROVEN learned DPI adapter")
        if self._learned_adapter is None or self._learned_adapter.closed:
            try:
                self._learned_adapter = LearnedHidAdapter(
                    self._learned_write_node.path,
                    self._learned_operation,
                    session=self._session_for_node(self._learned_write_node),
                )
            except OSError as exc:
                raise HardwareError(
                    f"Automatic Discovery: could not open learned DPI transport: {exc}"
                ) from exc
        return self._learned_adapter

    def _drop_learned_adapter(self) -> None:
        if self._learned_adapter is not None:
            self._learned_adapter.close()
            self._learned_adapter = None

    def get_dpi_state(self, device: MouseDevice) -> DpiState | None:
        if self._protocol_backend and self._protocol_backend.supports_dpi_monitoring(device):
            return self._protocol_backend.get_dpi_state(device)
        if self._learned_operation is not None and self._learned_write_node is not None:
            context = TransactionContext()
            try:
                TransactionEngine().run(
                    learned_dpi_read_spec(),
                    self._bound_learned_adapter(),
                    authorization=TransactionAuthorization(
                        active_queries=True,
                        reason="PROVEN exact-model learned DPI readback",
                    ),
                    context=context,
                )
                value = int(context.values["raw_readback"])
            except (OSError, LearnedOperationError, TransactionError) as exc:
                self._reset_learned_runtime()
                if self._last_dpi is None:
                    raise HardwareError(
                        f"Automatic Discovery learned DPI read failed: {exc}"
                    ) from exc
            else:
                self._last_dpi = value
        if self._last_dpi is None:
            return None
        return DpiState(self._last_dpi, self._last_dpi, active_stage=None, confirmed=True)

    def get_dpi(self, device: MouseDevice) -> int | tuple[int, int] | None:
        # Preserve the exact public return contract of an already-proven
        # protocol adapter (including independent/equal X/Y tuples). Learned
        # execution is only used when no native/vendor adapter is bound.
        if self._protocol_backend is not None:
            return self._protocol_backend.get_dpi(device)
        state = self.get_dpi_state(device)
        return state.display_value if state is not None else None

    def get_dpi_values(self, device: MouseDevice) -> list[int]:
        values = set(self._binding.raw_to_dpi.values()) if self._binding is not None else set()
        if self._learned_operation is not None:
            values.update(self._learned_operation.demonstrated_values)
        if self._protocol_backend is not None:
            values.update(self._protocol_backend.get_dpi_values(device))
        return sorted(values)

    def set_dpi(self, device: MouseDevice, dpi: int) -> DpiState | None:
        if (
            self._protocol_backend is not None
            and self._protocol_backend.get_capabilities(device).dpi.writable
        ):
            return self._protocol_backend.set_dpi(device, dpi)

        if self._learned_operation is None or self._learned_write_node is None:
            raise HardwareError("Automatic Discovery: no proven writable DPI adapter")
        context = TransactionContext(values={"target": int(dpi)})
        try:
            context = TransactionEngine().run(
                learned_dpi_transaction_spec(),
                self._bound_learned_adapter(),
                authorization=TransactionAuthorization(
                    reversible_writes=True,
                    reason="PROVEN exact-model learned DPI operation",
                ),
                context=context,
            )
        except (OSError, LearnedOperationError, TransactionError) as exc:
            self._reset_learned_runtime()
            raise HardwareError(
                f"Automatic Discovery learned DPI write failed: {exc}"
            ) from exc
        self._last_dpi = int(context.values["raw_readback"])
        return DpiState(
            self._last_dpi,
            self._last_dpi,
            active_stage=None,
            confirmed=True,
        )

    def supports_dpi_stages(self, device: MouseDevice) -> bool:
        return bool(self._protocol_backend and self._protocol_backend.supports_dpi_stages(device))

    def apply_dpi_stages(self, device: MouseDevice, stages: list[int], active_dpi: int) -> int | None:
        if self._protocol_backend is None:
            return None
        return self._protocol_backend.apply_dpi_stages(device, stages, active_dpi)

    def supports_polling_rate(self, device: MouseDevice) -> bool:
        if (
            self._protocol_backend is not None
            and self._protocol_backend.supports_polling_rate(device)
        ):
            return True
        return self._learned_polling_operation is not None

    def supports_polling_rate_writes(self, device: MouseDevice) -> bool:
        if (
            self._protocol_backend is not None
            and self._protocol_backend.supports_polling_rate(device)
        ):
            return self._protocol_backend.supports_polling_rate_writes(device)
        return self._learned_polling_operation is not None

    def supports_polling_rate_writes_without_takeover(self, device: MouseDevice) -> bool:
        if (
            self._protocol_backend is not None
            and self._protocol_backend.supports_polling_rate(device)
        ):
            return self._protocol_backend.supports_polling_rate_writes_without_takeover(
                device
            )
        if (
            self._learned_polling_operation is None
            or self._learned_polling_node is None
        ):
            return False
        try:
            return learned_polling_write_without_takeover(
                self._learned_polling_operation,
                self._session_for_node(self._learned_polling_node),
            )
        except (LearnedPollingTransportError, OSError):
            self._reset_learned_runtime()
            return False

    def get_polling_rate(self, device: MouseDevice) -> int | None:
        if (
            self._protocol_backend is not None
            and self._protocol_backend.supports_polling_rate(device)
        ):
            return self._protocol_backend.get_polling_rate(device)
        if (
            self._learned_polling_operation is None
            or self._learned_polling_node is None
        ):
            return None
        try:
            value = read_learned_polling_rate(
                self._learned_polling_operation,
                self._session_for_node(self._learned_polling_node),
            )
        except (LearnedPollingTransportError, OSError) as exc:
            self._reset_learned_runtime()
            raise HardwareError(
                f"Automatic Discovery learned polling read failed: {exc}"
            ) from exc
        self._last_polling_rate = value
        return value

    def get_polling_rates(self, device: MouseDevice) -> list[int]:
        if (
            self._protocol_backend is not None
            and self._protocol_backend.supports_polling_rate(device)
        ):
            return self._protocol_backend.get_polling_rates(device)
        if self._learned_polling_operation is None:
            return []
        return sorted(self._learned_polling_operation.demonstrated_rates)

    def set_polling_rate(self, device: MouseDevice, hz: int) -> None:
        if (
            self._protocol_backend is not None
            and self._protocol_backend.supports_polling_rate(device)
        ):
            if not self._protocol_backend.supports_polling_rate_writes(device):
                raise HardwareError(
                    "Automatic Discovery: proven protocol adapter does not allow "
                    "polling-rate writes"
                )
            self._protocol_backend.set_polling_rate(device, hz)
            return
        if (
            self._learned_polling_operation is None
            or self._learned_polling_node is None
        ):
            raise HardwareError(
                "Automatic Discovery: no proven writable polling-rate adapter"
            )
        try:
            value = execute_learned_polling(
                self._learned_polling_operation,
                self._session_for_node(self._learned_polling_node),
                int(hz),
            )
        except (LearnedPollingTransportError, OSError) as exc:
            self._reset_learned_runtime()
            raise HardwareError(
                f"Automatic Discovery learned polling write failed: {exc}"
            ) from exc
        self._last_polling_rate = value

    def _decode_report(self, data: bytes) -> int | None:
        binding = self._binding
        if binding is None or len(data) != binding.report_length:
            return None
        if binding.report_id and (not data or data[0] != binding.report_id):
            return None
        raw = data[binding.offset]
        return binding.raw_to_dpi.get(raw)

    def _watch_session_events(
        self,
        *,
        session: LearnedHidSession,
        decode_packet: Callable[[bytes], DpiState | None],
        callback: Callable[[DpiState], None],
        shutdown_event: threading.Event,
        ready_callback: Callable[[], None] | None,
        label: str,
    ) -> None:
        """Dispatch learned HID events off the single reader thread.

        LearnedHidSession subscribers run on its reader thread. They must never
        synchronously call a path that can re-enter ``session.exchange()``.
        Decode on the reader thread, enqueue the semantic event, and invoke the
        runtime callback from this watcher thread instead.
        """
        pending: queue.Queue[DpiState] = queue.Queue()

        def handle(packet: bytes) -> None:
            state = decode_packet(packet)
            if state is not None:
                pending.put(state)

        try:
            unsubscribe = session.subscribe(handle)
        except LearnedHidSessionError as exc:
            raise HardwareError(
                f"Automatic Discovery: could not subscribe {label}: {exc}"
            ) from exc

        try:
            if ready_callback is not None:
                ready_callback()
            while not shutdown_event.is_set():
                if session.closed:
                    detail = session.disconnect_error
                    raise HardwareError(
                        f"Automatic Discovery: {label} session disconnected"
                        + (f": {detail}" if detail is not None else "")
                    )
                try:
                    state = pending.get(timeout=0.05)
                except queue.Empty:
                    continue
                callback(state)
        finally:
            unsubscribe()

    def _watch_learned_cycle_trigger(
        self,
        callback: Callable[[DpiState], None],
        shutdown_event: threading.Event,
        ready_callback: Callable[[], None] | None,
    ) -> None:
        trigger = self._learned_action_trigger
        node = self._learned_action_node
        if (
            trigger is None
            or node is None
            or not self._learned_action_is_disjoint()
        ):
            raise HardwareError(
                "Automatic Discovery: no unambiguous learned DPI-cycle trigger"
            )
        try:
            session = self._session_for_node(node)
        except OSError as exc:
            raise HardwareError(
                f"Automatic Discovery: could not open learned action trigger: {exc}"
            ) from exc

        pressed = False

        def decode(packet: bytes) -> DpiState | None:
            nonlocal pressed
            if trigger.matches_press(packet):
                if pressed:
                    return None
                pressed = True
                return DpiState(
                    0,
                    0,
                    confirmed=True,
                    cycle_trigger=True,
                )
            if trigger.matches_release(packet):
                pressed = False
            return None

        self._watch_session_events(
            session=session,
            decode_packet=decode,
            callback=callback,
            shutdown_event=shutdown_event,
            ready_callback=ready_callback,
            label="learned DPI-cycle trigger",
        )

    def _watch_shared_learned_dpi_events(
        self,
        callback: Callable[[DpiState], None],
        shutdown_event: threading.Event,
        ready_callback: Callable[[], None] | None,
    ) -> None:
        binding = self._binding
        if binding is None:
            raise HardwareError(
                "Automatic Discovery: no calibrated DPI event mapping is available"
            )
        if not self._learned_event_stream_is_disjoint():
            raise HardwareError(
                "Automatic Discovery: learned event/reply packet identities overlap; "
                "refusing ambiguous shared routing"
            )
        try:
            session = self._session_for_node(binding.node)
        except OSError as exc:
            raise HardwareError(
                f"Automatic Discovery: could not open learned HID events: {exc}"
            ) from exc

        def decode(packet: bytes) -> DpiState | None:
            dpi = self._decode_report(packet)
            if dpi is None or dpi == self._last_dpi:
                return None
            self._last_dpi = dpi
            return DpiState(
                dpi,
                dpi,
                active_stage=None,
                confirmed=True,
            )

        self._watch_session_events(
            session=session,
            decode_packet=decode,
            callback=callback,
            shutdown_event=shutdown_event,
            ready_callback=ready_callback,
            label="learned DPI event",
        )

    def _watch_learned_dpi_events(
        self,
        callback: Callable[[DpiState], None],
        shutdown_event: threading.Event,
        ready_callback: Callable[[], None] | None,
    ) -> None:
        binding = self._binding
        if binding is None:
            raise HardwareError("Automatic Discovery: no calibrated DPI event mapping is available")
        if self._binding_shares_writable_interface():
            self._watch_shared_learned_dpi_events(
                callback,
                shutdown_event,
                ready_callback,
            )
            return

        try:
            fd = os.open(os.fspath(binding.node.path), os.O_RDONLY | os.O_NONBLOCK)
        except OSError as exc:
            raise HardwareError(
                f"Automatic Discovery: could not open learned hidraw interface: {exc}"
            ) from exc

        try:
            if ready_callback is not None:
                ready_callback()
            while not shutdown_event.is_set():
                try:
                    readable, _, _ = select.select([fd], [], [], 0.25)
                except OSError as exc:
                    raise HardwareError(f"Automatic Discovery: hidraw watcher failed: {exc}") from exc
                if not readable:
                    continue
                try:
                    data = os.read(fd, max(4096, binding.report_length))
                except BlockingIOError:
                    continue
                except OSError as exc:
                    raise HardwareError(f"Automatic Discovery: hidraw read failed: {exc}") from exc
                if not data:
                    raise HardwareError("Automatic Discovery: learned hidraw interface disconnected")
                dpi = self._decode_report(data)
                if dpi is None or dpi == self._last_dpi:
                    continue
                self._last_dpi = dpi
                # Learned evidence remains read-only; never provide an active
                # writable stage index to the software DPI cycler.
                callback(DpiState(dpi, dpi, active_stage=None, confirmed=True))
        finally:
            os.close(fd)

    def watch_dpi_events(
        self,
        device: MouseDevice,
        callback: Callable[[DpiState], None],
        shutdown_event: threading.Event,
        ready_callback: Callable[[], None] | None = None,
    ) -> None:
        if self._protocol_backend and self._protocol_backend.supports_dpi_events(device):
            self._protocol_backend.watch_dpi_events(
                device, callback, shutdown_event, ready_callback
            )
            return
        if self.supports_dpi_cycle_trigger(device):
            self._watch_learned_cycle_trigger(
                callback,
                shutdown_event,
                ready_callback,
            )
            return
        self._watch_learned_dpi_events(callback, shutdown_event, ready_callback)

    def close(self) -> None:
        if self._protocol_backend is not None:
            self._protocol_backend.close()
            self._protocol_backend = None
        self._reset_learned_runtime()
        self._learned_operation = None
        self._learned_write_node = None
        self._learned_polling_operation = None
        self._learned_polling_node = None
        self._learned_action_trigger = None
        self._learned_action_node = None
