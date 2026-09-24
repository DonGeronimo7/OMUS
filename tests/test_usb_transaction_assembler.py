# SPDX-License-Identifier: AGPL-3.0-or-later
from mouse_control.trace.models import (
    CaptureSource,
    TransactionAnomaly,
    UrbEventType,
    UsbDirection,
    UsbObservation,
    UsbTransferType,
)
from mouse_control.trace.transaction_assembler import UsbTransactionAssembler


def observation(
    sequence: int,
    event: UrbEventType,
    *,
    urb_id: int = 7,
    payload: bytes = b"",
    timestamp_ns: int | None = None,
) -> UsbObservation:
    return UsbObservation(
        capture_id="capture",
        sequence=sequence,
        timestamp_ns=sequence * 100 if timestamp_ns is None else timestamp_ns,
        source=CaptureSource.SYNTHETIC_TEST,
        bus_id=3,
        device_address=9,
        interface_number=1,
        endpoint=2,
        direction=UsbDirection.OUT,
        transfer_type=UsbTransferType.INTERRUPT,
        event_type=event,
        urb_id=urb_id,
        status=0,
        setup=None,
        declared_length=len(payload),
        captured_length=len(payload),
        payload=payload,
        physical_device_fingerprint="stable-device",
    )


def test_pairs_submit_and_completion_and_preserves_both_payloads() -> None:
    assembler = UsbTransactionAssembler()
    assert assembler.add(observation(1, UrbEventType.SUBMIT, payload=b"request")) == ()
    result = assembler.add(observation(2, UrbEventType.COMPLETE, payload=b"reply"))

    assert len(result) == 1
    transaction = result[0]
    assert transaction.complete
    assert transaction.request_payload == b"request"
    assert transaction.response_payload == b"reply"
    assert transaction.latency_ns == 100
    assert transaction.anomaly is None


def test_completion_without_submit_is_retained_as_anomaly() -> None:
    result = UsbTransactionAssembler().add(
        observation(1, UrbEventType.COMPLETE, payload=b"orphan")
    )
    assert result[0].anomaly is TransactionAnomaly.MISSING_SUBMIT
    assert not result[0].complete


def test_urb_reuse_flushes_previous_submit_without_pairing_wrong_events() -> None:
    assembler = UsbTransactionAssembler()
    assembler.add(observation(1, UrbEventType.SUBMIT, payload=b"old"))
    reused = assembler.add(observation(2, UrbEventType.SUBMIT, payload=b"new"))
    paired = assembler.add(observation(3, UrbEventType.COMPLETE, payload=b"reply"))

    assert reused[0].request_payload == b"old"
    assert reused[0].anomaly is TransactionAnomaly.REUSED_URB
    assert paired[0].request_payload == b"new"


def test_finish_retains_missing_completion_and_duplicate_events_are_ignored() -> None:
    assembler = UsbTransactionAssembler()
    submit = observation(1, UrbEventType.SUBMIT, payload=b"request")
    assert assembler.add(submit) == ()
    assert assembler.add(submit) == ()
    final = assembler.finish()
    assert len(final) == 1
    assert final[0].anomaly is TransactionAnomaly.MISSING_COMPLETION


def test_out_of_order_completion_is_not_given_negative_latency() -> None:
    assembler = UsbTransactionAssembler()
    assembler.add(observation(2, UrbEventType.SUBMIT, timestamp_ns=200))
    result = assembler.add(observation(1, UrbEventType.COMPLETE, timestamp_ns=100))
    assert result[0].latency_ns is None
    assert result[0].anomaly is TransactionAnomaly.EVENT_MISMATCH
