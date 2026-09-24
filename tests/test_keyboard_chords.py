# SPDX-License-Identifier: AGPL-3.0-or-later
"""Keyboard chord parser and uinput lifetime tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest
from evdev import ecodes

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mouse_control.remapper import MouseRemapper, parse_action


@pytest.mark.parametrize("value,codes", [
    ("chord:KEY_LEFTCTRL+KEY_C", (ecodes.KEY_LEFTCTRL, ecodes.KEY_C)),
    ("chord:KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_S",
     (ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTSHIFT, ecodes.KEY_S)),
])
def test_parse_valid_chords(value, codes):
    assert parse_action(value).codes == codes


@pytest.mark.parametrize("value", [
    "chord:", "chord:KEY_C", "chord:KEY_LEFTCTRL+",
    "chord:KEY_LEFTCTRL++KEY_C", "chord:NOT_A_KEY+KEY_C",
    "chord:BTN_LEFT+KEY_C", "chord:KEY_C+KEY_C",
])
def test_parse_invalid_chords(value):
    with pytest.raises(ValueError):
        parse_action(value)


def test_legacy_actions_remain_valid():
    assert parse_action("passthrough").kind == "passthrough"
    assert parse_action("disable").kind == "disable"
    assert parse_action("dpi-cycle").kind == "dpi-cycle"
    assert parse_action("mouse:BTN_MIDDLE").code == ecodes.BTN_MIDDLE
    assert parse_action("key:KEY_LEFTMETA").code == ecodes.KEY_LEFTMETA


def remapper(mappings):
    target = MouseRemapper("/dev/input/test", mappings)
    target.ui = MagicMock()
    target.device = MagicMock()
    target.device.capabilities.return_value = {
        ecodes.EV_KEY: [ecodes.BTN_SIDE], ecodes.EV_REL: []}
    return target


def writes(target):
    return target.ui.write.call_args_list


def test_chord_press_repeat_release_order_and_held_state():
    target = remapper({"BTN_EXTRA": "chord:KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_S"})
    target._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 1)
    assert writes(target) == [
        call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
        call(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1),
        call(ecodes.EV_KEY, ecodes.KEY_S, 1),
    ]
    target._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 2)
    target._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 1)
    assert len(writes(target)) == 3
    target._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 0)
    target._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 0)
    assert writes(target)[3:] == [
        call(ecodes.EV_KEY, ecodes.KEY_S, 0),
        call(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0),
        call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
    ]


def test_overlapping_chords_keep_shared_modifier_held():
    target = remapper({"BTN_SIDE": "chord:KEY_LEFTCTRL+KEY_C",
                       "BTN_EXTRA": "chord:KEY_LEFTCTRL+KEY_V"})
    for button, value in [(ecodes.BTN_SIDE, 1), (ecodes.BTN_EXTRA, 1),
                          (ecodes.BTN_SIDE, 0), (ecodes.BTN_EXTRA, 0)]:
        target._handle(ecodes.EV_KEY, button, value)
    assert writes(target) == [
        call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
        call(ecodes.EV_KEY, ecodes.KEY_C, 1),
        call(ecodes.EV_KEY, ecodes.KEY_V, 1),
        call(ecodes.EV_KEY, ecodes.KEY_C, 0),
        call(ecodes.EV_KEY, ecodes.KEY_V, 0),
        call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
    ]


def test_cleanup_releases_chords_and_resets_state_for_reconnect():
    target = remapper({"BTN_EXTRA": "chord:KEY_LEFTCTRL+KEY_S"})
    target._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 1)
    target._release_pressed_keys()
    assert writes(target)[2:] == [call(ecodes.EV_KEY, ecodes.KEY_S, 0),
                                  call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)]
    assert not target._pressed_keys
    assert not target._held_chords
    assert not target._chord_key_counts
    target.ui.write.reset_mock()
    target._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 1)
    assert writes(target) == [call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
                              call(ecodes.EV_KEY, ecodes.KEY_S, 1)]


def test_chord_codes_are_uinput_capabilities():
    target = remapper({"BTN_EXTRA": "chord:KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_S",
                       "BTN_TASK": "key:KEY_F13"})
    keys = target._capabilities()[ecodes.EV_KEY]
    assert {ecodes.BTN_SIDE, ecodes.BTN_LEFT, ecodes.KEY_LEFTCTRL,
            ecodes.KEY_LEFTSHIFT, ecodes.KEY_S, ecodes.KEY_F13} <= set(keys)
