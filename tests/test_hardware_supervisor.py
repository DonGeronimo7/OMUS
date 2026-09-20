"""Shared hardware lifecycle and reconnect reconciliation regressions."""

from types import SimpleNamespace
import threading
from unittest.mock import MagicMock, Mock

from mouse_control.discovery import MouseDevice
from mouse_control.hardware import (DesiredHardwareState, HardwareBackend,
                                    HardwareSupervisor)
from mouse_control.hardware.capabilities import BatteryState, DpiState
from mouse_control.hardware.discovery_backend import DiscoveryBackend
from mouse_control.remapper import DpiCycler


G305 = MouseDevice("G305", "/dev/input/test", vendor=0x046d,
                   product=0x4074, bustype=3)


def backend(name="Native HID", *, dpi=800, rate=1000):
    live = {"dpi": dpi, "rate": rate}
    target = MagicMock(spec=HardwareBackend)
    target.name = name
    target.supports_device.return_value = True
    target.supports_polling_rate_writes.return_value = True
    target.get_polling_rate.side_effect = lambda _device: live["rate"]
    target.set_polling_rate.side_effect = lambda _device, value: live.update(rate=value)
    target.supports_dpi_stages.return_value = False
    target.supports_dpi.return_value = True
    target.get_dpi.side_effect = lambda _device: live["dpi"]
    def set_dpi(_device, value):
        live["dpi"] = value
        return DpiState(value, confirmed=True)
    target.set_dpi.side_effect = set_dpi
    target.supports_dpi_events.return_value = True
    target.supports_battery.return_value = True
    target.get_battery_state.return_value = BatteryState(percentage=90)
    return target


def test_startup_and_reconnect_use_identical_desired_state_reconciliation():
    first = backend()
    second = backend(dpi=1500, rate=500)
    desired = DesiredHardwareState(1500, (800, 1500, 2000), 500)
    supervisor = HardwareSupervisor(first, G305, lambda _device: second, desired)

    supervisor.reconcile()
    names = [entry[0] for entry in first.method_calls]
    assert names.index("set_polling_rate") < names.index("set_dpi")
    first.set_polling_rate.assert_called_once_with(G305, 500)
    first.set_dpi.assert_called_once_with(G305, 1500)

    assert supervisor.rebind(expected_generation=0)
    second.set_polling_rate.assert_not_called()
    second.set_dpi.assert_not_called()
    first.close.assert_called_once()
    assert supervisor.current_backend is second
    assert supervisor.generation == 1


def test_stale_rebind_request_cannot_replace_new_backend_twice():
    first, second, third = backend(), backend(), backend()
    replacements = iter((second, third))
    supervisor = HardwareSupervisor(first, G305, lambda _device: next(replacements))
    assert supervisor.rebind(expected_generation=0)
    assert not supervisor.rebind(expected_generation=0)
    assert supervisor.current_backend is second
    third.close.assert_not_called()


def test_many_stale_wake_requests_select_and_reconcile_backend_only_once():
    first, second = backend(), backend()
    factory = Mock(return_value=second)
    supervisor = HardwareSupervisor(first, G305, factory)

    results = [supervisor.rebind(expected_generation=0) for _ in range(10)]

    assert results == [True] + [False] * 9
    factory.assert_called_once_with(G305)
    first.close.assert_called_once()


def test_evdev_observer_never_waits_for_slow_management_rebind() -> None:
    first_observe = Mock()
    second_observe = Mock()
    first = SimpleNamespace(
        name="first", observe_evdev_event=first_observe,
        invalidate_observer_continuity=Mock(), close=Mock(),
    )
    second = SimpleNamespace(
        name="second", observe_evdev_event=second_observe,
        invalidate_observer_continuity=Mock(), close=Mock(),
    )
    discovery_started = threading.Event()
    release_discovery = threading.Event()

    def slow_factory(_device):
        discovery_started.set()
        assert release_discovery.wait(1)
        return second

    supervisor = HardwareSupervisor(first, G305, slow_factory)
    rebind = threading.Thread(target=lambda: supervisor.rebind(0))
    rebind.start()
    assert discovery_started.wait(1)

    input_forwarded = threading.Event()
    input_thread = threading.Thread(target=lambda: (
        supervisor.observe_evdev_event(2, 0, 7), input_forwarded.set()
    ))
    input_thread.start()
    assert input_forwarded.wait(.1), "evdev observer blocked on management discovery"
    first_observe.assert_called_once_with(2, 0, 7)

    release_discovery.set()
    rebind.join(1)
    input_thread.join(1)
    assert not rebind.is_alive()
    supervisor.observe_evdev_event(2, 1, -3)
    second_observe.assert_called_once_with(2, 1, -3)
    first.close.assert_called_once()


def test_old_watcher_callback_is_ignored_after_generation_change():
    first, second = backend(), backend()
    captured = {}

    def retain_callback(_device, callback, _stop, _ready):
        captured["callback"] = callback

    first.watch_dpi_events.side_effect = retain_callback
    supervisor = HardwareSupervisor(first, G305, lambda _device: second)
    delivered = MagicMock()
    supervisor.watch_dpi_events(G305, delivered, MagicMock())

    assert supervisor.rebind(0)
    captured["callback"](DpiState(1500, confirmed=True))

    delivered.assert_not_called()


def test_dpi_battery_and_events_all_follow_the_current_backend():
    first, second = backend(dpi=800), backend(dpi=1500)
    supervisor = HardwareSupervisor(first, G305, lambda _device: second)
    cycler = DpiCycler(supervisor, G305, [800, 1500], 800, notifier=MagicMock())

    supervisor.rebind(0)
    assert cycler.cycle()
    assert supervisor.desired.active_dpi == 800
    second.set_dpi.assert_called_once_with(G305, 800)
    first.set_dpi.assert_not_called()
    assert supervisor.get_battery_state(G305) == BatteryState(percentage=90)
    second.get_battery_state.assert_called_once_with(G305)

    callback, stop = MagicMock(), MagicMock()
    supervisor.watch_dpi_events(G305, callback, stop)
    second.watch_dpi_events.assert_called_once()
    watched_device, guarded_callback, watched_stop, ready = (
        second.watch_dpi_events.call_args.args)
    assert watched_device == G305
    assert guarded_callback is not callback
    assert watched_stop is stop
    assert ready is None


def test_reconnect_reapplies_last_successful_runtime_dpi():
    first, second = backend(dpi=800), backend(dpi=800)
    supervisor = HardwareSupervisor(
        first, G305, lambda _device: second,
        DesiredHardwareState(active_dpi=800, dpi_stages=(800, 1500)))
    cycler = DpiCycler(supervisor, G305, [800, 1500], 800, notifier=MagicMock())
    assert cycler.cycle()
    supervisor.rebind(0)
    second.set_dpi.assert_called_once_with(G305, 1500)
    assert supervisor.get_dpi(G305) == 1500


def test_shutdown_closes_current_backend_exactly_once():
    target = backend()
    supervisor = HardwareSupervisor(target, G305, lambda _device: backend())
    supervisor.close()
    supervisor.close()
    target.close.assert_called_once()


def test_rebind_updates_device_identity_used_by_existing_consumers():
    configured = MouseDevice("G305", "/dev/input/stable", vendor=0x046d,
                             product=0x4074)
    resolved = MouseDevice("G305", "/dev/input/event9", phys="usb-new",
                           vendor=0x046d, product=0x4074, bustype=3)
    first, second = backend(), backend()
    supervisor = HardwareSupervisor(
        first, configured, lambda device: second,
        device_resolver=lambda _old: resolved, discovery_pending=True)
    supervisor.rebind(0)
    supervisor.get_dpi(configured)
    second.get_dpi.assert_called_with(resolved)
    assert supervisor.device == resolved
    assert not supervisor.discovery_pending


def discovery_backend(kind, *, name="Native HID"):
    target = DiscoveryBackend(protocol_factories=())
    target.close = MagicMock()
    if kind == "native":
        target._protocol_backend = SimpleNamespace(name=name)
    elif kind == "learned":
        target._learned_operation = object()
    return target


def test_reconnect_waits_for_previous_native_during_asynchronous_member_arrival():
    """Partial enumeration must not reconcile through a weaker learned writer."""
    native_before = discovery_backend("native")
    native_after = discovery_backend("native")
    learned_candidates = [discovery_backend("learned") for _ in range(3)]
    for candidate in learned_candidates:
        candidate.supports_dpi = MagicMock(return_value=True)
        candidate.set_dpi = MagicMock()
    native_after.supports_dpi_stages = MagicMock(return_value=False)
    native_after.supports_dpi = MagicMock(return_value=True)
    native_after.set_dpi = MagicMock(return_value=DpiState(1000, confirmed=True))
    native_after.get_dpi = MagicMock(return_value=1000)
    replacements = iter((*learned_candidates, native_after))
    supervisor = HardwareSupervisor(
        native_before,
        G305,
        lambda _device: next(replacements),
        DesiredHardwareState(active_dpi=1000),
    )

    for candidate in learned_candidates:
        assert not supervisor.rebind(0, force=True)
        assert supervisor.current_backend is native_before
        candidate.set_dpi.assert_not_called()
        candidate.close.assert_called_once()
        assert supervisor.generation == 0

    assert supervisor.rebind(0, force=True)
    assert supervisor.current_backend is native_after
    assert supervisor.generation == 1
    assert not supervisor.discovery_pending
    native_after.set_dpi.assert_not_called()
    native_before.close.assert_called_once()


def test_reconnect_preserves_proven_learned_affinity_until_learned_members_return():
    learned_before = discovery_backend("learned")
    topology_only = discovery_backend("plain")
    learned_after = discovery_backend("learned")
    replacements = iter((topology_only, learned_after))
    supervisor = HardwareSupervisor(
        learned_before, G305, lambda _device: next(replacements))

    assert not supervisor.rebind(0, force=True)
    assert supervisor.current_backend is learned_before
    assert supervisor.discovery_pending
    assert supervisor.generation == 0
    topology_only.close.assert_called_once()

    assert supervisor.rebind(0, force=True)
    assert supervisor.current_backend is learned_after
    assert not supervisor.discovery_pending
    assert supervisor.generation == 1
    learned_before.close.assert_called_once()


def test_cold_learned_fallback_keeps_failed_protocol_discovery_pending_without_rewrites():
    first, repeated, native = (discovery_backend('learned'), discovery_backend('learned'),
                               discovery_backend('native'))
    first.discovery_pending = repeated.discovery_pending = True
    repeated.set_dpi = MagicMock()
    replacements = iter([repeated, native])
    supervisor = HardwareSupervisor(first, G305, lambda _: next(replacements))
    supervisor._reconcile_backend = MagicMock()
    assert supervisor.discovery_pending
    assert not supervisor.rebind(0)
    assert supervisor.discovery_pending
    assert supervisor.generation == 0
    supervisor._reconcile_backend.assert_not_called()
    repeated.close.assert_called_once()
    assert supervisor.rebind(0)
    assert supervisor.current_backend is native
    assert not supervisor.discovery_pending
    assert supervisor.generation == 1
