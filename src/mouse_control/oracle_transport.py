"""Deterministic transport/replay adapter for VirtualPeripheralOracle."""
from __future__ import annotations
from dataclasses import dataclass
from .virtual_oracle import (OracleTransferKind, VirtualPeripheralOracle, VirtualReportKey)


@dataclass(frozen=True)
class TeachingTransfer:
    timestamp_ns: int
    kind: OracleTransferKind
    key: VirtualReportKey
    payload: bytes = b""


class OracleTeachingAdapter:
    """Feeds captured host transfers to the canonical Oracle in strict order."""
    def __init__(self, oracle: VirtualPeripheralOracle) -> None:
        self.oracle = oracle
        self._last_timestamp = -1

    def replay(self, transfers: tuple[TeachingTransfer, ...], *, action: str) -> int:
        with self.oracle.action(action) as action_id:
            for item in transfers:
                if item.timestamp_ns < self._last_timestamp:
                    raise ValueError("transport timestamps are not monotonic")
                self._last_timestamp = item.timestamp_ns
                if item.kind is OracleTransferKind.GET_REPORT:
                    if item.payload:
                        raise ValueError("GET_REPORT replay must not supply a payload")
                    self.oracle.get_report(item.key)
                elif item.kind is OracleTransferKind.SET_REPORT:
                    self.oracle.set_report(item.key, item.payload)
                elif item.kind is OracleTransferKind.OUTPUT_REPORT:
                    self.oracle.output_report(item.key, item.payload)
        return action_id
