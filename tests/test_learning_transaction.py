"""Regression tests for guided learning and protocol transaction execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from mouse_control.discovery_models import PhysicalDevice
from mouse_control.event_correlation import PhysicalAction, TimedReport
from mouse_control.learning_session import LearningSample, ReadOnlyLearningSession
from mouse_control.protocol_grammar import (
    SafetyClass,
    TransactionSpec,
    TransactionStep,
    TransportKind,
)
from mouse_control.transaction_engine import (
    RetryableTransactionError,
    StepResult,
    TransactionAdapter,
    TransactionAuthorization,
    TransactionAuthorizationError,
    TransactionContext,
    TransactionEngine,
    TransactionError,
)


def physical():
    return PhysicalDevice(
        "Test Mouse", 0x1234, 0x5678, 3, None, model_fingerprint="model"
    )


def action(value: int, timestamp: int) -> PhysicalAction:
    return PhysicalAction(
        timestamp,
        timestamp + 1,
        hid_reports=[TimedReport(timestamp, "/dev/hidraw8", bytes((0x11, 0x01, 0x07, value)))],
    )


def test_guided_learning_finds_raw_stage_field_and_teacher_mapping():
    session = ReadOnlyLearningSession(physical(), {})
    samples = [
        LearningSample(action(1, 1), {"dpi": 800}),
        LearningSample(action(2, 2), {"dpi": 1500}),
        LearningSample(action(3, 3), {"dpi": 2000}),
    ]
    learned = session.analyze(samples)

    raw_candidate = next(item for item in learned.report_candidates if item.offset == 3)
    assert raw_candidate.values == (1, 2, 3)
    assert any(
        hypothesis.behavior.value == "dpi_value"
        and hypothesis.offset == 3
        and dict(hypothesis.mapping or {}) == {1: 800, 2: 1500, 3: 2000}
        and hypothesis.confidence == "validated"
        for hypothesis in learned.hypotheses
    )


class Adapter:
    def __init__(self):
        self.calls = 0
        self.verified = []

    def execute(self, step, context):
        self.calls += 1
        if step.operation == "poll" and self.calls == 1:
            raise RetryableTransactionError("busy")
        return StepResult(value=b"ok")

    def condition(self, expression, result, context):
        return expression == "ready" and result == b"ok"

    def verify(self, rule, context):
        self.verified.append(rule)
        return rule == "readback"


def test_transaction_engine_retries_and_verifies():
    sleeps = []
    engine = TransactionEngine(sleep=lambda seconds: sleeps.append(seconds))
    adapter = Adapter()
    spec = TransactionSpec(
        "status",
        steps=(
            TransactionStep(
                "poll",
                transport=TransportKind.HID_FEATURE_GET,
                retries=1,
                delay_ms=20,
                condition="ready",
            ),
        ),
        safety=SafetyClass.READ_ONLY,
        verification=("readback",),
    )
    context = engine.run(spec, adapter)
    assert "status" in context.completed
    assert adapter.calls == 2
    assert adapter.verified == ["readback"]
    assert sleeps == [0.02, 0.02]


def test_active_query_write_transport_requires_explicit_authority():
    engine = TransactionEngine(sleep=lambda _seconds: None)
    adapter = Adapter()
    spec = TransactionSpec(
        "battery-heartbeat",
        steps=(TransactionStep("send-heartbeat", transport=TransportKind.HID_FEATURE_SET),),
        safety=SafetyClass.READ_ONLY,
    )
    with pytest.raises(TransactionAuthorizationError):
        engine.run(spec, adapter)

    context = engine.run(
        spec,
        adapter,
        authorization=TransactionAuthorization(active_queries=True),
    )
    assert "battery-heartbeat" in context.completed


def test_persistent_and_dangerous_transactions_are_separately_gated():
    engine = TransactionEngine(sleep=lambda _seconds: None)
    adapter = Adapter()
    persistent = TransactionSpec(
        "commit",
        steps=(TransactionStep("commit", transport=TransportKind.HID_FEATURE_SET),),
        safety=SafetyClass.PERSISTENT,
    )
    with pytest.raises(TransactionAuthorizationError):
        engine.run(persistent, adapter)
    engine.run(
        persistent,
        adapter,
        authorization=TransactionAuthorization(persistent_writes=True),
    )

    dangerous = TransactionSpec(
        "rf-reset",
        steps=(TransactionStep("send", transport=TransportKind.HID_FEATURE_SET),),
        safety=SafetyClass.DANGEROUS,
    )
    with pytest.raises(TransactionAuthorizationError):
        engine.run(dangerous, adapter)


def test_transaction_prerequisite_is_enforced():
    engine = TransactionEngine(sleep=lambda _seconds: None)
    adapter = Adapter()
    spec = TransactionSpec(
        "lighting",
        steps=(TransactionStep("send", transport=TransportKind.HID_FEATURE_SET),),
        safety=SafetyClass.REVERSIBLE,
        prerequisite=("dpi-config",),
    )
    auth = TransactionAuthorization(reversible_writes=True)
    with pytest.raises(TransactionError):
        engine.run(spec, adapter, authorization=auth)

    context = TransactionContext(completed={"dpi-config"})
    engine.run(spec, adapter, authorization=auth, context=context)
    assert "lighting" in context.completed
