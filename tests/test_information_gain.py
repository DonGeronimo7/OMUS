# SPDX-License-Identifier: AGPL-3.0-or-later
from types import SimpleNamespace

from mouse_control.information_gain import ExperimentHypothesis, choose_experiment
from mouse_control.discovery_research import build_discovery_research_plan
from mouse_control.protocol_grammar import TransportKind


def test_selects_experiment_that_best_partitions_remaining_hypotheses():
    hypotheses = (
        ExperimentHypothesis("a", {"idle": 0, "feature": 1}),
        ExperimentHypothesis("b", {"idle": 0, "feature": 0}),
        ExperimentHypothesis("c", {"idle": 0, "feature": 1}),
        ExperimentHypothesis("d", {"idle": 1, "feature": 0}),
    )
    choice = choose_experiment(hypotheses)
    assert choice is not None
    assert choice.experiment == "feature"
    assert choice.information_gain_bits == 1.0


def test_does_not_propose_non_discriminating_or_incomplete_experiment():
    hypotheses = (
        ExperimentHypothesis("a", {"same": 1, "partial": 0}),
        ExperimentHypothesis("b", {"same": 1}),
    )
    assert choose_experiment(hypotheses) is None


class _Store:
    def find_for_physical(self, *_args, **_kwargs):
        return None


def test_discovery_plan_actively_exposes_best_read_only_transport_experiment():
    device = object()
    result = SimpleNamespace(protocol=None, capabilities={}, device=device)
    candidates = (
        SimpleNamespace(score=8, family=SimpleNamespace(name="a", transports=(TransportKind.HID_INPUT,), write_scope="never")),
        SimpleNamespace(score=8, family=SimpleNamespace(name="b", transports=(TransportKind.HID_FEATURE_GET,), write_scope="never")),
    )
    plan = build_discovery_research_plan(
        result,
        candidates,
        learned_operation_store=_Store(),
        learned_polling_store=_Store(),
    )
    assert plan.deeper_learning_recommended
    assert plan.next_experiment is not None
    assert plan.next_experiment.experiment in {"observe:hid_input", "observe:hid_feature_get"}
    assert plan.next_experiment.information_gain_bits == 1.0
