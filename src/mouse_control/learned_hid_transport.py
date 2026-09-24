# SPDX-License-Identifier: AGPL-3.0-or-later
"""Protocol-neutral execution of PROVEN or explicitly promoted learned HID writes."""

from __future__ import annotations

from pathlib import Path

from .hid_session import HidrawIo
from .learned_hid_session import LearnedHidSession, LearnedHidSessionError
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
    """Transaction-engine adapter backed by one single-reader learned session.

    By default the adapter owns its session, preserving the historical public
    constructor/close behavior.  A caller may instead inject a shared session;
    that is the production bridge used when DPI queries/writes and unsolicited
    learned events must coexist on the same hidraw stream.
    """

    def __init__(
        self,
        path: str | Path,
        operation: LearnedOperation,
        *,
        io_factory=HidrawIo,
        timeout: float = 0.25,
        session: LearnedHidSession | None = None,
    ) -> None:
        self.path = Path(path)
        self.operation = operation
        self.timeout = float(timeout)
        self.closed = False
        self._owns_session = session is None
        if session is None:
            self._session = LearnedHidSession(
                self.path,
                io_factory=io_factory,
                timeout=self.timeout,
            )
        else:
            if Path(session.path) != self.path:
                raise LearnedHidTransportError(
                    "shared learned HID session is bound to a different interface"
                )
            self._session = session

    @property
    def session(self) -> LearnedHidSession:
        return self._session

    def close(self) -> None:
        if not self.closed:
            if self._owns_session:
                self._session.close()
            self.closed = True

    def _exchange(self, request: bytes, pattern) -> bytes:
        if self.closed:
            raise LearnedHidTransportError("learned HID adapter is closed")
        try:
            return self._session.exchange(
                request,
                pattern,
                timeout=self.timeout,
            )
        except LearnedHidSessionError as exc:
            raise LearnedHidTransportError(str(exc)) from exc

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
    session: LearnedHidSession | None = None,
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
        session=session,
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
    session: LearnedHidSession | None = None,
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
        raise LearnedHidTransportError(
            "unproven operation cannot execute outside promotion"
        )

    context = TransactionContext(values={"target": int(target)})
    adapter = LearnedHidAdapter(
        path,
        operation,
        io_factory=io_factory,
        timeout=timeout,
        session=session,
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
