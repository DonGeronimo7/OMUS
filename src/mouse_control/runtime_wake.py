# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event-driven wake coordination and latency instrumentation.

The coordinator never discovers hardware and never grants authority.  It only
interrupts bounded retry waits after Linux-visible activity and records how
quickly the existing runtime becomes usable again.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
import logging
import math
import socket
import threading
import time
from typing import Callable

from .discovery import MouseDevice


LOG = logging.getLogger(__name__)
_NETLINK_KOBJECT_UEVENT = 15


class RuntimeWakeState(Enum):
    ACTIVE = auto()
    QUIESCENT = auto()
    RECONNECTING = auto()
    UNAVAILABLE = auto()
    STOPPING = auto()


@dataclass(frozen=True)
class WakeLatencySample:
    source: str
    t0_ns: int
    t1_ns: int | None = None
    t2_ns: int | None = None
    t3_ns: int | None = None

    def durations_ms(self) -> tuple[float | None, float | None, float | None]:
        return tuple(
            None if value is None else (value - self.t0_ns) / 1_000_000
            for value in (self.t1_ns, self.t2_ns, self.t3_ns)
        )


def _percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * .95) - 1)]


def _percentile99(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * .99) - 1)]


class WakeLatencyRecorder:
    """Retain bounded T0→T1/T2/T3 samples for repeated wake trials."""

    def __init__(self, maximum_samples: int = 128) -> None:
        self._samples: deque[WakeLatencySample] = deque(maxlen=maximum_samples)
        self._current: WakeLatencySample | None = None
        self._lock = threading.Lock()

    def begin(self, source: str, timestamp_ns: int) -> None:
        with self._lock:
            self._current = WakeLatencySample(source, timestamp_ns)

    def _mark(self, field: str, timestamp_ns: int) -> None:
        with self._lock:
            current = self._current
            if current is None or getattr(current, field) is not None:
                return
            values = current.__dict__ | {field: timestamp_ns}
            current = WakeLatencySample(**values)
            self._current = current
            if current.t2_ns is not None and current.t3_ns is not None:
                self._samples.append(current)
                self._current = None
                t1, t2, t3 = current.durations_ms()
                LOG.info(
                    "Wake latency (%s): T0→T1 %.3f ms, T0→T2 %.3f ms, "
                    "T0→T3 %.3f ms", current.source, t1, t2, t3)

    def recognized(self, timestamp_ns: int) -> None:
        self._mark("t1_ns", timestamp_ns)

    def backend_usable(self, timestamp_ns: int) -> None:
        self._mark("t2_ns", timestamp_ns)

    def runtime_usable(self, timestamp_ns: int) -> None:
        self._mark("t3_ns", timestamp_ns)

    @property
    def samples(self) -> tuple[WakeLatencySample, ...]:
        with self._lock:
            return tuple(self._samples)

    def summary(self) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        with self._lock:
            samples = tuple(self._samples)
        for index, name in enumerate(("t0_to_t1", "t0_to_t2", "t0_to_t3")):
            values = [sample.durations_ms()[index] for sample in samples]
            numeric = [value for value in values if value is not None]
            if numeric:
                ordered = sorted(numeric)
                middle = len(ordered) // 2
                median = (ordered[middle] if len(ordered) % 2 else
                          (ordered[middle - 1] + ordered[middle]) / 2)
                result[name] = {
                    "minimum_ms": ordered[0], "median_ms": median,
                    "p95_ms": _percentile95(ordered),
                    "p99_ms": _percentile99(ordered),
                    "maximum_ms": ordered[-1],
                }
        return result


class RuntimeWakeCoordinator:
    """Fan out wake evidence without polling or rebuilding healthy sessions."""

    def __init__(self, *, quiescent_after: float = 30., clock_ns=time.monotonic_ns,
                 recorder: WakeLatencyRecorder | None = None) -> None:
        self.quiescent_after_ns = int(quiescent_after * 1_000_000_000)
        self._clock_ns = clock_ns
        self.recorder = recorder or WakeLatencyRecorder()
        self._condition = threading.Condition()
        self._generation = 0
        self._state = RuntimeWakeState.ACTIVE
        self._last_activity_ns = clock_ns()
        self._pending_t0_ns: int | None = None
        self._management_ready = True

    @property
    def state(self) -> RuntimeWakeState:
        with self._condition:
            return self._state

    @property
    def generation(self) -> int:
        with self._condition:
            return self._generation

    @property
    def stopping(self) -> bool:
        with self._condition:
            return self._state is RuntimeWakeState.STOPPING

    def _signal(self) -> None:
        self._generation += 1
        self._condition.notify_all()

    def device_event(self, source: str, timestamp_ns: int | None = None) -> None:
        """Record a matching Linux reappearance event and cancel retry backoff."""
        timestamp_ns = self._clock_ns() if timestamp_ns is None else timestamp_ns
        with self._condition:
            if self._state is RuntimeWakeState.STOPPING:
                return
            if (self._pending_t0_ns is None and
                    (self._state is not RuntimeWakeState.ACTIVE or
                     timestamp_ns - self._last_activity_ns >= self.quiescent_after_ns)):
                self._pending_t0_ns = timestamp_ns
                self.recorder.begin(source, timestamp_ns)
            self._signal()

    def activity(self, source: str, timestamp_ns: int | None = None) -> None:
        """Mark the first usable input/report after quiet or reconnect."""
        timestamp_ns = self._clock_ns() if timestamp_ns is None else timestamp_ns
        with self._condition:
            if self._state is RuntimeWakeState.STOPPING:
                return
            waking = (
                self._state is not RuntimeWakeState.ACTIVE
                or timestamp_ns - self._last_activity_ns >= self.quiescent_after_ns
            )
            self._last_activity_ns = timestamp_ns
            if not waking:
                return
            if self._pending_t0_ns is None:
                self.recorder.begin(source, timestamp_ns)
            self._state = RuntimeWakeState.ACTIVE
            self._pending_t0_ns = None
            self.recorder.recognized(timestamp_ns)
            if self._management_ready:
                self.recorder.backend_usable(timestamp_ns)
            self._signal()

    def recognized(self, timestamp_ns: int | None = None) -> None:
        self.recorder.recognized(self._clock_ns() if timestamp_ns is None else timestamp_ns)

    def backend_usable(self, timestamp_ns: int | None = None) -> None:
        timestamp_ns = self._clock_ns() if timestamp_ns is None else timestamp_ns
        with self._condition:
            if self._state is RuntimeWakeState.STOPPING:
                return
            self._management_ready = True
        self.recorder.backend_usable(timestamp_ns)

    def management_unavailable(self) -> None:
        """Mark optional hardware management stale without blocking input recovery."""
        with self._condition:
            if self._state is not RuntimeWakeState.STOPPING:
                self._management_ready = False

    def runtime_usable(self, timestamp_ns: int | None = None) -> None:
        self.recorder.runtime_usable(self._clock_ns() if timestamp_ns is None else timestamp_ns)

    def reconnecting(self) -> None:
        with self._condition:
            if self._state is not RuntimeWakeState.STOPPING:
                self._state = RuntimeWakeState.RECONNECTING
                self._management_ready = False

    def unavailable(self) -> None:
        with self._condition:
            if self._state is not RuntimeWakeState.STOPPING:
                self._state = RuntimeWakeState.UNAVAILABLE
                self._management_ready = False

    def wait(self, after_generation: int, timeout: float,
             shutdown_event: threading.Event) -> bool:
        """Return true when wake evidence interrupts the retry timeout."""
        with self._condition:
            self._condition.wait_for(
                lambda: (self._generation != after_generation
                         or self._state is RuntimeWakeState.STOPPING
                         or shutdown_event.is_set()), timeout)
            return (
                self._generation != after_generation
                and self._state is not RuntimeWakeState.STOPPING
                and not shutdown_event.is_set()
            )

    def stop(self) -> None:
        with self._condition:
            self._state = RuntimeWakeState.STOPPING
            self._signal()


def _uevent_matches(data: bytes, device: MouseDevice) -> bool:
    """Accept only add/change evidence carrying the selected exact VID:PID."""
    try:
        fields = data.decode("ascii", "replace").split("\0")
        env = dict(field.split("=", 1) for field in fields if "=" in field)
    except Exception:
        return False
    if env.get("ACTION") not in {"add", "change", "bind", "online"}:
        return False
    if device.vendor is None or device.product is None:
        return False
    vendor, product = device.vendor, device.product
    hid_id = env.get("HID_ID", "").split(":")
    if len(hid_id) == 3:
        try:
            if int(hid_id[1], 16) == vendor and int(hid_id[2], 16) == product:
                return True
        except ValueError:
            pass
    product_field = env.get("PRODUCT", "").split("/")
    if len(product_field) >= 3:
        try:
            if env.get("SUBSYSTEM") == "input":
                return int(product_field[1], 16) == vendor and int(product_field[2], 16) == product
            return int(product_field[0], 16) == vendor and int(product_field[1], 16) == product
        except ValueError:
            pass
    return False


class LinuxDeviceEventMonitor:
    """Listen for matching kernel/udev reappearance without a polling loop."""

    def __init__(self, device: MouseDevice, callback: Callable[[str, int], None],
                 *, socket_factory=socket.socket, clock_ns=time.monotonic_ns) -> None:
        self.device, self.callback = device, callback
        self._socket_factory, self._clock_ns = socket_factory, clock_ns
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _run(self) -> None:
        try:
            sock = self._socket_factory(
                socket.AF_NETLINK, socket.SOCK_DGRAM, _NETLINK_KOBJECT_UEVENT)
            self._socket = sock
            sock.bind((0, 3))  # kernel and udev multicast groups
            sock.settimeout(1.)
            while not self._stop.is_set():
                try:
                    data = sock.recv(8192)
                except TimeoutError:
                    continue
                if _uevent_matches(data, self.device):
                    self.callback("device-return", self._clock_ns())
        except (OSError, PermissionError) as exc:
            LOG.debug("Linux device-event monitor unavailable: %s", exc)
        finally:
            if self._socket is not None:
                self._socket.close()
                self._socket = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="mouse-device-events", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._socket is not None:
            self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
