# SPDX-License-Identifier: AGPL-3.0-or-later
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from evdev import InputEvent, ecodes

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from mouse_control import keyboard_capture as capture
from mouse_control.config import generate_config
from mouse_control.discovery import MouseDevice
from mouse_control.remapper import parse_action


def event(code, value=1, kind=ecodes.EV_KEY):
    return InputEvent(0, 0, kind, code, value)


def device(fd=10, batches=(), held=()):
    dev = MagicMock()
    dev.fd = fd
    dev.name = "Test keyboard"
    dev.active_keys.return_value = held
    dev.read.side_effect = [BlockingIOError(), *batches]
    dev.capabilities.return_value = {ecodes.EV_KEY: [ecodes.KEY_A]}
    return dev


def run_capture(devices, ready=None, capture_function=None):
    selector = ready or (lambda *_args, **_kwargs: (devices[:], [], []))
    with patch.object(capture, '_open_keyboards', return_value=devices), \
         patch.object(capture, '_capture_terminal', return_value=nullcontext()), \
         patch.object(capture, 'select', side_effect=selector):
        return (capture_function or capture.capture_keyboard_key)()


def test_chord_capture_holds_keys_until_all_released():
    dev = device(batches=[[
        event(ecodes.KEY_LEFTCTRL), event(ecodes.KEY_LEFTSHIFT), event(ecodes.KEY_S),
        event(ecodes.KEY_S, 2), event(ecodes.KEY_S, 0),
        event(ecodes.KEY_LEFTSHIFT, 0), event(ecodes.KEY_LEFTCTRL, 0)]])
    assert run_capture([dev], capture_function=capture.capture_keyboard_chord) == (
        'chord:KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_S')
    dev.grab.assert_called_once()
    dev.ungrab.assert_called_once()
    dev.close.assert_called_once()


def test_chord_capture_ignores_stale_and_one_key_attempts():
    dev = device(held=[ecodes.KEY_ENTER], batches=[
        [event(ecodes.KEY_ENTER, 0)],
        [event(ecodes.KEY_A), event(ecodes.KEY_A, 0),
         event(ecodes.KEY_LEFTCTRL), event(ecodes.KEY_C),
         event(ecodes.KEY_C, 0), event(ecodes.KEY_LEFTCTRL, 0)],
    ])
    assert run_capture([dev], capture_function=capture.capture_keyboard_chord) == (
        'chord:KEY_LEFTCTRL+KEY_C')
    dev.grab.assert_called_once()
    dev.ungrab.assert_called_once()


def test_chord_capture_escape_and_disconnect_close_devices():
    first = device(10, [OSError('unplugged')])
    second = device(11, [[event(ecodes.KEY_ESC)]])
    assert run_capture([first, second], capture_function=capture.capture_keyboard_chord) is None
    first.grab.assert_called_once()
    second.grab.assert_called_once()
    first.ungrab.assert_called_once()
    second.ungrab.assert_called_once()
    first.close.assert_called_once()
    second.close.assert_called_once()


@pytest.mark.parametrize('code,name', [(ecodes.KEY_LEFTMETA, 'KEY_LEFTMETA'),
                                      (ecodes.KEY_F12, 'KEY_F12'),
                                      (ecodes.KEY_VOLUMEUP, 'KEY_VOLUMEUP')])
def test_capture_compatible_with_existing_config(code, name):
    dev = device(batches=[[event(code)]])
    assert run_capture([dev]) == name
    assert parse_action(f'key:{name}').code == code
    assert f'key:{name}' in generate_config(MouseDevice('Mouse', '/dev/input/test'),
                                           {'BTN_EXTRA': f'key:{name}'})
    dev.grab.assert_called_once()
    dev.ungrab.assert_called_once()
    dev.close.assert_called_once()


def test_print_screen_is_captured_exclusively():
    dev = device(batches=[[event(ecodes.KEY_SYSRQ)]])
    assert run_capture([dev]) == capture.keyboard_key_name(ecodes.KEY_SYSRQ)
    dev.grab.assert_called_once()
    dev.ungrab.assert_called_once()


def test_super_shift_s_is_captured_exclusively():
    dev = device(batches=[[
        event(ecodes.KEY_LEFTMETA), event(ecodes.KEY_LEFTSHIFT), event(ecodes.KEY_S),
        event(ecodes.KEY_S, 0), event(ecodes.KEY_LEFTSHIFT, 0),
        event(ecodes.KEY_LEFTMETA, 0),
    ]])
    assert run_capture([dev], capture_function=capture.capture_keyboard_chord) == (
        'chord:KEY_LEFTMETA+KEY_LEFTSHIFT+KEY_S')
    dev.grab.assert_called_once()
    dev.ungrab.assert_called_once()


def test_filters_events_and_menu_enter():
    dev = device(held=[ecodes.KEY_ENTER], batches=[
        [event(ecodes.KEY_ENTER, 0)],
        [event(ecodes.KEY_A, 0), event(ecodes.KEY_A, 2), event(ecodes.BTN_LEFT),
         event(99999), event(0, kind=ecodes.EV_SYN), event(ecodes.KEY_F12)],
    ])
    assert run_capture([dev]) == 'KEY_F12'


def test_queued_enter_is_drained_but_fresh_enter_can_be_bound():
    dev = device()
    dev.read.side_effect = [[event(ecodes.KEY_ENTER)], BlockingIOError(), [event(ecodes.KEY_ENTER)]]
    assert run_capture([dev]) == 'KEY_ENTER'
    dev.grab.assert_called_once()
    dev.ungrab.assert_called_once()


def test_held_key_release_happens_before_exclusive_grab():
    dev = device(held=[ecodes.KEY_ENTER], batches=[
        [event(ecodes.KEY_ENTER, 0)], [event(ecodes.KEY_A)],
    ])
    order = []
    dev.grab.side_effect = lambda: order.append('grab')

    dev.read.side_effect = None
    queued = [BlockingIOError(), [event(ecodes.KEY_ENTER, 0)], [event(ecodes.KEY_A)]]

    def ordered_read():
        value = queued.pop(0)
        if isinstance(value, BaseException):
            raise value
        order.append('read')
        return value

    dev.read.side_effect = ordered_read
    assert run_capture([dev]) == 'KEY_A'
    assert order.index('read') < order.index('grab')


def test_multiple_keyboards_disconnect_and_cleanup():
    first = device(10, [OSError('unplugged')])
    second = device(11, [[event(ecodes.KEY_VOLUMEUP)]])
    assert run_capture([first, second]) == 'KEY_VOLUMEUP'
    first.grab.assert_called_once()
    second.grab.assert_called_once()
    first.ungrab.assert_called_once()
    second.ungrab.assert_called_once()
    first.close.assert_called_once()
    second.close.assert_called_once()


@pytest.mark.parametrize('failure', [KeyboardInterrupt(), OSError('unplugged')])
def test_cancel_or_disconnect(failure):
    dev = device(batches=[failure])
    assert run_capture([dev]) is None
    dev.grab.assert_called_once()
    dev.ungrab.assert_called_once()
    dev.close.assert_called_once()


def test_exception_after_grab_still_ungrabs_and_closes():
    dev = device()
    with patch.object(capture, '_open_keyboards', return_value=[dev]), \
         patch.object(capture, '_capture_terminal', return_value=nullcontext()), \
         patch.object(capture, 'select', side_effect=RuntimeError('boom')), \
         pytest.raises(RuntimeError, match='boom'):
        capture.capture_keyboard_key()
    dev.grab.assert_called_once()
    dev.ungrab.assert_called_once()
    dev.close.assert_called_once()


def test_partial_multi_device_grab_failure_rolls_back(capsys):
    first = device(10)
    second = device(11)
    second.grab.side_effect = OSError(16, 'Device or resource busy')
    assert run_capture([first, second]) is None
    first.grab.assert_called_once()
    second.grab.assert_called_once()
    first.ungrab.assert_called_once()
    second.ungrab.assert_not_called()
    first.close.assert_called_once()
    second.close.assert_called_once()
    output = capsys.readouterr().out
    assert 'Safe keyboard capture is unavailable' in output
    assert 'No shortcut was recorded' in output
    assert 'option 5' in output


def test_chord_grab_failure_uses_manual_fallback(capsys):
    dev = device()
    dev.grab.side_effect = OSError(16, 'Device or resource busy')
    assert run_capture([dev], capture_function=capture.capture_keyboard_chord) is None
    dev.ungrab.assert_not_called()
    dev.close.assert_called_once()
    assert 'option 7' in capsys.readouterr().out


def test_ctrl_c_and_ctrl_alone():
    dev = device(batches=[[event(ecodes.KEY_LEFTCTRL), event(ecodes.KEY_C)]])
    assert run_capture([dev]) is None
    dev.ungrab.assert_called_once()
    dev = device(batches=[[event(ecodes.KEY_LEFTCTRL), event(ecodes.KEY_LEFTCTRL, 0)]])
    assert run_capture([dev]) == 'KEY_LEFTCTRL'
    dev.ungrab.assert_called_once()


def test_no_devices():
    assert run_capture([]) is None


def test_aliases_and_unknown_codes():
    with patch.dict(ecodes.bytype[ecodes.EV_KEY], {ecodes.KEY_F12: ['BTN_FAKE', 'KEY_F12']}):
        assert capture.keyboard_key_name(ecodes.KEY_F12) == 'KEY_F12'
    assert capture.keyboard_key_name(ecodes.BTN_LEFT) is None
    assert capture.keyboard_key_name(99999) is None
    assert capture.keyboard_key_name(ecodes.KEY_RESERVED) is None


def test_discovery_prefers_stable_paths_and_skips_duplicates_and_inaccessible():
    paths = ['/dev/input/event1', '/dev/input/by-id/test-event-kbd', '/dev/input/event2',
             '/dev/input/event3', '/dev/input/event4']
    keyboard, mouse, virtual = device(), device(), device()
    mouse.capabilities.return_value = {ecodes.EV_KEY: [ecodes.BTN_LEFT]}
    virtual.name = 'mouse-control: Test'
    def realpath(path):
        return '/dev/input/event1' if path.endswith('event-kbd') else path
    with patch.object(capture, '_iter_candidate_paths', return_value=paths), \
         patch.object(capture.os.path, 'realpath', side_effect=realpath), \
         patch.object(capture, 'InputDevice', side_effect=[keyboard, PermissionError(), mouse, virtual]) as opened:
        assert capture._open_keyboards() == [keyboard]
    assert opened.call_args_list[0].args == ('/dev/input/by-id/test-event-kbd',)
    assert opened.call_count == 4
    mouse.close.assert_called_once()
    virtual.close.assert_called_once()
    keyboard.close.assert_not_called()


def test_terminal_restored_and_buffer_flushed_on_cancel():
    settings = [0, 0, 0, capture.termios.ICANON | capture.termios.ECHO | capture.termios.ISIG, 0, 0, []]
    with patch.object(capture.sys, 'stdin') as stdin, \
         patch.object(capture.termios, 'tcgetattr', side_effect=lambda fd: settings.copy()), \
         patch.object(capture.termios, 'tcsetattr') as setter:
        stdin.isatty.return_value = True
        stdin.fileno.return_value = 0
        with pytest.raises(KeyboardInterrupt), capture._capture_terminal():
            raise KeyboardInterrupt
    assert setter.call_args_list[0].args[2][3] == capture.termios.ISIG
    assert setter.call_args_list[-1].args == (0, capture.termios.TCSAFLUSH, settings)


def test_chord_terminal_allows_ctrl_c_and_restores_signals():
    settings = [0, 0, 0, capture.termios.ICANON | capture.termios.ECHO | capture.termios.ISIG,
                0, 0, []]
    with patch.object(capture.sys, 'stdin') as stdin, \
         patch.object(capture.termios, 'tcgetattr', side_effect=lambda fd: settings.copy()), \
         patch.object(capture.termios, 'tcsetattr') as setter:
        stdin.isatty.return_value = True
        stdin.fileno.return_value = 0
        with capture._capture_terminal(keep_signals=False):
            pass
    assert not setter.call_args_list[0].args[2][3] & capture.termios.ISIG
    assert setter.call_args_list[-1].args == (0, capture.termios.TCSAFLUSH, settings)
