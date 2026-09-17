"""Single owner for a device's optional hardware-control lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import threading
from collections.abc import Callable

from ..discovery import MouseDevice
from .base import HardwareBackend, HardwareError
from .capabilities import BatteryState, DpiState, HardwareCapabilities
from .discovery_backend import DiscoveryBackend

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class DesiredHardwareState:
    """Safe runtime state reapplied at startup and after every rebind."""

    active_dpi: int = 0
    dpi_stages: tuple[int, ...] = ()
    polling_rate_hz: int | None = None


class HardwareSupervisor(HardwareBackend):
    """Stable backend reference shared by every hardware consumer.

    The supervisor does not poll. A consumer that observes a disconnect asks
    it to rebind; generation checks prevent two consumers from replacing the
    same failed backend twice.
    """

    def __init__(self, backend: HardwareBackend, device: MouseDevice,
                 backend_factory: Callable[[MouseDevice], HardwareBackend],
                 desired: DesiredHardwareState = DesiredHardwareState(),
                 device_resolver: Callable[[MouseDevice], MouseDevice] | None = None,
                 discovery_pending: bool = False) -> None:
        self.device = device
        self._backend = backend
        self._backend_factory = backend_factory
        self.desired = desired
        self._device_resolver = device_resolver or (lambda selected: selected)
        self._has_preferred_backend = self._backend_has_proven_adapter(backend)
        self._discovery_pending = bool(discovery_pending and not self._has_preferred_backend)
        self._lock = threading.RLock()
        self._generation = 0
        self._closed = False

    @staticmethod
    def _backend_has_proven_adapter(backend: HardwareBackend) -> bool:
        if isinstance(backend, DiscoveryBackend):
            return (
                backend.protocol_adapter_name is not None
                or backend.has_proven_learned_adapter
            )
        return True

    @staticmethod
    def _discovery_binding_signature(backend: HardwareBackend):
        """Stable-enough signature for deciding whether a Discovery rebind matters.

        The signature deliberately includes current node paths as well as stable
        identity. A reconnect that moves to another hidraw node must therefore
        replace the live backend even when the learned grammar is unchanged.
        Two completely empty Discovery objects remain equivalent and can be
        collapsed while hotplug enumeration is still settling.
        """
        if not isinstance(backend, DiscoveryBackend):
            return None
        physical = backend._physical
        binding = backend._binding
        nodes = ()
        physical_identity = None
        if physical is not None:
            physical_identity = (
                physical.vendor_id,
                physical.product_id,
                physical.bus,
                physical.model_fingerprint,
                physical.instance_fingerprint,
                physical.ambiguous,
            )
            nodes = tuple(sorted(
                (
                    str(node.path),
                    node.subsystem,
                    node.node_type,
                    node.bus,
                    node.vendor_id,
                    node.product_id,
                    node.interface_number,
                    node.descriptor_sha256,
                )
                for node in physical.all_nodes
            ))
        learned = None
        if binding is not None:
            learned = (
                str(binding.node.path),
                binding.report_length,
                binding.report_id,
                binding.offset,
                tuple(sorted(binding.raw_to_dpi.items())),
                binding.kind,
                binding.cycle_order,
                binding.event_type,
                binding.code,
                binding.press_value,
                binding.release_value,
                binding.press_pattern,
                binding.release_pattern,
            )
        learned_writers = (
            (
                str(backend._learned_write_node.path)
                if backend._learned_write_node is not None
                else None
            ),
            (
                str(backend._learned_polling_node.path)
                if backend._learned_polling_node is not None
                else None
            ),
        )
        return (
            backend.protocol_adapter_name,
            physical_identity,
            nodes,
            learned,
            learned_writers,
        )

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def current_backend(self) -> HardwareBackend:
        with self._lock:
            return self._backend

    @property
    def discovery_pending(self) -> bool:
        with self._lock:
            return self._discovery_pending

    @property
    def name(self) -> str:
        with self._lock:
            return self._backend.name

    def supports_device(self, device: MouseDevice) -> bool:
        return self._call("supports_device", device)

    def _call(self, method: str, *args):
        with self._lock:
            if self._closed:
                raise HardwareError("hardware supervisor is closed")
            if args and isinstance(args[0], MouseDevice):
                args = (self.device, *args[1:])
            return getattr(self._backend, method)(*args)

    @staticmethod
    def _dpi_matches(actual, expected: int) -> bool:
        if isinstance(actual, tuple):
            return actual[0] == expected and actual[1] in (0, expected)
        return actual == expected

    def _reconcile_backend(self, backend: HardwareBackend,
                           device: MouseDevice | None = None) -> None:
        desired = self.desired
        device = device or self.device
        if desired.polling_rate_hz is not None:
            try:
                if backend.supports_polling_rate_writes_without_takeover(device):
                    backend.set_polling_rate(device, desired.polling_rate_hz)
                    actual = backend.get_polling_rate(device)
                    if actual != desired.polling_rate_hz:
                        raise HardwareError(
                            f"polling verification requested {desired.polling_rate_hz} Hz, "
                            f"read {actual} Hz")
                    LOG.info("Reconciled hardware polling rate to %s Hz through %s",
                             actual, backend.name)
                elif backend.supports_polling_rate(device):
                    LOG.info(
                        "Preserved native control mode; skipped automatic polling write through %s",
                        backend.name,
                    )
            except Exception as exc:
                LOG.warning("Could not reconcile %s polling state: %s", backend.name, exc)

        try:
            if desired.dpi_stages and backend.supports_dpi_stages(device):
                backend.apply_dpi_stages(
                    device, list(desired.dpi_stages), desired.active_dpi)
            if desired.active_dpi > 0 and backend.supports_dpi(device):
                backend.set_dpi(device, desired.active_dpi)
                actual = backend.get_dpi(device)
                if not self._dpi_matches(actual, desired.active_dpi):
                    raise HardwareError(
                        f"DPI verification requested {desired.active_dpi}, read {actual}")
                LOG.info("Reconciled hardware DPI to %s through %s", actual, backend.name)
        except Exception as exc:
            LOG.warning("Could not reconcile %s DPI state: %s", backend.name, exc)

    def reconcile(self) -> None:
        with self._lock:
            if not self._closed:
                self._reconcile_backend(self._backend)

    def record_active_dpi(self, dpi: int | tuple[int, int]) -> None:
        value = dpi[0] if isinstance(dpi, tuple) else dpi
        if value <= 0:
            return
        with self._lock:
            if not self._closed:
                self.desired = replace(self.desired, active_dpi=value)

    def rebind(self, expected_generation: int | None = None) -> bool:
        with self._lock:
            if self._closed:
                return False
            if (expected_generation is not None and
                    expected_generation != self._generation):
                return False
            old = self._backend
            replacement = None
            try:
                resolved_device = self._device_resolver(self.device)
                replacement = self._backend_factory(resolved_device)
                self._reconcile_backend(replacement, resolved_device)
            except Exception:
                if replacement is not None:
                    close = getattr(replacement, "close", None)
                    if close:
                        close()
                raise

            old_signature = self._discovery_binding_signature(old)
            new_signature = self._discovery_binding_signature(replacement)
            if (old_signature is not None and new_signature is not None and
                    old_signature == new_signature):
                close = getattr(replacement, "close", None)
                if close:
                    close()
                self.device = resolved_device
                return False

            self.device = resolved_device
            self._backend = replacement
            replacement_preferred = self._backend_has_proven_adapter(replacement)
            if replacement_preferred:
                self._has_preferred_backend = True
                self._discovery_pending = False
            elif self._has_preferred_backend:
                self._discovery_pending = True
            self._generation += 1
            if old is not replacement:
                close = getattr(old, "close", None)
                if close:
                    close()
            LOG.info("Rebound hardware backend to %s (generation %d)",
                     replacement.name, self._generation)
            return True

    def get_device_name(self, device): return self._call("get_device_name", device)
    def get_capabilities(self, device) -> HardwareCapabilities: return self._call("get_capabilities", device)
    def supports_battery(self, device): return self._call("supports_battery", device)
    def get_battery_state(self, device) -> BatteryState | None: return self._call("get_battery_state", device)
    def get_dpi_state(self, device) -> DpiState | None: return self._call("get_dpi_state", device)
    def supports_dpi(self, device): return self._call("supports_dpi", device)
    def get_dpi(self, device): return self._call("get_dpi", device)
    def supports_dpi_monitoring(self, device): return self._call("supports_dpi_monitoring", device)
    def supports_dpi_events(self, device): return self._call("supports_dpi_events", device)
    def supports_dpi_cycle_trigger(self, device): return self._call("supports_dpi_cycle_trigger", device)
    def get_dpi_values(self, device): return self._call("get_dpi_values", device)
    def set_dpi(self, device, dpi): return self._call("set_dpi", device, dpi)
    def supports_dpi_stages(self, device): return self._call("supports_dpi_stages", device)
    def apply_dpi_stages(self, device, stages, active_dpi): return self._call("apply_dpi_stages", device, stages, active_dpi)
    def supports_polling_rate(self, device): return self._call("supports_polling_rate", device)
    def supports_polling_rate_writes(self, device): return self._call("supports_polling_rate_writes", device)
    def supports_polling_rate_writes_without_takeover(self, device): return self._call("supports_polling_rate_writes_without_takeover", device)
    def get_polling_rate(self, device): return self._call("get_polling_rate", device)
    def get_polling_rates(self, device): return self._call("get_polling_rates", device)
    def set_polling_rate(self, device, hz): return self._call("set_polling_rate", device, hz)

    def observe_evdev_event(self, event_type, code, value) -> None:
        with self._lock:
            if self._closed:
                return
            backend = self._backend
        observe = getattr(backend, "observe_evdev_event", None)
        if callable(observe):
            observe(event_type, code, value)

    def invalidate_observer_continuity(self) -> None:
        with self._lock:
            if self._closed:
                return
            backend = self._backend
        invalidate = getattr(backend, "invalidate_observer_continuity", None)
        if callable(invalidate):
            invalidate()

    def watch_dpi_events(self, device, callback, shutdown_event,
                         ready_callback=None) -> None:
        with self._lock:
            if self._closed:
                raise HardwareError("hardware supervisor is closed")
            backend = self._backend
            device = self.device
        backend.watch_dpi_events(device, callback, shutdown_event, ready_callback)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            close = getattr(self._backend, "close", None)
            if close:
                close()
