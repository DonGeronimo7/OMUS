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
    ])
    old.read.side_effect = OSError(errno.ENODEV, "No such device")
    stop = threading.Event()
    cycler = MagicMock()
    remapper = module.MouseRemapper(
        TARGET.path, {"BTN_EXTRA": "key:KEY_F13", "BTN_TASK": "dpi-cycle"}, stop,
        dpi_cycler=cycler, target_device=TARGET, retry_interval=0)
    ui = MagicMock()

    def selected(*_args):
        if old.read.call_count:
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
