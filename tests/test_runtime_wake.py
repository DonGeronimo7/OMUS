"""Deterministic near-zero-latency wake-path regressions."""

import threading
import time
from unittest.mock import Mock

from mouse_control.battery import BatteryMonitorSupervisor
from mouse_control.discovery import MouseDevice
from mouse_control.hardware.capabilities import DpiState
from mouse_control.hardware.supervisor import HardwareSupervisor
from mouse_control.notifications import DpiMonitorSupervisor
from mouse_control.runtime_wake import (
    LinuxDeviceEventMonitor,
    RuntimeWakeCoordinator,
    RuntimeWakeState,
    WakeLatencyRecorder,
    _uevent_matches,
)


MOUSE = MouseDevice("G305", "/dev/input/event5", vendor=0x046D,
                    product=0x4074, bustype=3)


def event_backend():
    backend = Mock(name="known native backend")
    backend.name = "Native HID"
    backend.supports_dpi_events.return_value = True
    return backend


def test_known_quiescent_hid_event_reuses_session_without_discovery():
    clock = iter((0, 31_000_000_000, 31_001_000_000, 31_002_000_000))
    wake = RuntimeWakeCoordinator(quiescent_after=30, clock_ns=lambda: next(clock))
    backend = event_backend()
    factory = Mock()
    supervisor = HardwareSupervisor(
        backend, MOUSE, factory, wake_coordinator=wake)
    delivered = Mock()

    def one_event(_device, callback, stop, ready):
        ready()
        callback(DpiState(1500, confirmed=True))
        stop.set()

    backend.watch_dpi_events.side_effect = one_event
    supervisor.watch_dpi_events(MOUSE, delivered, threading.Event(), Mock())

    factory.assert_not_called()
    backend.close.assert_not_called()
    delivered.assert_called_once()
    assert supervisor.current_backend is backend
    assert supervisor.generation == 0
    assert wake.state is RuntimeWakeState.ACTIVE
    assert len(wake.recorder.samples) == 1


def test_matching_device_return_cancels_long_reconnect_backoff():
    unavailable = Mock(name="sleeping backend")
    attempted = threading.Event()

    def not_ready(_device):
        attempted.set()
        raise OSError("receiver absent")

    unavailable.supports_dpi_events.side_effect = not_ready
    ready = event_backend()
    shutdown = threading.Event()

    def deliver(_device, _callback, stop, ready_callback):
        ready_callback()
        stop.set()

    ready.watch_dpi_events.side_effect = deliver
    wake = RuntimeWakeCoordinator()
    factory = Mock(return_value=ready)
    supervisor = DpiMonitorSupervisor(
        unavailable, MOUSE, factory, [800], 800, shutdown, Mock(),
        retry_interval=60, wake_coordinator=wake)

    started = time.monotonic()
    supervisor.start()
    assert attempted.wait(1)
    wake.device_event("device-return")
    supervisor._thread.join(1)

    assert not supervisor._thread.is_alive()
    assert time.monotonic() - started < 1
    factory.assert_called_once_with(MOUSE)
    ready.watch_dpi_events.assert_called_once()


def test_unrelated_or_changed_interface_event_does_not_match_exact_identity():
    exact_input = (
        b"add@/devices/x\0ACTION=add\0SUBSYSTEM=input\0"
        b"PRODUCT=3/46d/4074/111\0"
    )
    exact_hid = (
        b"change@/devices/x\0ACTION=change\0SUBSYSTEM=hidraw\0"
        b"HID_ID=0003:0000046D:00004074\0"
    )
    changed_product = exact_input.replace(b"4074", b"4075")
    removed = exact_input.replace(b"ACTION=add", b"ACTION=remove")

    assert _uevent_matches(exact_input, MOUSE)
    assert _uevent_matches(exact_hid, MOUSE)
    assert not _uevent_matches(changed_product, MOUSE)
    assert not _uevent_matches(removed, MOUSE)


def test_linux_device_monitor_blocks_for_events_and_emits_matching_timestamp():
    event = (
        b"add@/devices/x\0ACTION=add\0SUBSYSTEM=input\0"
        b"PRODUCT=3/46d/4074/111\0"
    )
    sock = Mock()
    sock.recv.return_value = event
    observed = []
    monitor = None

    def callback(source, timestamp_ns):
        observed.append((source, timestamp_ns))
        monitor._stop.set()

    monitor = LinuxDeviceEventMonitor(
        MOUSE, callback, socket_factory=Mock(return_value=sock),
        clock_ns=lambda: 1234)
    monitor._run()

    sock.bind.assert_called_once_with((0, 3))
    sock.settimeout.assert_called_once_with(1.)
    sock.recv.assert_called_once_with(8192)
    sock.close.assert_called_once()
    assert observed == [("device-return", 1234)]


def test_latency_instrumentation_reports_repeated_min_median_p95_and_max():
    recorder = WakeLatencyRecorder()
    for start, duration_ms in ((0, 1), (10_000_000, 2),
                               (20_000_000, 3), (30_000_000, 20)):
        recorder.begin("fixture", start)
        recorder.recognized(start + 100_000)
        recorder.backend_usable(start + 500_000)
        recorder.runtime_usable(start + duration_ms * 1_000_000)

    summary = recorder.summary()
    assert summary["t0_to_t1"] == {
        "minimum_ms": .1, "median_ms": .1, "p95_ms": .1,
        "p99_ms": .1, "maximum_ms": .1,
    }
    assert summary["t0_to_t2"] == {
        "minimum_ms": .5, "median_ms": .5, "p95_ms": .5,
        "p99_ms": .5, "maximum_ms": .5,
    }
    assert summary["t0_to_t3"] == {
        "minimum_ms": 1., "median_ms": 2.5, "p95_ms": 20.,
        "p99_ms": 20., "maximum_ms": 20.,
    }


def test_first_input_and_full_management_ready_are_recorded_independently():
    recorder = WakeLatencyRecorder()
    wake = RuntimeWakeCoordinator(clock_ns=lambda: 0, recorder=recorder)

    wake.management_unavailable()
    wake.activity("evdev-input", 31_000_000_000)
    wake.runtime_usable(31_001_000_000)

    assert recorder.samples == ()
    wake.backend_usable(31_020_000_000)

    sample = recorder.samples[0]
    assert sample.durations_ms() == (0.0, 20.0, 1.0)


def test_management_unavailability_does_not_turn_input_unavailable_or_storm_retries():
    wake = RuntimeWakeCoordinator(clock_ns=lambda: 0)

    wake.management_unavailable()
    assert wake.state is RuntimeWakeState.ACTIVE
    generation = wake.generation

    wake.activity("first-wake-input", 31_000_000_000)
    assert wake.generation == generation + 1
    for offset in range(1, 101):
        wake.management_unavailable()
        wake.activity("rapid-input", 31_000_000_000 + offset * 1_000_000)

    assert wake.state is RuntimeWakeState.ACTIVE
    assert wake.generation == generation + 1


def test_shutdown_interrupts_event_driven_wait_without_polling():
    wake = RuntimeWakeCoordinator()
    shutdown = threading.Event()
    returned = threading.Event()
    results = []

    def waiter():
        results.append(wake.wait(wake.generation, 60, shutdown))
        returned.set()

    thread = threading.Thread(target=waiter)
    thread.start()
    shutdown.set()
    wake.stop()
    assert returned.wait(1)
    thread.join(1)
    assert results == [False]


def test_stopping_coordinator_ignores_late_wake_evidence():
    wake = RuntimeWakeCoordinator()
    generation = wake.generation

    wake.stop()
    wake.device_event("late-device-return")
    wake.activity("late-input")

    assert wake.state is RuntimeWakeState.STOPPING
    assert wake.generation == generation + 1


def test_stopping_coordinator_ends_dpi_and_battery_retry_loops_without_rebind():
    wake = RuntimeWakeCoordinator()
    shutdown = threading.Event()
    dpi_attempted = threading.Event()
    battery_attempted = threading.Event()
    dpi_backend = Mock(discovery_pending=True)
    battery_backend = Mock(discovery_pending=True)
    dpi_backend.supports_dpi_events.side_effect = (
        lambda _device: dpi_attempted.set() or False
    )
    dpi_backend.supports_dpi_monitoring.return_value = False
    battery_backend.supports_battery.side_effect = (
        lambda _device: battery_attempted.set() or False
    )
    dpi_factory = Mock()
    battery_factory = Mock()
    dpi = DpiMonitorSupervisor(
        dpi_backend, MOUSE, dpi_factory, [800], 800, shutdown, Mock(),
        retry_interval=60, wake_coordinator=wake,
    )
    battery = BatteryMonitorSupervisor(
        battery_backend, MOUSE, battery_factory, shutdown, tray=Mock(),
        interval=60, retry_interval=60, wake_coordinator=wake,
    )

    dpi.start()
    battery.start()
    assert dpi_attempted.wait(1)
    assert battery_attempted.wait(1)
    wake.stop()
    dpi._thread.join(1)
    battery._thread.join(1)

    assert not dpi._thread.is_alive()
    assert not battery._thread.is_alive()
    dpi_factory.assert_not_called()
    battery_factory.assert_not_called()
