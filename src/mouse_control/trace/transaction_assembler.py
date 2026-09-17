"""Pair usbmon URB events without assigning vendor semantics."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .models import (
    TransactionAnomaly,
    UrbEventType,
    UsbDirection,
    UsbObservation,
    UsbTransaction,
    UsbTransferType,
)


class UsbTransactionAssembler:
    """Deterministically assemble submit/completion pairs by capture and URB.

    Pending URBs are capture-local. Reuse, capture boundaries, missing submits,
    and mismatched metadata are retained as explicit anomalies rather than
    silently discarded.
    """

    def __init__(self) -> None:
        self._pending: dict[tuple[str, int], UsbObservation] = {}
        self._seen: set[tuple[object, ...]] = set()

    @staticmethod
    def _event_key(item: UsbObservation) -> tuple[object, ...]:
        return (
            item.capture_id,
            item.sequence,
            item.urb_id,
            item.event_type,
            item.timestamp_ns,
            item.payload,
        )

    @staticmethod
    def _identity(item: UsbObservation) -> tuple[str, int] | None:
        if item.urb_id is None:
            return None
        return item.capture_id, item.urb_id

    @staticmethod
    def _payloads(
        submit: UsbObservation | None,
        completion: UsbObservation | None,
    ) -> tuple[bytes, bytes]:
        anchor = submit or completion
        assert anchor is not None
        direction = anchor.setup.direction if anchor.setup is not None else anchor.direction
        if direction is UsbDirection.OUT:
            return (submit.payload if submit else b"", completion.payload if completion else b"")
        if direction is UsbDirection.IN:
            return (submit.payload if submit else b"", completion.payload if completion else b"")
        return (submit.payload if submit else b"", completion.payload if completion else b"")

    @classmethod
    def _transaction(
        cls,
        submit: UsbObservation | None,
        completion: UsbObservation | None,
        anomaly: TransactionAnomaly | None = None,
    ) -> UsbTransaction:
        anchor = submit or completion
        assert anchor is not None
        request, response = cls._payloads(submit, completion)
        if submit is not None and completion is not None:
            latency = completion.timestamp_ns - submit.timestamp_ns
            if latency < 0:
                latency = None
                anomaly = anomaly or TransactionAnomaly.EVENT_MISMATCH
        else:
            latency = None
        suffix = submit.sequence if submit is not None else completion.sequence  # type: ignore[union-attr]
        urb = "none" if anchor.urb_id is None else f"{anchor.urb_id:016x}"
        return UsbTransaction(
            transaction_id=f"{anchor.capture_id}:{urb}:{suffix}",
            submit=submit,
            completion=completion,
            request_payload=request,
            response_payload=response,
            setup=(submit.setup if submit and submit.setup else anchor.setup),
            transfer_type=anchor.transfer_type,
            endpoint=anchor.endpoint,
            direction=anchor.direction,
            status=(completion.status if completion else anchor.status),
            latency_ns=latency,
            complete=submit is not None and completion is not None,
            anomaly=anomaly,
        )

    def add(self, item: UsbObservation) -> tuple[UsbTransaction, ...]:
        event_key = self._event_key(item)
        if event_key in self._seen:
            return ()
        self._seen.add(event_key)
        identity = self._identity(item)

        if item.event_type is UrbEventType.SUBMIT:
            if identity is None:
                return (self._transaction(item, None, TransactionAnomaly.MISSING_COMPLETION),)
            previous = self._pending.pop(identity, None)
            self._pending[identity] = item
            if previous is not None:
                return (self._transaction(previous, None, TransactionAnomaly.REUSED_URB),)
            return ()

        if item.event_type in {UrbEventType.COMPLETE, UrbEventType.ERROR}:
            submit = self._pending.pop(identity, None) if identity is not None else None
            anomaly = None if submit is not None else TransactionAnomaly.MISSING_SUBMIT
            if submit is not None and (
                submit.bus_id != item.bus_id
                or submit.device_address != item.device_address
                or submit.transfer_type is not item.transfer_type
                or submit.endpoint != item.endpoint
            ):
                anomaly = TransactionAnomaly.EVENT_MISMATCH
            return (self._transaction(submit, item, anomaly),)

        return (self._transaction(None, item, TransactionAnomaly.EVENT_MISMATCH),)

    def extend(self, observations: Iterable[UsbObservation]) -> tuple[UsbTransaction, ...]:
        result: list[UsbTransaction] = []
        for item in observations:
            result.extend(self.add(item))
        return tuple(result)

    def boundary(self, capture_id: str | None = None) -> tuple[UsbTransaction, ...]:
        keys = sorted(
            key for key in self._pending
            if capture_id is None or key[0] == capture_id
        )
        result = tuple(
            self._transaction(
                self._pending.pop(key), None, TransactionAnomaly.CAPTURE_BOUNDARY
            )
            for key in keys
        )
        return result

    def finish(self) -> tuple[UsbTransaction, ...]:
        return tuple(
            replace(transaction, anomaly=TransactionAnomaly.MISSING_COMPLETION)
            for transaction in self.boundary()
        )
