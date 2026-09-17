from __future__ import annotations

import pytest

from mouse_control.read_only_dpi_cycle import ReadOnlyDpiCycleTracker


def test_three_stage_trigger_cycle_preserves_order_and_wraparound():
    tracker = ReadOnlyDpiCycleTracker((800, 1500, 2000), initial_dpi=800)

    states = []
    for _ in range(4):
        state = tracker.observe_trigger(True)
        assert state is not None
        states.append(state)
        assert tracker.observe_trigger(True) is None  # hold/packet echo
        assert tracker.observe_trigger(False) is None

    assert [state.display_value for state in states] == [1500, 2000, 800, 1500]
    assert all(state.confirmed for state in states)
    assert all(state.cycle_trigger is False for state in states)


def test_trigger_without_synchronization_never_invents_stage():
    tracker = ReadOnlyDpiCycleTracker((800, 1500, 2000))

    assert tracker.observe_trigger(True) is None
    assert tracker.observe_trigger(True) is None
    assert tracker.observe_trigger(False) is None
    assert not tracker.synchronized


def test_absolute_state_synchronizes_and_resynchronizes():
    tracker = ReadOnlyDpiCycleTracker((800, 1500, 2000))

    state = tracker.observe_absolute(1500)
    assert state is not None
    assert state.display_value == 1500
    assert tracker.current_dpi == 1500
    assert tracker.observe_absolute(1500) is None

    state = tracker.observe_trigger(True)
    assert state is not None and state.display_value == 2000
    tracker.observe_trigger(False)

    state = tracker.observe_absolute(800)
    assert state is not None and state.display_value == 800
    assert tracker.current_dpi == 800


def test_reconnect_invalidates_trigger_only_certainty():
    tracker = ReadOnlyDpiCycleTracker((800, 1500, 2000), initial_dpi=1500)
    tracker.invalidate_trigger_sync()

    assert not tracker.synchronized
    assert tracker.observe_trigger(True) is None
    tracker.observe_trigger(False)
    assert tracker.observe_absolute(2000) is not None
    assert tracker.synchronized


def test_press_hold_release_is_exactly_one_transition():
    tracker = ReadOnlyDpiCycleTracker((800, 1500, 2000), initial_dpi=800)

    first = tracker.observe_trigger(True)
    assert first is not None and first.display_value == 1500
    assert tracker.observe_trigger(True) is None
    assert tracker.observe_trigger(True) is None
    tracker.observe_trigger(False)
    second = tracker.observe_trigger(True)
    assert second is not None and second.display_value == 2000


def test_invalid_cycles_and_unknown_absolute_values_are_rejected():
    with pytest.raises(ValueError):
        ReadOnlyDpiCycleTracker((800,))
    with pytest.raises(ValueError):
        ReadOnlyDpiCycleTracker((800, 800))

    tracker = ReadOnlyDpiCycleTracker((800, 1500))
    with pytest.raises(ValueError):
        tracker.observe_absolute(2000)
