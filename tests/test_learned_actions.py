from __future__ import annotations

import pytest

from mouse_control.learned_actions import (
    LearnedActionError,
    LearnedActionStore,
    LearnedActionTrigger,
    learned_action_from_profile,
    learned_action_to_profile,
)
from mouse_control.learned_operations import (
    StableDeviceIdentity,
    StableInterfaceIdentity,
)
from mouse_control.polling_replay import PacketPattern
from mouse_control.protocol_grammar import SemanticBehavior


def trigger(observations=8):
    return LearnedActionTrigger(
        behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        identity=StableDeviceIdentity(
            3, 0x046D, 0x4074, "model", "instance"
        ),
        interface=StableInterfaceIdentity(
            3, 0x046D, 0x4074, 2, "descriptor"
        ),
        press_pattern=PacketPattern(
            tuple(bytes.fromhex("02 20 00 00 00 00 00 00 00"))
        ),
        release_pattern=PacketPattern(
            tuple(bytes.fromhex("02 00 00 00 00 00 00 00 00"))
        ),
        observation_count=observations,
    )


def test_round_trip_is_permanently_read_only():
    item = trigger()
    profile = learned_action_to_profile(item)
    restored = learned_action_from_profile(profile)
    assert restored == item
    assert restored.write_authorized is False
    assert profile["write_authorized"] is False
    assert profile["safety"] == "read_only"
    assert profile["write_scope"] == "never"


def test_requires_five_complete_observations():
    with pytest.raises(LearnedActionError, match="at least five"):
        learned_action_to_profile(trigger(observations=4))


def test_patterns_are_exact_and_directional():
    item = trigger()
    assert item.matches_press(
        bytes.fromhex("02 20 00 00 00 00 00 00 00")
    )
    assert not item.matches_press(
        bytes.fromhex("02 00 00 00 00 00 00 00 00")
    )
    assert item.matches_release(
        bytes.fromhex("02 00 00 00 00 00 00 00 00")
    )


def test_store_uses_separate_learned_action_directory(tmp_path):
    store = LearnedActionStore(tmp_path)
    path = store.save(trigger())
    assert path.parent == tmp_path
    assert path.name.endswith("-dpi_cycle_trigger.json")
    assert store.load(path) == trigger()
