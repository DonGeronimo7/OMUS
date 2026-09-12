"""Live mouse remapping using evdev input capture and a virtual uinput device."""

from __future__ import annotations

from dataclasses import dataclass
import select
import signal
import threading
from typing import Any
import logging

from evdev import InputDevice, UInput, ecodes

from .discovery import MouseDevice
from .hardware import DpiState, HardwareBackend
from .notifications import FreedesktopNotifier, Notifier


LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Action:
    kind: str
    code: int | None = None


def parse_action(value: str) -> Action:
    value = value.strip()
    if value == "passthrough":
        return Action("passthrough")
    if value == "disable":
        return Action("disable")
    if value == "dpi-cycle":
        return Action("dpi-cycle")
    if value.startswith("mouse:"):
        name = value.split(":", 1)[1]
        code = getattr(ecodes, name, None)
        if code is None or not name.startswith("BTN_"):
            raise ValueError(f"Invalid mouse action: {value}")
        return Action("mouse", code)
    if value.startswith("key:"):
        name = value.split(":", 1)[1]
        code = getattr(ecodes, name, None)
        if code is None or not name.startswith("KEY_"):
            raise ValueError(f"Invalid keyboard action: {value}")
        return Action("key", code)
    raise ValueError(f"Unknown action: {value}")


class DpiCycler:
    """Own the authoritative stage for application-driven DPI cycling."""

    def __init__(self, backend: HardwareBackend, device: MouseDevice, stages: list[int],
                 current_dpi: int, notifications_enabled: bool = True,
                 notifier: Notifier | None = None) -> None:
        self.backend = backend
        self.device = device
        self.stages = stages
        self.current_dpi = current_dpi
        self.notifications_enabled = notifications_enabled
        self.notifier = notifier if notifier is not None else FreedesktopNotifier()

    def cycle(self) -> bool:
        if not self.stages:
            LOG.warning("DPI cycle ignored: no configured stages")
            return False
        try:
            index = self.stages.index(self.current_dpi)
        except ValueError:
            index = -1
        next_dpi = self.stages[(index + 1) % len(self.stages)]
        try:
            if not self.backend.supports_dpi(self.device):
                LOG.warning("DPI cycle ignored: %s does not support DPI control", self.backend.name)
                return False
            confirmed = self.backend.set_dpi(self.device, next_dpi)
        except Exception as exc:
            LOG.warning("Could not set DPI to %s through %s: %s",
                        next_dpi, self.backend.name, exc)
            return False
        actual_dpi = (confirmed.display_value
                      if isinstance(confirmed, DpiState) else next_dpi)
        if not isinstance(actual_dpi, int):
            LOG.warning("DPI cycle produced independent X/Y DPI; using X axis")
            actual_dpi = actual_dpi[0]
        self.current_dpi = actual_dpi
        if self.notifications_enabled:
            try:
                self.notifier.notify_dpi(actual_dpi)
            except Exception as exc:
                LOG.warning("Desktop DPI notification failed: %s", exc)
        return True


class MouseRemapper:
    """Grab one physical mouse and emit translated events through uinput."""

    def __init__(self, device_path: str, mappings: dict[str, str],
                 shutdown_event: threading.Event | None = None,
                 dpi_cycler: DpiCycler | None = None) -> None:
        self.device_path = device_path
        self.device = InputDevice(device_path)
        parsed: dict[int, Action] = {}
        for name, action in mappings.items():
            code = getattr(ecodes, name, None)
            if code is None or not name.startswith("BTN_"):
                raise ValueError(f"Invalid remap source button: {name}")
            parsed[code] = parse_action(action)
        self.mappings = parsed
        self.ui: UInput | None = None
        self.shutdown_event = shutdown_event if shutdown_event is not None else threading.Event()
        self.dpi_cycler = dpi_cycler

    def _capabilities(self) -> dict[int, list[int]]:
        caps = self.device.capabilities(verbose=False)
        capabilities: dict[int, list[int]] = {}
        for event_type, codes in caps.items():
            if event_type == ecodes.EV_SYN:
                continue
            capabilities[event_type] = list(codes)

        rel = set(capabilities.get(ecodes.EV_REL, []))
        rel.update((ecodes.REL_X, ecodes.REL_Y))
        capabilities[ecodes.EV_REL] = sorted(rel)

        keys = set(capabilities.get(ecodes.EV_KEY, []))
        keys.update((ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE))
        for action in self.mappings.values():
            if action.code is not None and action.kind in {"mouse", "key"}:
                keys.add(action.code)
        capabilities[ecodes.EV_KEY] = sorted(keys)
        return capabilities

    def _emit(self, event_type: int, code: int, value: int) -> None:
        assert self.ui is not None
        self.ui.write(event_type, code, value)

    def _handle(self, event_type: int, code: int, value: int) -> None:
        if event_type == ecodes.EV_SYN:
            return
        if event_type != ecodes.EV_KEY:
            self._emit(event_type, code, value)
            return

        action = self.mappings.get(code, Action("passthrough"))
        if action.kind == "disable":
            return
        if action.kind == "dpi-cycle":
            if value == 1 and self.dpi_cycler is not None:
                self.dpi_cycler.cycle()
            return
        if action.kind == "passthrough":
            self._emit(event_type, code, value)
        elif action.code is not None:
            self._emit(ecodes.EV_KEY, action.code, value)

    def stop(self, *_: Any) -> None:
        self.shutdown_event.set()

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        try:
            self.device.grab()
            with UInput(self._capabilities(), name=f"mouse-control: {self.device.name}") as ui:
                self.ui = ui
                print(f"Remapping: {self.device.name}")
                print("Press Ctrl+C to stop.")
                while not self.shutdown_event.is_set():
                    readable, _, _ = select.select([self.device.fd], [], [], 0.25)
                    if not readable:
                        continue
                    for event in self.device.read():
                        self._handle(event.type, event.code, event.value)
                        if event.type != ecodes.EV_SYN:
                            self.ui.syn()
        finally:
            try:
                self.device.ungrab()
            except OSError:
                pass
            self.device.close()
