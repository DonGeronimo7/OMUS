"""Optional DPI monitoring and Freedesktop desktop notifications."""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Protocol

from .discovery import MouseDevice
from .hardware import HardwareBackend


LOG = logging.getLogger(__name__)


class Notifier(Protocol):
    def notify_dpi(self, dpi: int | tuple[int, int]) -> None: ...


class FreedesktopNotifier:
    """Send short-lived DPI notifications on one dedicated D-Bus worker."""

    def __init__(self) -> None:
        self._queue: queue.Queue[int | tuple[int, int] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    @staticmethod
    def _body(dpi: int | tuple[int, int]) -> str:
        if isinstance(dpi, tuple):
            x, y = dpi
            if y in (0, x):
                return f"{x} DPI"
            return f"{x} × {y} DPI"
        return f"{dpi} DPI"

    async def _connect(self):
        from dbus_next import BusType
        from dbus_next.aio import MessageBus

        return await MessageBus(bus_type=BusType.SESSION).connect()

    async def _notify(self, bus, dpi: int | tuple[int, int]) -> int:
        from dbus_next import Message, Variant
        from dbus_next.constants import MessageType

        reply = await bus.call(Message(
            destination="org.freedesktop.Notifications",
            path="/org/freedesktop/Notifications",
            interface="org.freedesktop.Notifications",
            member="Notify",
            signature="susssasa{sv}i",
            body=["mouse-control", 0, "", "Mouse DPI", self._body(dpi), [], {
                "urgency": Variant("y", 1),
                "transient": Variant("b", True),
                "suppress-sound": Variant("b", True),
            }, 1500],
        ))
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(reply.body[0] if reply.body else reply.error_name)
        return int(reply.body[0])

    @staticmethod
    def _disconnect(bus) -> None:
        if bus is not None:
            try:
                bus.disconnect()
            except Exception:
                pass

    async def _run_async(self) -> None:
        bus = None
        try:
            while True:
                try:
                    dpi = self._queue.get_nowait()
                except queue.Empty:
                    # Yield while idle so queued work and shutdown stay responsive.
                    await asyncio.sleep(0.05)
                    continue
                try:
                    if dpi is None:
                        return
                    if bus is None:
                        bus = await self._connect()
                    LOG.info("DPI Notify: %s replaces_id=0", self._body(dpi))
                    notification_id = await self._notify(bus, dpi)
                    LOG.info("DPI Notify result: id=%s", notification_id)
                except Exception as exc:
                    LOG.warning("DPI notification failed: %s", exc)
                    self._disconnect(bus)
                    bus = None
                finally:
                    self._queue.task_done()
        finally:
            self._disconnect(bus)

    def _run(self) -> None:
        asyncio.run(self._run_async())

    def notify_dpi(self, dpi: int | tuple[int, int]) -> None:
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run, name="dpi-notifier", daemon=True
                )
                self._thread.start()
        self._queue.put(dpi)

    def wait_idle(self) -> None:
        """Wait for queued calls; intended for deterministic tests."""
        self._queue.join()

    def close(self) -> None:
        thread = self._thread
        if thread is None or not thread.is_alive():
            return
        self._queue.put(None)
        thread.join(timeout=1.0)


class DpiMonitor:
    """Poll a backend conservatively without coupling the remapper to hardware APIs."""

    def __init__(self, backend: HardwareBackend, device: MouseDevice,
                 notifier: Notifier | None = None, interval: float = 1.0,
                 shutdown_event: threading.Event | None = None) -> None:
        self.backend = backend
        self.device = device
        self.notifier = notifier if notifier is not None else FreedesktopNotifier()
        self.interval = interval
        self._last_dpi: int | tuple[int, int] | None = None
        self.shutdown_event = shutdown_event if shutdown_event is not None else threading.Event()
        self._thread: threading.Thread | None = None
        self._read_failed = False
        self._notify_failed = False

    def poll_once(self) -> None:
        try:
            dpi = self.backend.get_dpi(self.device)
            if dpi is None:
                return
            self._read_failed = False
        except Exception as exc:
            if not self._read_failed:
                LOG.warning("DPI monitoring read failed; will retry: %s", exc)
                self._read_failed = True
            return

        previous = self._last_dpi
        self._last_dpi = dpi
        if previous is None or dpi == previous:
            return
        try:
            self.notifier.notify_dpi(dpi)
            self._notify_failed = False
        except Exception as exc:
            if not self._notify_failed:
                LOG.warning("Desktop DPI notification failed; will retry: %s", exc)
                self._notify_failed = True

    def _run(self) -> None:
        self.poll_once()
        while not self.shutdown_event.wait(self.interval):
            self.poll_once()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="dpi-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.shutdown_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval + 0.5))
        close = getattr(self.notifier, "close", None)
        if close is not None:
            close()


class DpiEventMonitor:
    """Translate backend stage events into configured DPI notifications."""

    def __init__(self, backend: HardwareBackend, device: MouseDevice,
                 stages: list[int], active_dpi: int,
                 notifier: Notifier | None = None,
                 shutdown_event: threading.Event | None = None) -> None:
        self.backend = backend
        self.device = device
        self.stages = stages
        self.notifier = notifier if notifier is not None else FreedesktopNotifier()
        self.shutdown_event = shutdown_event if shutdown_event is not None else threading.Event()
        self._last_stage: int | None = (
            stages.index(active_dpi) if active_dpi in stages else None
        )
        self._thread: threading.Thread | None = None

    def handle_stage(self, stage: int) -> None:
        if stage < 0 or stage >= len(self.stages):
            LOG.warning("Ignoring out-of-range HID++ DPI stage: %s", stage)
            return
        if stage == self._last_stage:
            return
        self._last_stage = stage
        dpi = self.stages[stage]
        try:
            self.notifier.notify_dpi(dpi)
            LOG.info("HID++ DPI changed to %s (stage %s)", dpi, stage)
        except Exception as exc:
            LOG.warning("Desktop DPI notification failed: %s", exc)

    def _run(self) -> None:
        try:
            self.backend.watch_dpi_events(self.device, self.handle_stage,
                                          self.shutdown_event)
        except Exception as exc:
            LOG.warning("HID++ DPI monitoring stopped: %s", exc)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="dpi-event-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.shutdown_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        close = getattr(self.notifier, "close", None)
        if close is not None:
            close()


def create_dpi_monitor(backend: HardwareBackend, device: MouseDevice,
                       enabled: bool = True,
                       shutdown_event: threading.Event | None = None,
                       stages: list[int] | None = None,
                       active_dpi: int = 0) -> DpiMonitor | DpiEventMonitor | None:
    if not enabled:
        return None
    try:
        if backend.supports_dpi_events(device) is True:
            return DpiEventMonitor(backend, device, stages or [], active_dpi,
                                   shutdown_event=shutdown_event)
        if not backend.supports_dpi_monitoring(device):
            return None
    except Exception as exc:
        LOG.warning("DPI monitoring is unavailable: %s", exc)
        return None
    return DpiMonitor(backend, device, shutdown_event=shutdown_event)
