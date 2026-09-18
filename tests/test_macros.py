"""Structured macro parsing, playback, cleanup, and configuration tests."""

import tomllib
from unittest.mock import MagicMock, call, patch

import pytest
from evdev import ecodes

from mouse_control.config import merge_setup_config
from mouse_control.discovery import MouseDevice
from mouse_control.remapper import MouseRemapper, parse_action, parse_macros


MACROS = {
    "copy_paste": [
        {"type": "chord", "value": "KEY_LEFTCTRL+KEY_C"},
        {"type": "delay", "milliseconds": 100},
        {"type": "chord", "value": "KEY_LEFTCTRL+KEY_V"},
    ],
    "game": [
        {"type": "key", "value": "KEY_1"},
        {"type": "mouse", "value": "BTN_LEFT"},
    ],
}


def target(macros=MACROS, mappings=None):
    result = MouseRemapper(
        "/dev/input/test", mappings or {"BTN_EXTRA": "macro:copy_paste"}, macros=macros
    )
    result.ui = MagicMock()
    result.device = MagicMock()
    result.device.capabilities.return_value = {ecodes.EV_KEY: [], ecodes.EV_REL: []}
    return result


def test_macro_steps_reuse_key_chord_mouse_actions_in_order_and_interpret_delay():
    result = target()
    waits = []
    result._macro_cancel.wait = lambda seconds: waits.append(seconds) or False

    result._play_macro(parse_macros(MACROS)["copy_paste"])
    result._play_macro(parse_macros(MACROS)["game"])

    assert waits == [0.1]
    assert result.ui.write.call_args_list == [
        call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
        call(ecodes.EV_KEY, ecodes.KEY_C, 1),
        call(ecodes.EV_KEY, ecodes.KEY_C, 0),
        call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
        call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
        call(ecodes.EV_KEY, ecodes.KEY_V, 1),
        call(ecodes.EV_KEY, ecodes.KEY_V, 0),
        call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
        call(ecodes.EV_KEY, ecodes.KEY_1, 1),
        call(ecodes.EV_KEY, ecodes.KEY_1, 0),
        call(ecodes.EV_KEY, ecodes.BTN_LEFT, 1),
        call(ecodes.EV_KEY, ecodes.BTN_LEFT, 0),
    ]
    assert not result._pressed_keys


def test_macro_failure_releases_every_key_pressed_by_the_failed_step():
    result = target()
    failed = False

    def write(event_type, code, value):
        nonlocal failed
        if code == ecodes.KEY_C and value == 1 and not failed:
            failed = True
            raise OSError("uinput failed")

    result.ui.write.side_effect = write
    with pytest.raises(OSError):
        result._tap_action(parse_action("chord:KEY_LEFTCTRL+KEY_C"))

    assert call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0) in result.ui.write.call_args_list
    assert not result._pressed_keys


def test_macro_does_not_release_key_already_held_by_ordinary_mapping():
    result = target()
    result._pressed_keys.add(ecodes.KEY_LEFTCTRL)
    result._tap_action(parse_action("chord:KEY_LEFTCTRL+KEY_C"))
    assert result.ui.write.call_args_list == [
        call(ecodes.EV_KEY, ecodes.KEY_C, 1),
        call(ecodes.EV_KEY, ecodes.KEY_C, 0),
    ]
    assert result._pressed_keys == {ecodes.KEY_LEFTCTRL}


def test_interrupted_delay_stops_before_later_action_and_cleanup_is_idempotent():
    result = target()
    result._macro_cancel.set()
    result._play_macro(parse_macros(MACROS)["copy_paste"])
    result._release_pressed_keys()
    assert result.ui.write.call_args_list == []


@pytest.mark.parametrize("macros, message", [
    ({"empty": []}, "at least one step"),
    ({"bad": [{"type": "delay", "milliseconds": -1}]}, "0..60000"),
    ({"bad": [{"type": "shell", "value": "echo nope"}]}, "Unknown action"),
    ({"bad": [{"type": "key", "value": "BTN_LEFT"}]}, "Invalid keyboard"),
])
def test_invalid_macro_configuration_fails_clearly(macros, message):
    with pytest.raises(ValueError, match=message):
        parse_macros(macros)


def test_macro_configuration_round_trips_without_changing_ordinary_remaps():
    mouse = MouseDevice("Test", "/dev/input/test")
    content = merge_setup_config(
        {}, mouse,
        mappings={"BTN_SIDE": "key:KEY_F13", "BTN_EXTRA": "macro:copy_paste"},
        dpi_stages=[800], active_dpi=800, polling_rate_hz=None, macros=MACROS,
    )
    loaded = tomllib.loads(content)
    assert loaded["macros"] == MACROS
    assert loaded["remap"]["BTN_SIDE"] == "key:KEY_F13"
    assert parse_macros(loaded["macros"])["copy_paste"][1].delay_ms == 100


def test_macro_assignment_is_press_only_and_ordinary_remap_is_unchanged():
    result = target(mappings={
        "BTN_EXTRA": "macro:copy_paste",
        "BTN_SIDE": "key:KEY_F13",
    })
    with patch.object(result, "_start_macro_worker"), patch.object(result._macro_queue, "put") as put:
        result._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 1)
        result._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 2)
        result._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 0)
    put.assert_called_once_with(result.macros["copy_paste"])

    result._handle(ecodes.EV_KEY, ecodes.BTN_SIDE, 1)
    result._handle(ecodes.EV_KEY, ecodes.BTN_SIDE, 0)
    assert result.ui.write.call_args_list[-2:] == [
        call(ecodes.EV_KEY, ecodes.KEY_F13, 1),
        call(ecodes.EV_KEY, ecodes.KEY_F13, 0),
    ]


def test_macro_capabilities_include_all_synthetic_keys_and_buttons():
    result = target()
    keys = set(result._capabilities()[ecodes.EV_KEY])
    assert {ecodes.KEY_LEFTCTRL, ecodes.KEY_C, ecodes.KEY_V,
            ecodes.KEY_1, ecodes.BTN_LEFT} <= keys


def test_undefined_assigned_macro_is_rejected():
    with pytest.raises(ValueError, match="Undefined macro"):
        MouseRemapper("/dev/input/test", {"BTN_SIDE": "macro:missing"}, macros={})
