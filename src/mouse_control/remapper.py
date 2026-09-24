# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live mouse remapping using evdev input capture and a virtual uinput device."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
import errno
import queue
import select
import signal
import threading
import time
from typing import Any
import logging

from evdev import InputDevice, UInput, ecodes

from .discovery import MouseDevice, get_mouse_devices
from .hardware import DpiState, HardwareBackend
from .notifications import FreedesktopNotifier, Notifier


LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Action:
    kind: str
    code: int | None = None
    codes: tuple[int, ...] = ()


@dataclass(frozen=True)
class MacroStep:
    action: Action | None = None
    delay_ms: int = 0


def parse_macros(value: object) -> dict[str, tuple[MacroStep, ...]]:
    """Validate structured macro configuration without accepting executable text."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("[macros] must be a table")
    parsed: dict[str, tuple[MacroStep, ...]] = {}
    for name, raw_steps in value.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Macro names must be non-empty strings")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError(f"Macro {name!r} must contain at least one step")
        steps: list[MacroStep] = []
        for index, raw in enumerate(raw_steps, 1):
            if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
                raise ValueError(f"Macro {name!r} step {index} must be a table with a type")
            kind = raw["type"].strip()
            if kind == "delay":
                milliseconds = raw.get("milliseconds")
                if (not isinstance(milliseconds, int) or isinstance(milliseconds, bool)
                        or not 0 <= milliseconds <= 60_000):
                    raise ValueError(
                        f"Macro {name!r} step {index} delay must be 0..60000 milliseconds"
                    )
                if set(raw) != {"type", "milliseconds"}:
                    raise ValueError(f"Macro {name!r} step {index} has unknown fields")
                steps.append(MacroStep(delay_ms=milliseconds))
                continue
            action_value = raw.get("value")
            if not isinstance(action_value, str) or set(raw) != {"type", "value"}:
                raise ValueError(f"Macro {name!r} step {index} requires one string value")
            action = parse_action(f"{kind}:{action_value}")
            if action.kind not in {"key", "chord", "mouse"}:
                raise ValueError(f"Macro {name!r} step {index} uses unsupported action {kind!r}")
            steps.append(MacroStep(action=action))
        parsed[name] = tuple(steps)
    return parsed


def parse_action(value: str) -> Action:
    value = value.strip()
    if value == "passthrough":
        return Action("passthrough")
    if value == "disable":
        return Action("disable")
    if value == "dpi-cycle":
        return Action("dpi-cycle")
    if value.startswith("macro:"):
        name = value.split(":", 1)[1].strip()
        if not name:
            raise ValueError(f"Invalid macro action: {value}")
        return Action("macro", codes=(), code=None)
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
    if value.startswith("chord:"):
        names = value.split(":", 1)[1].split("+")
        codes = tuple(getattr(ecodes, name, None) for name in names)
        if (len(codes) < 2 or any(not name.startswith("KEY_") or not isinstance(code, int)
                                   for name, code in zip(names, codes))
                or len(set(codes)) != len(codes)):
            raise ValueError(f"Invalid keyboard chord: {value}")
        return Action("chord", codes=codes)
    raise ValueError(f"Unknown action: {value}")


class DpiCycler:
    """Cycle configured stages while retaining the confirmed hardware DPI."""

    def __init__(self, backend: HardwareBackend, device: MouseDevice, stages: list[int],
                 current_dpi: int, notifications_enabled: bool = True,
                 notifier: Notifier | None = None) -> None:
        self.backend = backend
        self.device = device
        self.stages = stages
        # Persisted active DPI is a preference, never evidence of live state.
        self.current_dpi = None
        self.current_dpi_confirmed = False
        self._stage_index = -1
        self._state_epoch = None
        self._cycle_lock = threading.RLock()
        self.notifications_enabled = notifications_enabled
        self.notifier = notifier if notifier is not None else FreedesktopNotifier()
        self.synchronize()

    def _epoch(self):
        return getattr(self.backend, "dpi_epoch", getattr(self.backend, "generation", None))

    @staticmethod
    def _valid_dpi(dpi):
        return (type(dpi) is int and dpi > 0) or (
            isinstance(dpi, tuple) and len(dpi) == 2 and
            all(type(value) is int and value > 0 for value in dpi))

    def invalidate(self) -> None:
        with self._cycle_lock:
            self.current_dpi_confirmed = False
            self._stage_index = -1

    def synchronize(self) -> bool:
        """Read once per hardware/wake epoch; ordinary presses reuse confirmation."""
        with self._cycle_lock:
            epoch = self._epoch()
            if self.current_dpi_confirmed and self._state_epoch == epoch:
                return True
            self.invalidate()
            started = time.perf_counter_ns()
            try:
                dpi = self.backend.get_dpi(self.device)
                if not self._valid_dpi(dpi):
                    return False
                self.observe_dpi(dpi)
            except Exception as exc:
                LOG.debug("DPI synchronization waiting for hardware: %s", exc)
                return False
            LOG.info("DPI synchronized: confirmed=%s elapsed_ms=%.3f", dpi,
                     (time.perf_counter_ns() - started) / 1e6)
            return True

    def cycle(self) -> bool:
        with self._cycle_lock:
            transaction = getattr(type(self.backend), "dpi_transaction", None)
            with (transaction(self.backend) if callable(transaction) else nullcontext()):
                return self._cycle()

    def observe_dpi(self, dpi: int | tuple[int, int]) -> None:
        """Synchronize from hardware without changing desired configuration."""
        if not self._valid_dpi(dpi):
            return
        with self._cycle_lock:
            self.current_dpi = dpi
            self.current_dpi_confirmed = True
            scalar = dpi[0] if isinstance(dpi, tuple) and dpi[0] == dpi[1] else dpi
            # Preserve established off-list behavior: next press selects stage 0.
            self._stage_index = self.stages.index(scalar) if scalar in self.stages else -1
            self._state_epoch = self._epoch()

    def _cycle(self) -> bool:
        if not self.stages:
            LOG.warning("DPI cycle ignored: no configured stages")
            return False
        started = time.perf_counter_ns()
        if not self.synchronize():
            LOG.warning("DPI cycle deferred: hardware DPI is unknown")
            return False
        previous = self.current_dpi
        next_dpi = self.stages[(self._stage_index + 1) % len(self.stages)]
        try:
            if not self.backend.supports_dpi(self.device):
                return False
            result = self.backend.set_dpi(self.device, next_dpi)
            # Native and PROVEN learned writers already perform their canonical
            # readback. Reuse it instead of adding a second HID query.
            actual = (result.display_value if isinstance(result, DpiState) and result.confirmed
                      else self.backend.get_dpi(self.device))
            if not self._valid_dpi(actual):
                raise RuntimeError("hardware did not confirm the requested change")
            self.observe_dpi(actual)
            if actual == previous and not self._dpi_matches(actual, next_dpi):
                LOG.warning("DPI cycle unchanged: requested=%s confirmed=%s", next_dpi, actual)
                return False
        except Exception as exc:
            self.invalidate()
            self.synchronize()
            LOG.warning("DPI cycle failed: requested=%s confirmed=%s: %s",
                        next_dpi, self.current_dpi if self.current_dpi_confirmed else None, exc)
            return False
        self._record_desired_dpi(actual)
        LOG.info("DPI cycle: requested=%s confirmed=%s elapsed_ms=%.3f", next_dpi, actual,
                 (time.perf_counter_ns() - started) / 1e6)
        if self.notifications_enabled:
            try:
                deliberate = (self.notifier.notify_deliberate_dpi
                              if callable(getattr(type(self.notifier), "notify_deliberate_dpi", None))
                              else None)
                (deliberate or self.notifier.notify_dpi)(actual)
            except Exception as exc:
                LOG.warning("Desktop DPI notification failed: %s", exc)
        return True

    @staticmethod
    def _dpi_matches(actual_dpi, requested):
        if isinstance(actual_dpi, tuple):
            return actual_dpi[0] == requested and actual_dpi[1] in (0, requested)
        return actual_dpi == requested

    def _record_desired_dpi(self, dpi):
        record = getattr(type(self.backend), "record_active_dpi", None)
        if callable(record):
            record(self.backend, dpi)


class MouseRemapper:
    """Grab one physical mouse and emit translated events through uinput."""

    def __init__(self, device_path: str, mappings: dict[str, str],
                 shutdown_event: threading.Event | None = None,
                 dpi_cycler: DpiCycler | None = None,
                 target_device: MouseDevice | None = None,
                 retry_interval: float = 0.5,
                 event_observer: Any | None = None,
                 macros: object = None,
                 wake_coordinator: Any | None = None,
                 motion_diagnostic: Any | None = None) -> None:
        self.device_path = device_path
        # An evdev event node is disposable.  Keep the selected mouse's
        # discovery identity separately so a changed eventN can be rebound.
        self.target_device = target_device or MouseDevice("", device_path)
        self.device: InputDevice | None = None
        parsed: dict[int, Action] = {}
        for name, action in mappings.items():
            code = getattr(ecodes, name, None)
            if code is None or not name.startswith("BTN_"):
                raise ValueError(f"Invalid remap source button: {name}")
            parsed[code] = parse_action(action)
        self.mappings = parsed
        self.macros = parse_macros(macros)
        self._macro_names = {
            code: mappings[name].split(":", 1)[1].strip()
            for name, code in ((name, getattr(ecodes, name, None)) for name in mappings)
            if code is not None and parsed[code].kind == "macro"
        }
        missing = sorted({name for name in self._macro_names.values() if name not in self.macros})
        if missing:
            raise ValueError("Undefined macro(s): " + ", ".join(missing))
        self.ui: UInput | None = None
        self.shutdown_event = shutdown_event if shutdown_event is not None else threading.Event()
        self.dpi_cycler = dpi_cycler
        self.retry_interval = retry_interval
        self.event_observer = event_observer
        self.wake_coordinator = wake_coordinator
        self.motion_diagnostic = motion_diagnostic
        self._pressed_keys: set[int] = set()
        self._held_chords: set[int] = set()
        self._chord_key_counts: dict[int, int] = {}
        self._ambiguity_logged = False
        self._output_lock = threading.RLock()
        self._macro_queue: queue.Queue[tuple[MacroStep, ...] | None] = queue.Queue()
        self._macro_cancel = threading.Event()
        self._macro_thread: threading.Thread | None = None
        self._dpi_queue: queue.Queue[int | None] = queue.Queue()
        self._dpi_cancel = threading.Event()
        self._dpi_thread: threading.Thread | None = None
        self._pending_frame: list[tuple[int, int, int]] = []
        self._discard_until_syn_report = False

    def _capabilities(self) -> dict[int, list[int]]:
        assert self.device is not None
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
            keys.update(action.codes)
        for steps in self.macros.values():
            for step in steps:
                if step.action is not None:
                    if step.action.code is not None:
                        keys.add(step.action.code)
                    keys.update(step.action.codes)
        capabilities[ecodes.EV_KEY] = sorted(keys)
        return capabilities

    def _emit(self, event_type: int, code: int, value: int) -> None:
        output_lock = getattr(self, "_output_lock", None)
        if output_lock is None:
            output_lock = self._output_lock = threading.RLock()
        with output_lock:
            assert self.ui is not None
            self.ui.write(event_type, code, value)
            motion_diagnostic = getattr(self, "motion_diagnostic", None)
            if motion_diagnostic is not None:
                motion_diagnostic.virtual_event(event_type, code, value)
            if event_type == ecodes.EV_KEY:
                pressed_keys = getattr(self, "_pressed_keys", None)
                if pressed_keys is None:
                    pressed_keys = self._pressed_keys = set()
                if value:
                    pressed_keys.add(code)
                else:
                    pressed_keys.discard(code)

    def _tap_action(self, action: Action) -> None:
        codes = action.codes if action.kind == "chord" else (action.code,)
        emitted: list[int] = []
        with self._output_lock:
            try:
                for code in codes:
                    assert code is not None
                    # Do not release a key/button already held by an ordinary
                    # mapping when this short macro action finishes.
                    if code in self._pressed_keys:
                        continue
                    self._emit(ecodes.EV_KEY, code, 1)
                    emitted.append(code)
                if emitted and self.ui is not None:
                    self.ui.syn()
            finally:
                for code in reversed(emitted):
                    self._emit(ecodes.EV_KEY, code, 0)
                if emitted and self.ui is not None:
                    self.ui.syn()

    def _play_macro(
        self,
        steps: tuple[MacroStep, ...],
        cancel_event: threading.Event | None = None,
    ) -> None:
        cancel_event = self._macro_cancel if cancel_event is None else cancel_event
        for step in steps:
            if cancel_event.is_set() or self.shutdown_event.is_set():
                return
            if step.action is not None:
                self._tap_action(step.action)
            elif cancel_event.wait(step.delay_ms / 1000):
                return

    def _macro_worker(
        self,
        requests: queue.Queue[tuple[MacroStep, ...] | None],
        cancel_event: threading.Event,
    ) -> None:
        while not self.shutdown_event.is_set():
            steps = requests.get()
            if steps is None:
                return
            try:
                self._play_macro(steps, cancel_event)
            except Exception as exc:
                LOG.warning("Macro playback failed: %s", exc)
                self._release_pressed_keys()

    def _start_macro_worker(self) -> None:
        if self._macro_thread is None or not self._macro_thread.is_alive():
            self._macro_cancel = threading.Event()
            self._macro_queue = queue.Queue()
            self._macro_thread = threading.Thread(
                target=self._macro_worker,
                args=(self._macro_queue, self._macro_cancel),
                name="omus-macros", daemon=True,
            )
            self._macro_thread.start()

    def _stop_macros(self) -> None:
        self._macro_cancel.set()
        self._macro_queue.put(None)
        if self._macro_thread is not None and self._macro_thread is not threading.current_thread():
            self._macro_thread.join(timeout=1)
        self._macro_thread = None

    def _dpi_worker(
        self,
        requests: queue.Queue[int | None],
        cancel_event: threading.Event,
    ) -> None:
        while not self.shutdown_event.is_set():
            request = requests.get()
            if request is None or cancel_event.is_set():
                return
            try:
                if self.dpi_cycler is not None:
                    success = self.dpi_cycler.cycle()
                    LOG.info("DPI input result: success=%s confirmed=%s input_to_result_ms=%.3f",
                             success, self.dpi_cycler.current_dpi,
                             (time.perf_counter_ns() - request) / 1e6)
            except Exception as exc:
                LOG.warning("DPI cycle worker failed: %s", exc)

    def _start_dpi_worker(self) -> None:
        if self.dpi_cycler is None:
            return
        if self._dpi_thread is None or not self._dpi_thread.is_alive():
            self._dpi_cancel = threading.Event()
            self._dpi_queue = queue.Queue()
            self._dpi_thread = threading.Thread(
                target=self._dpi_worker,
                args=(self._dpi_queue, self._dpi_cancel),
                name="omus-dpi-cycle", daemon=True,
            )
            self._dpi_thread.start()

    def _schedule_dpi_cycle(self) -> None:
        received = time.perf_counter_ns()
        self._start_dpi_worker()
        if self.dpi_cycler is None:
            return
        self._dpi_queue.put(received)

    def _stop_dpi_worker(self, *, wait: bool = True) -> None:
        self._dpi_cancel.set()
        self._dpi_queue.put(None)
        if (wait and self._dpi_thread is not None
                and self._dpi_thread is not threading.current_thread()):
            self._dpi_thread.join(timeout=1)
        self._dpi_thread = None

    @staticmethod
    def _is_disconnect(exc: OSError) -> bool:
        return exc.errno in {errno.ENODEV, errno.ENOENT, errno.EIO, errno.ENXIO}

    def _matching_devices(self) -> list[MouseDevice]:
        """Return unambiguous discovery candidates for a non-stable path."""
        target = self.target_device
        if target.vendor is None or target.product is None:
            return []
        matches = [mouse for mouse in get_mouse_devices()
                   if mouse.vendor == target.vendor and mouse.product == target.product
                   and (target.bustype is None or mouse.bustype == target.bustype)]
        if target.phys:
            same_phys = [mouse for mouse in matches if mouse.phys == target.phys]
            if same_phys:
                return same_phys
        # USB topology may change on reconnect. A unique exact device identity
        # is still usable; multiple candidates remain ambiguous.
        return matches

    def _acquire_device(self) -> InputDevice | None:
        # A by-id symlink is the strongest identity we have.  Opening it also
        # follows it when the receiver returns on a different event node.
        if "/dev/input/by-id/" in self.device_path:
            try:
                return InputDevice(self.device_path)
            except OSError as exc:
                if not self._is_disconnect(exc):
                    raise
                return None

        candidates = self._matching_devices()
        if len(candidates) > 1:
            if not self._ambiguity_logged:
                LOG.warning("Mouse reconnect is ambiguous; waiting for the selected device")
                self._ambiguity_logged = True
            return None
        self._ambiguity_logged = False
        path = candidates[0].path if candidates else self.device_path
        try:
            return InputDevice(path)
        except OSError as exc:
            if not self._is_disconnect(exc):
                raise
            return None

    def _release_pressed_keys(self) -> None:
        output_lock = getattr(self, "_output_lock", None)
        if output_lock is None:
            output_lock = self._output_lock = threading.RLock()
        with output_lock:
            if self.ui is None:
                self._pressed_keys.clear()
                self._held_chords.clear()
                self._chord_key_counts.clear()
                return
            had_pressed_keys = bool(self._pressed_keys)
            for source in tuple(self._held_chords):
                self._handle_chord(source, self.mappings[source], 0)
            for code in tuple(self._pressed_keys):
                self.ui.write(ecodes.EV_KEY, code, 0)
            if had_pressed_keys:
                self.ui.syn()
            self._pressed_keys.clear()
            self._held_chords.clear()
            self._chord_key_counts.clear()

    def _handle_chord(self, source: int, action: Action, value: int) -> None:
        if value == 1:
            if source in self._held_chords:
                return
            self._held_chords.add(source)
            for key in action.codes:
                count = self._chord_key_counts.get(key, 0)
                if count == 0:
                    self._emit(ecodes.EV_KEY, key, 1)
                self._chord_key_counts[key] = count + 1
        elif value == 0:
            if source not in self._held_chords:
                return
            self._held_chords.remove(source)
            for key in reversed(action.codes):
                count = self._chord_key_counts[key] - 1
                if count:
                    self._chord_key_counts[key] = count
                else:
                    del self._chord_key_counts[key]
                    self._emit(ecodes.EV_KEY, key, 0)

    def _close_device(self) -> None:
        if self.device is None:
            return
        try:
            self.device.ungrab()
        except OSError:
            pass
        self.device.close()
        self.device = None

    def _observe_event(self, event_type: int, code: int, value: int) -> None:
        observe = getattr(getattr(self, "event_observer", None), "observe_evdev_event", None)
        if callable(observe):
            try:
                observe(event_type, code, value)
            except Exception as exc:
                LOG.warning("Calibrated evdev observation failed: %s", exc)

    def _invalidate_observer_continuity(self) -> None:
        invalidate = getattr(
            self.event_observer, "invalidate_observer_continuity", None
        )
        if callable(invalidate):
            invalidate()

    def _handle(self, event_type: int, code: int, value: int) -> None:
        self._observe_event(event_type, code, value)
        if event_type == ecodes.EV_SYN:
            if code not in {ecodes.SYN_REPORT, ecodes.SYN_DROPPED}:
                self._emit(event_type, code, value)
            return
        if event_type != ecodes.EV_KEY:
            self._emit(event_type, code, value)
            return

        action = self.mappings.get(code, Action("passthrough"))
        if action.kind == "disable":
            return
        if action.kind == "dpi-cycle":
            if value == 1:
                self._schedule_dpi_cycle()
            return
        if action.kind == "macro":
            if value == 1:
                self._start_macro_worker()
                self._macro_queue.put(self.macros[self._macro_names[code]])
            return
        if action.kind == "passthrough":
            self._emit(event_type, code, value)
        elif action.kind == "chord":
            self._handle_chord(code, action, value)
        elif action.code is not None:
            self._emit(ecodes.EV_KEY, action.code, value)

    def _process_event(
        self,
        event_type: int,
        code: int,
        value: int,
        *,
        timestamp_ns: int | None = None,
        arrival_ns: int | None = None,
    ) -> bool:
        """Buffer and forward one physical evdev frame.

        Return True after a complete, usable physical frame was emitted.  A
        SYN_DROPPED marker means the kernel client queue overflowed: the
        incomplete frame and all events through the next SYN_REPORT are not
        trustworthy and must not reach uinput.
        """
        if event_type == ecodes.EV_SYN and code == ecodes.SYN_DROPPED:
            self._observe_event(event_type, code, value)
            self._pending_frame.clear()
            self._discard_until_syn_report = True
            if self.motion_diagnostic is not None:
                self.motion_diagnostic.dropped()
            self._invalidate_observer_continuity()
            if self.wake_coordinator is not None:
                self.wake_coordinator.reconnecting()
            self._stop_macros()
            self._stop_dpi_worker(wait=False)
            self._release_pressed_keys()
            LOG.warning("Input events dropped; discarding through the next SYN_REPORT")
            return False

        if self._discard_until_syn_report:
            if event_type == ecodes.EV_SYN and code == ecodes.SYN_REPORT:
                self._discard_until_syn_report = False
            return False

        if event_type == ecodes.EV_SYN and code == ecodes.SYN_REPORT:
            now_ns = time.monotonic_ns() if arrival_ns is None else arrival_ns
            if self.motion_diagnostic is not None:
                self.motion_diagnostic.physical_frame(
                    self._pending_frame,
                    now_ns if timestamp_ns is None else timestamp_ns,
                    now_ns,
                )
            for pending_type, pending_code, pending_value in self._pending_frame:
                self._handle(pending_type, pending_code, pending_value)
            self._pending_frame.clear()
            self._handle(event_type, code, value)
            assert self.ui is not None
            self.ui.syn()
            if self.motion_diagnostic is not None:
                self.motion_diagnostic.virtual_frame(time.monotonic_ns())
            return True

        # Other synchronization codes, including SYN_MT_REPORT and the
        # obsolete SYN_CONFIG, belong to the current physical frame.  Preserve
        # their ordering instead of mistaking them for a frame boundary.
        self._pending_frame.append((event_type, code, value))
        return False

    def stop(self, *_: Any) -> None:
        self.shutdown_event.set()
        if self.wake_coordinator is not None:
            self.wake_coordinator.stop()

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        try:
            announced = False
            disconnected = False
            while not self.shutdown_event.is_set():
                if self.device is None:
                    wake_generation = (self.wake_coordinator.generation
                                       if self.wake_coordinator is not None else None)
                    self.device = self._acquire_device()
                    if self.device is None:
                        if not disconnected:
                            LOG.warning("Mouse disconnected; waiting for reconnect")
                            disconnected = True
                        if self.wake_coordinator is None:
                            self.shutdown_event.wait(self.retry_interval)
                        else:
                            self.wake_coordinator.wait(
                                wake_generation, self.retry_interval, self.shutdown_event)
                        continue
                    try:
                        self.device.grab()
                    except OSError as exc:
                        self._close_device()
                        if not self._is_disconnect(exc):
                            raise
                        continue
                    if self.ui is None:
                        self.ui = UInput(self._capabilities(),
                                        name=f"omus: {self.device.name}")
                    self._start_dpi_worker()
                    LOG.info("Mouse remapping operational")
                    if disconnected:
                        LOG.info("Mouse reconnected at %s", self.device.path)
                        if self.wake_coordinator is not None:
                            self.wake_coordinator.recognized()
                    if not announced:
                        print(f"Remapping: {self.device.name}")
                        print("Press Ctrl+C to stop.")
                        announced = True
                    disconnected = False
                try:
                    readable, _, _ = select.select([self.device.fd], [], [], 0.25)
                    if not readable:
                        continue
                    for event in self.device.read():
                        if (self.wake_coordinator is not None and
                                event.type != ecodes.EV_SYN):
                            self.wake_coordinator.activity("evdev-input")
                        event_timestamp_ns = getattr(event, "timestamp_ns", None)
                        if event_timestamp_ns is None:
                            event_timestamp_ns = (
                                int(event.sec) * 1_000_000_000 + int(event.usec) * 1_000
                            )
                        usable_frame = self._process_event(
                            event.type, event.code, event.value,
                            timestamp_ns=event_timestamp_ns,
                            arrival_ns=time.monotonic_ns(),
                        )
                        if usable_frame and self.wake_coordinator is not None:
                            self.wake_coordinator.runtime_usable()
                except OSError as exc:
                    if not self._is_disconnect(exc):
                        raise
                    self._stop_macros()
                    self._stop_dpi_worker(wait=False)
                    self._pending_frame.clear()
                    self._discard_until_syn_report = False
                    self._release_pressed_keys()
                    self._invalidate_observer_continuity()
                    self._close_device()
                    disconnected = True
                    if self.wake_coordinator is not None:
                        self.wake_coordinator.reconnecting()
                    LOG.warning("Mouse disconnected; waiting for reconnect")
        finally:
            self._stop_macros()
            self._stop_dpi_worker()
            self._pending_frame.clear()
            self._discard_until_syn_report = False
            self._release_pressed_keys()
            self._close_device()
            if self.ui is not None:
                self.ui.close()
                self.ui = None
