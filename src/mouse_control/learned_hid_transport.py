"""Protocol-neutral execution of PROVEN or explicitly promoted learned HID writes."""

from __future__ import annotations

import os
from pathlib import Path
import time

from .hid_session import HidrawIo
from .learned_operations import LearnedOperation, LearnedOperationError
from .protocol_grammar import SafetyClass, TransactionSpec, TransactionStep, TransportKind
from .transaction_engine import (
    StepResult,
    TransactionAdapter,
    TransactionAuthorization,
    TransactionContext,
    TransactionEngine,
    TransactionError,
)


class LearnedHidTransportError(TransactionError):
    """A learned raw HID transaction failed."""


class LearnedHidAdapter(TransactionAdapter):
    def __init__(
        self,
        path: str | Path,
        operation: LearnedOperation,
        *,
        io_factory=HidrawIo,
        timeout: float = 0.25,
    ) -> None:
        self.path = Path(path)
        self.operation = operation
        self.timeout = float(timeout)
        self._io = io_factory(self.path)
        self.closed = False

    def close(self) -> None:
        if not self.closed:
            self._io.close()
            self.closed = True

    def _exchange(self, request: bytes, pattern) -> bytes:
        if self.closed:
            raise LearnedHidTransportError("learned HID adapter is closed")
        self._io.write(request)
        deadline = time.monotonic() + self.timeout
        seen = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LearnedHidTransportError(
                    f"timed out waiting for learned reply after {seen} unrelated packet(s)"
                )
            data = self._io.read(remaining)
            if data == b"":
                raise LearnedHidTransportError("hidraw interface disconnected")
            if data is None:
                continue
            seen += 1
            packet = bytes(data)
            if pattern.matches(packet):
                return packet

    def execute(self, step: TransactionStep, context: TransactionContext):
        if step.frame == "write":
            target = int(context.values["target"])
            request = self.operation.render_write(target)
            reply = self._exchange(request, self.operation.write_reply)
            context.values["write_request"] = request
            context.values["write_reply"] = reply
            return StepResult(reply)

        if step.frame == "readback":
            request = self.operation.render_read()
            reply = self._exchange(request, self.operation.read_reply)
            value = self.operation.decode_readback(reply)
            context.values["read_request"] = request
            context.values["read_reply"] = reply
            context.values["raw_readback"] = value
            return StepResult(value)

        raise LearnedHidTransportError(f"unsupported learned frame {step.frame!r}")

    def condition(self, expression: str, result, context: TransactionContext) -> bool:
        if expression == "readback-is-target":
            return int(result) == int(context.values["target"])
        raise LearnedHidTransportError(f"unknown learned condition {expression!r}")

    def verify(self, rule: str, context: TransactionContext) -> bool:
        if rule == "readback-target":
            return int(context.values.get("raw_readback", -1)) == int(
                context.values.get("target", -2)
            )
        raise LearnedHidTransportError(f"unknown learned verification {rule!r}")


def learned_dpi_transaction_spec() -> TransactionSpec:
    return TransactionSpec(
        name="learned-dpi-write",
        safety=SafetyClass.REVERSIBLE,
        steps=(
            TransactionStep(
                operation="request",
                frame="write",
                transport=TransportKind.HID_OUTPUT,
            ),
            TransactionStep(
                operation="request",
                frame="readback",
                transport=TransportKind.HID_OUTPUT,
                condition="readback-is-target",
            ),
        ),
        verification=("readback-target",),
    )



def learned_dpi_read_spec() -> TransactionSpec:
    return TransactionSpec(
        name="learned-dpi-read",
        safety=SafetyClass.READ_ONLY,
        steps=(
            TransactionStep(
                operation="request",
                frame="readback",
                transport=TransportKind.HID_OUTPUT,
            ),
        ),
    )


def read_learned_dpi(
    operation: LearnedOperation,
    path: str | Path,
    *,
    authorization: TransactionAuthorization | None = None,
    io_factory=HidrawIo,
    timeout: float = 0.25,
) -> int:
    """Read current DPI through a PROVEN learned active-query grammar."""

    if not operation.write_authorized:
        raise LearnedHidTransportError(
            "learned active query is unavailable until the operation is PROVEN"
        )
    auth = authorization or TransactionAuthorization()
    if not auth.active_queries:
        raise LearnedHidTransportError(
            "explicit active-query authorization is required"
        )
    context = TransactionContext()
    adapter = LearnedHidAdapter(
        path,
        operation,
        io_factory=io_factory,
        timeout=timeout,
    )
    try:
        TransactionEngine().run(
            learned_dpi_read_spec(),
            adapter,
            authorization=auth,
            context=context,
        )
        return int(context.values["raw_readback"])
    except (OSError, LearnedOperationError) as exc:
        raise LearnedHidTransportError(str(exc)) from exc
    finally:
        adapter.close()


def execute_learned_dpi(
    operation: LearnedOperation,
    path: str | Path,
    target: int,
    *,
    promotion: bool = False,
    authorization: TransactionAuthorization | None = None,
    io_factory=HidrawIo,
    timeout: float = 0.25,
) -> TransactionContext:
    """Execute one exact demonstrated DPI transaction.

    Normal runtime requires a PROVEN operation. Promotion may replay a
    DEMONSTRATED operation only when the caller explicitly passes reversible
    write authorization. In both cases only demonstrated values are accepted.
    """

    if not operation.accepts(target):
        raise LearnedHidTransportError(
            f"target {target} was not in the demonstrated value set"
        )
    if not operation.write_authorized and not promotion:
        raise LearnedHidTransportError(
            "learned operation is DEMONSTRATED, not PROVEN"
        )
    if promotion and operation.write_authorized:
        promotion = False

    auth = authorization or TransactionAuthorization()
    if not auth.reversible_writes:
        raise LearnedHidTransportError(
            "explicit reversible-write authorization is required"
        )
    if not operation.write_authorized and not promotion:
        raise LearnedHidTransportError("unproven operation cannot execute outside promotion")

    context = TransactionContext(values={"target": int(target)})
    adapter = LearnedHidAdapter(
        path,
        operation,
        io_factory=io_factory,
        timeout=timeout,
    )
    try:
        return TransactionEngine().run(
            learned_dpi_transaction_spec(),
            adapter,
            authorization=auth,
            context=context,
        )
    except (OSError, LearnedOperationError) as exc:
        raise LearnedHidTransportError(str(exc)) from exc
    finally:
        adapter.close()
