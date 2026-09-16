"""Discovery-backed fallback hardware support.

This is the replacement for the old inert ``GenericBackend``.  Every device
that reaches this fallback is passed through the safety-first Discovery engine.
If physically calibrated read-side evidence has already been learned, the
backend rebinds that stable report identity to the current hidraw node and can
monitor DPI events without any vendor protocol implementation.

Unknown HID writes are never issued here.  Learned profiles are observation
authority only; write promotion remains a separate, proven-evidence process.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import select
import threading
from typing import Any, Callable, Mapping

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


@dataclass(frozen=True)
class _LearnedDpiBinding:
    physical: PhysicalDevice
    node: DeviceNode
    report_length: int
    report_id: int
    offset: int
    raw_to_dpi: Mapping[int, int]


class DiscoveryBackend(HardwareBackend):
    """Safe default backend powered by automatic hardware discovery."""

    name = "Automatic Discovery"

    def __init__(
        self,
        *,
        profile_directory: Path | None = None,
        topology_builder: Callable[[MouseDevice], PhysicalDevice] = build_device_graph,
    ) -> None:
        self.profile_directory = profile_directory or get_calibrated_profile_directory()
        self._topology_builder = topology_builder
        self._physical: PhysicalDevice | None = None
        self._binding: _LearnedDpiBinding | None = None
        self._last_dpi: int | None = None

    def _run_passive_discovery(self, device: MouseDevice) -> PhysicalDevice | None:
        """Run normal read-only Discovery; failure still leaves software remapping usable."""

        try:
            # Imported lazily so hardware registry import order stays cycle-safe.
            from ..discovery_engine import DiscoveryEngine

            engine = DiscoveryEngine(
                topology_builder=self._topology_builder,
                detectors=(),
                save_profiles=False,
            )
            return engine.discover(device).device
        except Exception:
            # This is the final hardware fallback.  Missing hidraw permissions or
            # incomplete topology must not disable evdev/uinput remapping.
            return None

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
        # DiscoveryBackend is the final safe fallback even when no learned
        # hardware capability is available; evdev remapping remains usable.
        return True

    def get_device_name(self, device: MouseDevice) -> str | None:
        return self._physical.name if self._physical is not None else device.name

    def get_capabilities(self, device: MouseDevice) -> HardwareCapabilities:
        if self._binding is None:
            return HardwareCapabilities()
        values = tuple(sorted(set(self._binding.raw_to_dpi.values())))
        return HardwareCapabilities(
            dpi=DpiCapabilities(
                readable=True,
                writable=False,
                values=values,
                stage_count=len(values),
                stage_values_readable=True,
                active_stage_readable=False,
                events=True,
            )
        )

    def supports_dpi(self, device: MouseDevice) -> bool:
        return self._binding is not None

    def supports_dpi_monitoring(self, device: MouseDevice) -> bool:
        # The learned path is event-driven; it does not pretend to have a
        # vendor-defined synchronous GET-DPI transaction.
        return False

    def supports_dpi_events(self, device: MouseDevice) -> bool:
        return self._binding is not None

    def get_dpi(self, device: MouseDevice) -> int | None:
        return self._last_dpi

    def get_dpi_values(self, device: MouseDevice) -> list[int]:
        if self._binding is None:
            return []
        return sorted(set(self._binding.raw_to_dpi.values()))

    def _decode_report(self, data: bytes) -> int | None:
        binding = self._binding
        if binding is None or len(data) != binding.report_length:
            return None
        if binding.report_id and (not data or data[0] != binding.report_id):
            return None
        raw = data[binding.offset]
        return binding.raw_to_dpi.get(raw)

    def watch_dpi_events(
        self,
        device: MouseDevice,
        callback: Callable[[DpiState], None],
        shutdown_event: threading.Event,
        ready_callback: Callable[[], None] | None = None,
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
                # active_stage intentionally stays None.  Existing native
                # backends use active_stage to drive writable software cycling;
                # calibrated Discovery has read authority only.
                callback(DpiState(dpi, dpi, active_stage=None, confirmed=True))
        finally:
            os.close(fd)
