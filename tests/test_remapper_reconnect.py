"""Deterministic evdev reconnect lifecycle regression tests."""

import errno
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from evdev import ecodes
from mouse_control.discovery import MouseDevice
from mouse_control import remapper as module
from mouse_control.runtime_wake import RuntimeWakeCoordinator, RuntimeWakeState


TARGET = MouseDevice("G305", "/dev/input/by-id/g305-event-mouse",
                     phys="usb-1", vendor=0x046D, product=0x4074, bustype=3)


def device(path, events=()):
    result = MagicMock(path=path, fd=9, name="G305")
    result.capabilities.return_value = {ecodes.EV_KEY: [], ecodes.EV_REL: []}
    result.read.return_value = list(events)
    return result


def test_enodev_read_closes_stale_device_and_rebinds_stable_path():
    old = device("/dev/input/event5")
    new = device("/dev/input/event8", [
        MagicMock(type=ecodes.EV_KEY, code=ecodes.BTN_EXTRA, value=1),
        MagicMock(type=ecodes.EV_KEY, code=ecodes.BTN_TASK, value=1),
        MagicMock(type=ecodes.EV_SYN, code=ecodes.SYN_REPORT, value=0),
    ])
    old.read.side_effect = OSError(errno.ENODEV, "No such device")
    stop = threading.Event()
    cycler = MagicMock()
    cycled = threading.Event()
    cycler.cycle.side_effect = lambda: cycled.set() or True
    remapper = module.MouseRemapper(
        TARGET.path, {"BTN_EXTRA": "key:KEY_F13", "BTN_TASK": "dpi-cycle"}, stop,
        dpi_cycler=cycler, target_device=TARGET, retry_interval=0)
    ui = MagicMock()

    selections = 0

    def selected(*_args):
        nonlocal selections
        selections += 1
        if selections >= 3:
            assert cycled.wait(1)
            stop.set()
        return [9], [], []

    with patch.object(module, "InputDevice", side_effect=[old, new]) as factory, \
         patch.object(module, "UInput", return_value=ui), \
         patch.object(module.select, "select", side_effect=selected), \
         patch.object(module.signal, "signal"):
        remapper.run()

    assert factory.call_args_list[0].args == (TARGET.path,)
    assert factory.call_args_list[1].args == (TARGET.path,)
    old.close.assert_called_once()
    new.grab.assert_called_once()
    ui.write.assert_any_call(ecodes.EV_KEY, ecodes.KEY_F13, 1)
    cycler.cycle.assert_called_once()


def test_disconnect_releases_held_chord_before_retry():
    old = device("/dev/input/event5", [
        MagicMock(type=ecodes.EV_KEY, code=ecodes.BTN_EXTRA, value=1),
        MagicMock(type=ecodes.EV_SYN, code=ecodes.SYN_REPORT, value=0),
    ])
    old.read.side_effect = [old.read.return_value, OSError(errno.ENODEV, "disconnected")]
    stop = threading.Event()
    stop.wait = MagicMock(side_effect=lambda _interval: stop.set())
    remapper = module.MouseRemapper(
        TARGET.path, {"BTN_EXTRA": "chord:KEY_LEFTCTRL+KEY_S"}, stop,
        target_device=TARGET, retry_interval=0)
    ui = MagicMock()
    with patch.object(module, "InputDevice", side_effect=[old, OSError(errno.ENODEV, "missing")]), \
         patch.object(module, "UInput", return_value=ui), \
         patch.object(module.select, "select", return_value=([9], [], [])), \
         patch.object(module.signal, "signal"):
        remapper.run()
    assert [entry.args for entry in ui.write.call_args_list] == [
        (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
        (ecodes.EV_KEY, ecodes.KEY_S, 1),
        (ecodes.EV_KEY, ecodes.KEY_S, 0),
        (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
    ]
    assert not remapper._held_chords


def test_fallback_rebinds_single_matching_device_and_rejects_ambiguity():
    target = MouseDevice("G305", "/dev/input/event5", phys="usb-1",
                         vendor=0x046D, product=0x4074, bustype=3)
    matching = MouseDevice("G305", "/dev/input/event8", phys="usb-1",
                           vendor=0x046D, product=0x4074, bustype=3)
    remapper = module.MouseRemapper(target.path, {}, target_device=target)
    reopened = device(matching.path)
    with patch.object(module, "get_mouse_devices", return_value=[matching]), \
         patch.object(module, "InputDevice", return_value=reopened) as factory:
        assert remapper._acquire_device() is reopened
    factory.assert_called_once_with(matching.path)

    with patch.object(module, "get_mouse_devices", return_value=[matching, matching]), \
         patch.object(module, "InputDevice") as factory:
        assert remapper._acquire_device() is None
    factory.assert_not_called()


def test_reconnect_accepts_unique_vid_pid_when_event_node_and_phys_change():
    target = MouseDevice("G305", "/dev/input/event5", phys="usb-old",
                         vendor=0x046D, product=0x4074, bustype=3)
    reconnected = MouseDevice("G305", "/dev/input/event8", phys="usb-new",
                              vendor=0x046D, product=0x4074, bustype=3)
    remapper = module.MouseRemapper(target.path, {}, target_device=target)
    with patch.object(module, "get_mouse_devices", return_value=[reconnected]), \
         patch.object(module, "InputDevice", return_value=device(reconnected.path)) as factory:
        assert remapper._acquire_device() is not None
    factory.assert_called_once_with(reconnected.path)

    second = MouseDevice("G305", "/dev/input/event9", phys="usb-other",
                         vendor=0x046D, product=0x4074, bustype=3)
    with patch.object(module, "get_mouse_devices", return_value=[reconnected, second]), \
         patch.object(module, "InputDevice") as factory:
        assert remapper._acquire_device() is None
    factory.assert_not_called()


def test_shutdown_while_disconnected_does_not_open_or_wait_forever():
    stop = threading.Event()
    stop.set()
    remapper = module.MouseRemapper(TARGET.path, {}, stop, target_device=TARGET,
                                    retry_interval=10)
    with patch.object(module, "InputDevice") as factory, \
         patch.object(module.signal, "signal"):
        remapper.run()
    factory.assert_not_called()


def test_ten_reconnect_cycles_preserve_first_frame_mapping_and_syn_boundary():
    stop = threading.Event()
    physical_frames = [
        [
            MagicMock(type=ecodes.EV_REL, code=ecodes.REL_X, value=index + 1),
            MagicMock(type=ecodes.EV_REL, code=ecodes.REL_Y, value=-(index + 2)),
            MagicMock(type=ecodes.EV_KEY, code=ecodes.BTN_EXTRA, value=1),
            MagicMock(type=ecodes.EV_KEY, code=ecodes.BTN_EXTRA, value=0),
            MagicMock(type=ecodes.EV_SYN, code=ecodes.SYN_REPORT, value=0),
        ]
        for index in range(11)
    ]
    devices = []
    for index, events in enumerate(physical_frames):
        current = device(f"/dev/input/event{index + 5}")
        if index < 10:
            current.read.side_effect = [events, OSError(errno.ENODEV, "sleep")]
        else:
            current.read.side_effect = lambda events=events: stop.set() or events
        devices.append(current)

    wake = RuntimeWakeCoordinator(quiescent_after=0)
    remapper = module.MouseRemapper(
        TARGET.path, {"BTN_EXTRA": "key:KEY_F13"}, stop,
        target_device=TARGET, retry_interval=60, wake_coordinator=wake,
    )
    ui = MagicMock()
    with patch.object(module, "InputDevice", side_effect=devices) as factory, \
         patch.object(module, "UInput", return_value=ui), \
         patch.object(module.select, "select", return_value=([9], [], [])), \
         patch.object(module.signal, "signal"):
        remapper.run()

    assert factory.call_count == 11
    assert ui.syn.call_count == 11
    assert [entry.args for entry in ui.write.call_args_list] == [
        output
        for index in range(11)
        for output in (
            (ecodes.EV_REL, ecodes.REL_X, index + 1),
            (ecodes.EV_REL, ecodes.REL_Y, -(index + 2)),
            (ecodes.EV_KEY, ecodes.KEY_F13, 1),
            (ecodes.EV_KEY, ecodes.KEY_F13, 0),
        )
    ]
    assert not remapper._pressed_keys
    assert wake.state is RuntimeWakeState.ACTIVE
