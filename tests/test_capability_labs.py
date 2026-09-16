from __future__ import annotations

from types import SimpleNamespace

import pytest

from mouse_control.dpi_generalization_cli import validate_numeric_generalization
from mouse_control.polling_trace_cli import estimate_polling_from_events
from mouse_control.protocol_grammar import CodecKind, CodecSpec
from mouse_control.transaction_inference import SemanticField


def _operation():
    return SimpleNamespace(
        write_authorized=True,
        write_field=SemanticField(5, 2, CodecSpec(CodecKind.U16_BE)),
        read_field=SemanticField(5, 2, CodecSpec(CodecKind.U16_BE)),
        demonstrated_values=(800, 1500, 2000, 2500, 3000),
    )


def test_numeric_generalization_accepts_unseen_values_inside_envelope():
    validate_numeric_generalization(_operation(), 1500, (1600, 1550))


@pytest.mark.parametrize("candidate", [800, 1500, 3000, 3500, 400])
def test_numeric_generalization_rejects_demonstrated_or_outside_values(candidate):
    with pytest.raises(Exception):
        validate_numeric_generalization(_operation(), 1500, (candidate,))


def test_polling_estimator_recovers_500hz_motion_frames():
    events = []
    timestamp_ns = 1_000_000_000
    for _ in range(20):
        events.append(
            SimpleNamespace(
                timestamp_ns=timestamp_ns,
                event_type=0x02,
                code=0x00,
                value=5,
            )
        )
        events.append(
            SimpleNamespace(
                timestamp_ns=timestamp_ns,
                event_type=0x00,
                code=0x00,
                value=0,
            )
        )
        timestamp_ns += 2_000_000

    peak, standard, error = estimate_polling_from_events(events)
    assert peak == pytest.approx(500.0)
    assert standard == 500
    assert error == pytest.approx(0.0)
