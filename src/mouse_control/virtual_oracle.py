"""Transport-agnostic core for a Virtual Peripheral Oracle.

A future UHID/USB-IP adapter can forward vendor-software GET/SET_REPORT traffic
into this object.  The core is useful offline today: it enforces exact report
shapes, lets research explicitly control virtual state, records vendor writes
inside semantic action windows, computes differential byte evidence, and emits
EvidenceGraph observations.  Nothing here can access physical hardware.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import json
from typing import Iterator, Mapping

from .evidence_graph import EvidenceGraph, EvidenceNode


class VirtualOracleError(ValueError):
    pass


class OracleTransferKind(str, Enum):
    GET_REPORT = "get_report"
    SET_REPORT = "set_report"
    OUTPUT_REPORT = "output_report"


class OracleDirection(str, Enum):
    HOST_TO_DEVICE = "host_to_device"
    DEVICE_TO_HOST = "device_to_host"


@dataclass(frozen=True, order=True)
class VirtualReportKey:
    interface_number: int
    report_type: str
    report_id: int

    def __post_init__(self) -> None:
        if self.interface_number < 0 or self.report_type not in {"feature", "input", "output"}:
            raise VirtualOracleError("invalid virtual report identity")
        if not 0 <= self.report_id <= 0xFF:
            raise VirtualOracleError("virtual report ID must fit u8")


@dataclass(frozen=True)
class VirtualReportDefinition:
    key: VirtualReportKey
    length: int
    readable: bool = True
    writable: bool = False
    write_updates_state: bool = False

    def __post_init__(self) -> None:
        if self.length <= 0:
            raise VirtualOracleError("virtual report length must be positive")
        if self.write_updates_state and not self.writable:
            raise VirtualOracleError("state-updating virtual report must be writable")


@dataclass(frozen=True)
class OracleTransaction:
    sequence: int
    action_id: int | None
    direction: OracleDirection
    kind: OracleTransferKind
    key: VirtualReportKey
    payload: bytes


@dataclass(frozen=True)
class OracleAction:
    identifier: int
    label: str
    parameters: tuple[tuple[str, object], ...]
    start_sequence: int
    end_sequence: int


@dataclass(frozen=True)
class DifferentialByte:
    key: VirtualReportKey
    transfer_ordinal: int
    offset: int
    values: tuple[int, ...]


class VirtualPeripheralOracle:
    """Strict virtual report-state model and vendor-traffic recorder."""

    def __init__(
        self,
        definitions: tuple[VirtualReportDefinition, ...],
        *,
        initial_state: Mapping[VirtualReportKey, bytes] | None = None,
    ) -> None:
        if not definitions:
            raise VirtualOracleError("virtual peripheral requires at least one report")
        self._definitions = {item.key: item for item in definitions}
        if len(self._definitions) != len(definitions):
            raise VirtualOracleError("duplicate virtual report definition")
        self._state: dict[VirtualReportKey, bytes] = {
            key: bytes(item.length) for key, item in self._definitions.items()
        }
        for key, payload in (initial_state or {}).items():
            self.set_state(key, payload)
        self._transactions: list[OracleTransaction] = []
        self._actions: list[OracleAction] = []
        self._active_action: tuple[int, str, tuple[tuple[str, object], ...], int] | None = None
        self._next_action_id = 1

    @property
    def transactions(self) -> tuple[OracleTransaction, ...]:
        return tuple(self._transactions)

    @property
    def actions(self) -> tuple[OracleAction, ...]:
        return tuple(self._actions)

    def _definition(self, key: VirtualReportKey) -> VirtualReportDefinition:
        try:
            return self._definitions[key]
        except KeyError as exc:
            raise VirtualOracleError(f"unknown virtual report {key}") from exc

    def _validate_payload(self, key: VirtualReportKey, payload: bytes) -> bytes:
        definition = self._definition(key)
        payload = bytes(payload)
        if len(payload) != definition.length:
            raise VirtualOracleError(
                f"{key}: expected {definition.length} bytes, received {len(payload)}"
            )
        return payload

    def set_state(self, key: VirtualReportKey, payload: bytes) -> None:
        """Research-side state override.  It creates no fake vendor transaction."""

        self._state[key] = self._validate_payload(key, payload)

    def get_state(self, key: VirtualReportKey) -> bytes:
        return self._state[self._definition(key).key]

    def _record(
        self,
        direction: OracleDirection,
        kind: OracleTransferKind,
        key: VirtualReportKey,
        payload: bytes,
    ) -> OracleTransaction:
        sequence = len(self._transactions)
        action_id = self._active_action[0] if self._active_action else None
        transaction = OracleTransaction(sequence, action_id, direction, kind, key, bytes(payload))
        self._transactions.append(transaction)
        return transaction

    def get_report(self, key: VirtualReportKey) -> bytes:
        definition = self._definition(key)
        if not definition.readable:
            raise VirtualOracleError(f"{key}: report is not readable")
        payload = self._state[key]
        self._record(OracleDirection.DEVICE_TO_HOST, OracleTransferKind.GET_REPORT, key, payload)
        return payload

    def set_report(self, key: VirtualReportKey, payload: bytes) -> None:
        definition = self._definition(key)
        if not definition.writable:
            raise VirtualOracleError(f"{key}: report is not writable")
        payload = self._validate_payload(key, payload)
        self._record(OracleDirection.HOST_TO_DEVICE, OracleTransferKind.SET_REPORT, key, payload)
        if definition.write_updates_state:
            self._state[key] = payload

    def output_report(self, key: VirtualReportKey, payload: bytes) -> None:
        definition = self._definition(key)
        if key.report_type != "output" or not definition.writable:
            raise VirtualOracleError(f"{key}: report is not a writable output report")
        payload = self._validate_payload(key, payload)
        self._record(OracleDirection.HOST_TO_DEVICE, OracleTransferKind.OUTPUT_REPORT, key, payload)
        if definition.write_updates_state:
            self._state[key] = payload

    @contextmanager
    def action(self, label: str, **parameters: object) -> Iterator[int]:
        """Record an explicit vendor-UI semantic action around transport calls."""

        if not label.strip() or self._active_action is not None:
            raise VirtualOracleError("oracle actions must be non-empty and non-nested")
        identifier = self._next_action_id
        self._next_action_id += 1
        params = tuple(sorted(parameters.items()))
        start = len(self._transactions)
        self._active_action = (identifier, label, params, start)
        try:
            yield identifier
        finally:
            active = self._active_action
            self._active_action = None
            if active is not None:
                self._actions.append(OracleAction(
                    active[0], active[1], active[2], active[3], len(self._transactions)
                ))

    def action_transactions(self, action_id: int) -> tuple[OracleTransaction, ...]:
        if not any(item.identifier == action_id for item in self._actions):
            raise VirtualOracleError(f"unknown or unfinished action {action_id}")
        return tuple(item for item in self._transactions if item.action_id == action_id)

    def differential_write_bytes(self, action_ids: tuple[int, ...]) -> tuple[DifferentialByte, ...]:
        """Find byte positions that vary across aligned host-write observations.

        Transactions align by ``(report key, transfer kind, ordinal within that
        action)``.  A missing aligned write is treated as ambiguity and omitted,
        rather than comparing unrelated packets.
        """

        if len(action_ids) < 2 or len(set(action_ids)) != len(action_ids):
            raise VirtualOracleError("differential analysis requires distinct actions")
        per_action: list[dict[tuple[VirtualReportKey, OracleTransferKind, int], bytes]] = []
        for action_id in action_ids:
            counters: dict[tuple[VirtualReportKey, OracleTransferKind], int] = {}
            aligned: dict[tuple[VirtualReportKey, OracleTransferKind, int], bytes] = {}
            for item in self.action_transactions(action_id):
                if item.direction is not OracleDirection.HOST_TO_DEVICE:
                    continue
                base = (item.key, item.kind)
                ordinal = counters.get(base, 0)
                counters[base] = ordinal + 1
                aligned[(item.key, item.kind, ordinal)] = item.payload
            per_action.append(aligned)
        common = set(per_action[0])
        for mapping in per_action[1:]:
            common &= set(mapping)
        result: list[DifferentialByte] = []
        for key, kind, ordinal in sorted(common, key=repr):
            payloads = [mapping[(key, kind, ordinal)] for mapping in per_action]
            if len({len(payload) for payload in payloads}) != 1:
                continue
            for offset, values in enumerate(zip(*payloads)):
                if len(set(values)) > 1:
                    result.append(DifferentialByte(key, ordinal, offset, tuple(values)))
        return tuple(result)

    def emit_action_evidence(
        self,
        graph: EvidenceGraph,
        action_id: int,
        *,
        parents: tuple[str, ...] = (),
        source: str = "virtual-peripheral-oracle",
    ) -> tuple[str, ...]:
        """Persist oracle observations as experiment/frame evidence, never proof."""

        action = next((item for item in self._actions if item.identifier == action_id), None)
        if action is None:
            raise VirtualOracleError(f"unknown or unfinished action {action_id}")
        action_claim = json.dumps({
            "label": action.label,
            "parameters": list(action.parameters),
            "start_sequence": action.start_sequence,
            "end_sequence": action.end_sequence,
        }, sort_keys=True, separators=(",", ":"))
        experiment_id = graph.add(EvidenceNode("experiment", action_claim, source, parents))
        result = [experiment_id]
        for transaction in self.action_transactions(action_id):
            claim = json.dumps({
                "sequence": transaction.sequence,
                "direction": transaction.direction.value,
                "kind": transaction.kind.value,
                "interface": transaction.key.interface_number,
                "report_type": transaction.key.report_type,
                "report_id": transaction.key.report_id,
                "payload_hex": transaction.payload.hex(),
            }, sort_keys=True, separators=(",", ":"))
            result.append(graph.add(EvidenceNode("frame", claim, source, (experiment_id,))))
        return tuple(result)
