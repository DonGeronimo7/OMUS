from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mouse_control import guided_discovery as guided


def _sample(*, teacher=False):
    state = {"dpi": 800} if teacher else {}
    return SimpleNamespace(
        action=SimpleNamespace(hid_reports=(), evdev_events=(), feature_changes=()),
        unreadable_hidraw_paths=(),
        teacher_before_state=state,
        teacher_state=state,
    )


def _result(*, dpi_writable=False, polling_writable=False, ambiguous=False, hidraw=True):
    def capability(name, writable):
        return SimpleNamespace(name=name, writable=writable, readable=writable)

    caps = {}
    if dpi_writable:
        caps["dpi"] = capability("dpi", True)
    if polling_writable:
        caps["report_rate"] = capability("report_rate", True)
    return SimpleNamespace(
        device=SimpleNamespace(
            ambiguous=ambiguous,
            hidraw_nodes=[SimpleNamespace(path="/dev/hidraw-test")] if hidraw else [],
        ),
        capabilities=caps,
        protocol=None,
    )


def test_guided_dpi_learning_reuses_two_controls_then_three_actions(monkeypatch):
    samples = [_sample() for _ in range(5)]
    session = Mock()
    session.observe_action.side_effect = samples
    learned = SimpleNamespace(samples=samples[2:])
    session.analyze.return_value = learned
    monkeypatch.setattr(
        guided,
        "refine_teacher_free",
        lambda _learned: SimpleNamespace(candidates=[SimpleNamespace(candidate=object())], hypotheses=()),
    )

    steps = []
    outcome = guided.run_guided_dpi_learning(
        object(),
        _result(),
        SimpleNamespace(descriptors={"node": object()}),
        prompt=lambda step: steps.append(step) or True,
        session_factory=lambda *_args: session,
    )

    assert [step.index for step in steps] == [1, 2, 3, 4, 5]
    assert session.observe_action.call_count == 5
    assert session.analyze.call_args.kwargs["control_samples"] == samples[:2]
    assert outcome.controls == tuple(samples[:2])
    assert outcome.samples == tuple(samples[2:])
    assert outcome.action_identified is True


def test_guided_dpi_learning_cancel_stops_before_hardware_capture():
    session = Mock()
    with pytest.raises(guided.GuidedDiscoveryCancelled):
        guided.run_guided_dpi_learning(
            object(),
            _result(),
            SimpleNamespace(descriptors={"node": object()}),
            prompt=lambda _step: False,
            session_factory=lambda *_args: session,
        )
    session.observe_action.assert_not_called()
    session.analyze.assert_not_called()


def test_teacher_read_occurs_before_each_guided_prompt():
    events = []
    controls = [_sample(), _sample()]
    actions = [_sample(teacher=True) for _ in range(3)]
    session = Mock()
    session.observe_action.side_effect = controls + actions
    session.analyze.return_value = SimpleNamespace(
        samples=actions,
        discriminative_trigger_candidates=(object(),),
        hypotheses=(),
    )

    def prompt(step):
        events.append(("prompt", step.index))
        return True

    def teacher_reader(_selected):
        events.append(("teacher", None))
        return {"dpi": 800}

    guided.run_guided_dpi_learning(
        object(),
        _result(),
        SimpleNamespace(descriptors={"node": object()}),
        prompt=prompt,
        teacher=True,
        teacher_reader=teacher_reader,
        session_factory=lambda *_args: session,
    )
    assert events[:2] == [("prompt", 1), ("prompt", 2)]
    assert events[2:] == [
        ("teacher", None), ("prompt", 3),
        ("teacher", None), ("prompt", 4),
        ("teacher", None), ("prompt", 5),
    ]


def test_passive_discovery_skips_learning_for_proven_dpi():
    result = _result(dpi_writable=True)
    engine = Mock(descriptors={"node": object()})
    engine.discover.return_value = result
    outcome = guided.run_guided_discovery(
        object(),
        prompt=lambda _step: True,
        engine_factory=lambda: engine,
    )
    assert outcome.learning is None
    assert outcome.dpi_writable is True
    assert "already safely proven" in outcome.learning_skipped_reason


def test_ambiguous_device_refuses_guided_binding():
    result = _result(ambiguous=True)
    engine = Mock(descriptors={"node": object()})
    engine.discover.return_value = result
    outcome = guided.run_guided_discovery(
        object(),
        prompt=lambda _step: True,
        engine_factory=lambda: engine,
    )
    assert outcome.learning is None
    assert "ambiguous" in outcome.learning_skipped_reason


def test_unknown_device_runs_only_read_only_observation(monkeypatch):
    result = _result()
    engine = Mock(descriptors={"node": object()})
    engine.discover.return_value = result
    session = Mock()
    captures = [_sample() for _ in range(5)]
    session.observe_action.side_effect = captures
    session.analyze.return_value = SimpleNamespace(samples=captures[2:])
    monkeypatch.setattr(
        guided,
        "refine_teacher_free",
        lambda _learned: SimpleNamespace(candidates=(), hypotheses=()),
    )

    outcome = guided.run_guided_discovery(
        object(),
        prompt=lambda _step: True,
        engine_factory=lambda: engine,
        session_factory=lambda *_args: session,
    )
    assert outcome.learning is not None
    assert session.observe_action.call_count == 5
    assert not session.set_dpi.called
    assert outcome.dpi_writable is False
    assert outcome.polling_writable is False
