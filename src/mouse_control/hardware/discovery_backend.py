"""Universal mouse hardware backend powered by Automatic Discovery.

Every selected mouse is represented to the rest of Mouse Control through this
backend.  Discovery owns identity, passive evidence, learned read-side grammar,
and capability exposure.  Proven vendor/protocol implementations are internal
adapters: they may provide validated reads/writes, but callers no longer select
a vendor backend directly.

Physically learned profiles are observation authority only.  They can add
read/event capabilities, but can never authorize a HID write.  Writable
operations are delegated only to an already-proven protocol adapter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import json
import logging
import os
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
from ..discovery import MouseDevice
from ..discovery_models import DeviceNode, PhysicalDevice
from .base import HardwareBackend, HardwareError
from .capabilities import DpiCapabilities, DpiState, HardwareCapabilities

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
        topology_builder: Callable[[MouseDevice], PhysicalDevice] = build_device_graph,
        protocol_factories: Iterable[Callable[[], HardwareBackend]] = (),
        log_protocol_failures: bool = True,
    ) -> None:
        self.profile_directory = profile_directory or get_calibrated_profile_directory()
        self._topology_builder = topology_builder
        self._protocol_factories = tuple(protocol_factories)
        self._log_protocol_failures = log_protocol_failures
        self._physical: PhysicalDevice | None = None
        self._binding: _LearnedDpiBinding | None = None
        self._protocol_backend: HardwareBackend | None = None
        self._last_dpi: int | None = None

    @property
    def name(self) -> str:
        if self._protocol_backend is None:
            return "Automatic Discovery"
        return f"Automatic Discovery ({self._protocol_backend.name} adapter)"

    @property
    def protocol_adapter_name(self) -> str | None:
        """Human-readable proven protocol adapter, if one was bound."""
        return self._protocol_backend.name if self._protocol_backend is not None else None

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

    def supports_device(self, device: MouseDevice) -> bool:
        if self._protocol_backend is not None:
            self._protocol_backend.close()
        self._physical = self._run_passive_discovery(device)
        self._binding = None
        self._last_dpi = None

        if self._physical is not None and not self._physical.ambiguous:
            matches = [
                profile
                for profile in self._profiles()
                if self._profile_matches(profile, self._physical)
            ]
            if len(matches) == 1:
                self._binding = self._binding_from_profile(matches[0], self._physical)

        # Proven vendor/protocol support is an implementation detail behind the
        # universal Discovery contract, not an alternate backend visible to callers.
        self._bind_protocol_adapter(device)
        return True

    def get_device_name(self, device: MouseDevice) -> str | None:
        if self._protocol_backend is not None:
            return self._protocol_backend.get_device_name(device)
        return self._physical.name if self._physical is not None else device.name

    def _learned_dpi_capabilities(self) -> DpiCapabilities:
        if self._binding is None:
            return DpiCapabilities()
        values = tuple(sorted(set(self._binding.raw_to_dpi.values())))
        return DpiCapabilities(
            readable=True,
            writable=False,
            values=values,
            stage_count=len(values),
            stage_values_readable=True,
            active_stage_readable=False,
            events=True,
        )

    @staticmethod
    def _merge_dpi_capabilities(proven: DpiCapabilities, learned: DpiCapabilities) -> DpiCapabilities:
        if not learned.readable:
            return proven
        values = tuple(sorted(set((proven.values or ()) + (learned.values or ())))) or None
        return DpiCapabilities(
            readable=proven.readable or learned.readable,
            writable=proven.writable,
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
        if self._protocol_backend is None:
            return HardwareCapabilities(dpi=learned_dpi)
        proven = self._protocol_backend.get_capabilities(device)
        return HardwareCapabilities(
            dpi=self._merge_dpi_capabilities(proven.dpi, learned_dpi),
            report_rate=proven.report_rate,
            battery=proven.battery,
        )

    def supports_battery(self, device: MouseDevice) -> bool:
        return bool(self._protocol_backend and self._protocol_backend.supports_battery(device))

    def get_battery_state(self, device: MouseDevice):
        if self._protocol_backend is None:
            return None
        return self._protocol_backend.get_battery_state(device)

    def supports_dpi(self, device: MouseDevice) -> bool:
        return self._binding is not None or bool(
            self._protocol_backend and self._protocol_backend.supports_dpi(device)
        )

    def supports_dpi_monitoring(self, device: MouseDevice) -> bool:
        return bool(
            self._protocol_backend and self._protocol_backend.supports_dpi_monitoring(device)
        )

    def supports_dpi_events(self, device: MouseDevice) -> bool:
        return self._binding is not None or bool(
            self._protocol_backend and self._protocol_backend.supports_dpi_events(device)
        )

    def get_dpi_state(self, device: MouseDevice) -> DpiState | None:
        if self._protocol_backend and self._protocol_backend.supports_dpi_monitoring(device):
            return self._protocol_backend.get_dpi_state(device)
        if self._last_dpi is None:
            return None
        return DpiState(self._last_dpi, self._last_dpi, active_stage=None, confirmed=True)

    def get_dpi(self, device: MouseDevice) -> int | tuple[int, int] | None:
        if self._protocol_backend and self._protocol_backend.supports_dpi_monitoring(device):
            return self._protocol_backend.get_dpi(device)
        return self._last_dpi

    def get_dpi_values(self, device: MouseDevice) -> list[int]:
        values = set(self._binding.raw_to_dpi.values()) if self._binding is not None else set()
        if self._protocol_backend is not None:
            values.update(self._protocol_backend.get_dpi_values(device))
        return sorted(values)

    def set_dpi(self, device: MouseDevice, dpi: int) -> DpiState | None:
        if self._protocol_backend is None or not self._protocol_backend.get_capabilities(device).dpi.writable:
            raise HardwareError("Automatic Discovery: no proven writable DPI adapter")
        return self._protocol_backend.set_dpi(device, dpi)

    def supports_dpi_stages(self, device: MouseDevice) -> bool:
        return bool(self._protocol_backend and self._protocol_backend.supports_dpi_stages(device))

    def apply_dpi_stages(self, device: MouseDevice, stages: list[int], active_dpi: int) -> int | None:
        if self._protocol_backend is None:
            return None
        return self._protocol_backend.apply_dpi_stages(device, stages, active_dpi)

    def supports_polling_rate(self, device: MouseDevice) -> bool:
        return bool(self._protocol_backend and self._protocol_backend.supports_polling_rate(device))

    def supports_polling_rate_writes(self, device: MouseDevice) -> bool:
        return bool(
            self._protocol_backend and self._protocol_backend.supports_polling_rate_writes(device)
        )

    def supports_polling_rate_writes_without_takeover(self, device: MouseDevice) -> bool:
        return bool(
            self._protocol_backend
            and self._protocol_backend.supports_polling_rate_writes_without_takeover(device)
        )

    def get_polling_rate(self, device: MouseDevice) -> int | None:
        if self._protocol_backend is None:
            return None
        return self._protocol_backend.get_polling_rate(device)

    def get_polling_rates(self, device: MouseDevice) -> list[int]:
        if self._protocol_backend is None:
            return []
        return self._protocol_backend.get_polling_rates(device)

    def set_polling_rate(self, device: MouseDevice, hz: int) -> None:
        if self._protocol_backend is None or not self._protocol_backend.supports_polling_rate_writes(device):
            raise HardwareError("Automatic Discovery: no proven writable polling-rate adapter")
        self._protocol_backend.set_polling_rate(device, hz)

    def _decode_report(self, data: bytes) -> int | None:
        binding = self._binding
        if binding is None or len(data) != binding.report_length:
            return None
        if binding.report_id and (not data or data[0] != binding.report_id):
            return None
        raw = data[binding.offset]
        return binding.raw_to_dpi.get(raw)

    def _watch_learned_dpi_events(
        self,
        callback: Callable[[DpiState], None],
        shutdown_event: threading.Event,
        ready_callback: Callable[[], None] | None,
    ) -> None:
        binding = self._binding
        if binding is None:
            raise HardwareError("Automatic Discovery: no calibrated DPI event mapping is available")

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
        self._watch_learned_dpi_events(callback, shutdown_event, ready_callback)

    def close(self) -> None:
        if self._protocol_backend is not None:
            self._protocol_backend.close()
            self._protocol_backend = None
