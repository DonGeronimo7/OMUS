# SPDX-License-Identifier: AGPL-3.0-or-later
"""Protocol-neutral inference and execution for demonstrated polling transactions.

This laboratory layer learns an exact-model polling transaction from the raw
teacher corpus.  It deliberately does not persist write authority.  Execution
is restricted to semantic rates present in the demonstrations.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import json
import time

from .hid_session import HidrawIo
from .protocol_codec import infer_polling_codecs


class PollingReplayError(RuntimeError):
    """The polling corpus is ambiguous, unsafe, or failed during replay."""


@dataclass(frozen=True)
class PacketPattern:
    bytes_: tuple[int | None, ...]

    @property
    def length(self) -> int:
        return len(self.bytes_)

    def matches(self, packet: bytes) -> bool:
        return (
            len(packet) == len(self.bytes_)
            and all(
                expected is None or packet[index] == expected
                for index, expected in enumerate(self.bytes_)
            )
        )


@dataclass(frozen=True)
class ReplayStep:
    request: PacketPattern
    response: PacketPattern
    request_semantic_offset: int | None = None
    response_semantic_offset: int | None = None


@dataclass(frozen=True)
class PollingReplayGrammar:
    steps: tuple[ReplayStep, ...]
    write_step_index: int
    read_step_index: int
    raw_to_hz: Mapping[int, int]
    demonstrated_rates: tuple[int, ...]

    def raw_for_rate(self, rate_hz: int) -> int:
        rate = int(rate_hz)
        if rate not in self.demonstrated_rates:
            raise PollingReplayError(
                f"{rate} Hz was not demonstrated; generic replay is restricted "
                "to the teacher corpus"
            )
        matches = [raw for raw, semantic in self.raw_to_hz.items() if semantic == rate]
        if len(matches) != 1:
            raise PollingReplayError(
                f"expected one raw encoding for {rate} Hz, found {len(matches)}"
            )
        return int(matches[0])


@dataclass(frozen=True)
class _Segment:
    request: bytes
    responses: tuple[bytes, ...]


def _event_bytes(event: Mapping[str, object]) -> bytes:
    try:
        return bytes.fromhex(str(event["data_hex"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PollingReplayError(f"invalid raw event: {exc}") from exc


def _segments(events: Sequence[Mapping[str, object]]) -> tuple[_Segment, ...]:
    result: list[_Segment] = []
    request: bytes | None = None
    responses: list[bytes] = []
    for event in events:
        direction = str(event.get("direction", "")).lower()
        if direction == "tx":
            if request is not None:
                result.append(_Segment(request, tuple(responses)))
            request = _event_bytes(event)
            responses = []
        elif direction == "rx" and request is not None:
            responses.append(_event_bytes(event))
    if request is not None:
        result.append(_Segment(request, tuple(responses)))
    if not result:
        raise PollingReplayError("demonstration contains no TX requests")
    if any(not segment.responses for segment in result):
        raise PollingReplayError(
            "every demonstrated request must have at least one following RX packet"
        )
    return tuple(result)


def _exact_pattern(packets: Sequence[bytes], *, label: str) -> PacketPattern:
    if not packets:
        raise PollingReplayError(f"{label}: no packets")
    lengths = {len(packet) for packet in packets}
    if len(lengths) != 1:
        raise PollingReplayError(f"{label}: packet lengths are not stable")
    first = packets[0]
    if any(packet != first for packet in packets[1:]):
        raise PollingReplayError(f"{label}: bytes vary unexpectedly")
    return PacketPattern(tuple(first))


def _semantic_request_pattern(
    packets: Sequence[bytes],
    rates: Sequence[int],
    *,
    label: str,
) -> tuple[PacketPattern, int, dict[int, int]]:
    if not packets:
        raise PollingReplayError(f"{label}: no packets")
    lengths = {len(packet) for packet in packets}
    if len(lengths) != 1:
        raise PollingReplayError(f"{label}: packet lengths are not stable")
    width = len(packets[0])
    candidates: list[tuple[int, tuple[int | None, ...], dict[int, int]]] = []

    for offset in range(width):
        raw_values = tuple(packet[offset] for packet in packets)
        if len(set(raw_values)) < 2:
            continue

        hypotheses = infer_polling_codecs(raw_values)
        mappings: dict[tuple[tuple[int, int], ...], dict[int, int]] = {}
        for hypothesis in hypotheses:
            mapping = {int(raw): int(rate) for raw, rate in hypothesis.mapping.items()}
            if all(mapping.get(raw) == int(rate) for raw, rate in zip(raw_values, rates)):
                mappings[tuple(sorted(mapping.items()))] = mapping

        for mapping in mappings.values():
            pattern: list[int | None] = []
            valid = True
            for index in range(width):
                values = {packet[index] for packet in packets}
                if index == offset:
                    pattern.append(None)
                elif len(values) == 1:
                    pattern.append(next(iter(values)))
                else:
                    valid = False
                    break
            if valid:
                candidates.append((offset, tuple(pattern), mapping))

    unique: dict[tuple[int, tuple[int | None, ...], tuple[tuple[int, int], ...]],
                 tuple[int, tuple[int | None, ...], dict[int, int]]] = {}
    for candidate in candidates:
        offset, pattern, mapping = candidate
        key = (offset, pattern, tuple(sorted(mapping.items())))
        unique[key] = candidate

    if len(unique) != 1:
        raise PollingReplayError(
            f"{label}: expected one polling semantic byte, found {len(unique)}"
        )
    offset, pattern, mapping = next(iter(unique.values()))
    return PacketPattern(pattern), offset, mapping


def _candidate_response_sets(
    windows: Sequence[Sequence[bytes]],
    *,
    max_combinations: int = 512,
) -> Iterable[tuple[bytes, ...]]:
    if not windows or any(not window for window in windows):
        return ()
    common_lengths = set(len(packet) for packet in windows[0])
    for window in windows[1:]:
        common_lengths &= {len(packet) for packet in window}

    emitted: set[tuple[bytes, ...]] = set()
    output: list[tuple[bytes, ...]] = []
    for length in sorted(common_lengths):
        groups = [
            tuple(packet for packet in window if len(packet) == length)
            for window in windows
        ]
        combinations = 1
        for group in groups:
            combinations *= len(group)
        if combinations > max_combinations:
            # Ambiguous high-volume async traffic is not safe to guess through.
            continue
        for selection in product(*groups):
            key = tuple(selection)
            if key not in emitted:
                emitted.add(key)
                output.append(key)
    return tuple(output)


def _constant_response_pattern(
    windows: Sequence[Sequence[bytes]],
    *,
    label: str,
) -> PacketPattern:
    # A packet that merely repeats across demonstrations may be asynchronous
    # traffic.  The teacher requests were synchronous, so the real completion
    # response should also occupy the latest consistent position in the RX
    # window before the next TX.  Combine both facts; never choose by position
    # alone and never choose by repeated bytes alone.
    stable: dict[bytes, PacketPattern] = {}
    for selection in _candidate_response_sets(windows):
        if all(packet == selection[0] for packet in selection[1:]):
            stable[selection[0]] = PacketPattern(tuple(selection[0]))

    if not stable:
        raise PollingReplayError(
            f"{label}: no stable correlated response was found"
        )

    scored = []
    for packet, pattern in stable.items():
        positions = []
        for window in windows:
            indexes = [index for index, item in enumerate(window) if item == packet]
            if not indexes:
                break
            # Normalize position so differently sized async windows are comparable.
            positions.append((max(indexes) + 1) / len(window))
        if len(positions) == len(windows):
            scored.append((sum(positions) / len(positions), packet, pattern))

    if not scored:
        raise PollingReplayError(
            f"{label}: stable packets could not be correlated positionally"
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score = scored[0][0]
    best = [item for item in scored if abs(item[0] - best_score) < 1e-9]
    if len(best) != 1:
        raise PollingReplayError(
            f"{label}: synchronous response correlation remains ambiguous"
        )
    return best[0][2]


def _semantic_response_pattern(
    windows: Sequence[Sequence[bytes]],
    rates: Sequence[int],
    raw_to_hz: Mapping[int, int],
    *,
    label: str,
) -> tuple[PacketPattern, int]:
    candidates: dict[tuple[tuple[int | None, ...], int], tuple[PacketPattern, int]] = {}
    for selection in _candidate_response_sets(windows):
        lengths = {len(packet) for packet in selection}
        if len(lengths) != 1:
            continue
        width = len(selection[0])
        for offset in range(width):
            raw_values = tuple(packet[offset] for packet in selection)
            if not all(
                raw_to_hz.get(int(raw)) == int(rate)
                for raw, rate in zip(raw_values, rates)
            ):
                continue
            pattern: list[int | None] = []
            valid = True
            for index in range(width):
                values = {packet[index] for packet in selection}
                if index == offset:
                    pattern.append(None)
                elif len(values) == 1:
                    pattern.append(next(iter(values)))
                else:
                    valid = False
                    break
            if not valid:
                continue
            key = (tuple(pattern), offset)
            candidates[key] = (PacketPattern(tuple(pattern)), offset)

    if len(candidates) != 1:
        raise PollingReplayError(
            f"{label}: expected one semantic readback response, found {len(candidates)}"
        )
    return next(iter(candidates.values()))


def infer_polling_replay_grammar(profile: Mapping[str, object]) -> PollingReplayGrammar:
    """Infer one exact demonstrated multi-step polling transaction.

    Request alignment is positional across complete demonstrations that began
    from the same known teacher-established state.  The write field must be the
    only varying request byte and must fit an existing polling codec hypothesis.
    Responses are selected only when one structurally stable correlation exists
    across every demonstration; ambiguity is rejected.
    """
    if profile.get("profile_kind") not in {
        "polling-demonstrations",
        "polling-host-demonstrations",
    }:
        raise PollingReplayError("unexpected polling corpus kind")
    if profile.get("write_authorized") is not False:
        raise PollingReplayError(
            "teacher corpus must remain explicitly non-authoritative"
        )

    raw_demonstrations = profile.get("demonstrations")
    if not isinstance(raw_demonstrations, list) or len(raw_demonstrations) < 3:
        raise PollingReplayError("at least three polling demonstrations are required")

    rates: list[int] = []
    demonstrations: list[tuple[_Segment, ...]] = []
    for raw in raw_demonstrations:
        if not isinstance(raw, Mapping):
            raise PollingReplayError("invalid demonstration entry")
        try:
            rate = int(raw["target_hz"])
            events = raw["events"]
        except (KeyError, TypeError, ValueError) as exc:
            raise PollingReplayError(f"invalid demonstration: {exc}") from exc
        if rate <= 0 or not isinstance(events, list):
            raise PollingReplayError("invalid target rate or event list")
        rates.append(rate)
        demonstrations.append(_segments(events))

    if len(set(rates)) != len(rates):
        raise PollingReplayError("demonstrated polling rates must be distinct")
    step_counts = {len(demo) for demo in demonstrations}
    if len(step_counts) != 1:
        raise PollingReplayError("demonstrations do not share one transaction length")
    step_count = next(iter(step_counts))
    if step_count < 2:
        raise PollingReplayError("polling transaction is too short to prove safely")

    write_candidates: list[tuple[int, PacketPattern, int, dict[int, int]]] = []
    for step_index in range(step_count):
        requests = tuple(demo[step_index].request for demo in demonstrations)
        try:
            pattern, offset, mapping = _semantic_request_pattern(
                requests, rates, label=f"request step {step_index + 1}"
            )
        except PollingReplayError:
            continue
        write_candidates.append((step_index, pattern, offset, mapping))

    if len(write_candidates) != 1:
        raise PollingReplayError(
            f"expected one polling write request step, found {len(write_candidates)}"
        )
    write_step, write_pattern, write_offset, raw_to_hz = write_candidates[0]

    request_patterns: list[PacketPattern] = []
    for step_index in range(step_count):
        packets = tuple(demo[step_index].request for demo in demonstrations)
        if step_index == write_step:
            request_patterns.append(write_pattern)
        else:
            request_patterns.append(
                _exact_pattern(packets, label=f"request step {step_index + 1}")
            )

    read_candidates: list[tuple[int, PacketPattern, int]] = []
    for step_index in range(step_count):
        windows = tuple(demo[step_index].responses for demo in demonstrations)
        try:
            pattern, offset = _semantic_response_pattern(
                windows, rates, raw_to_hz, label=f"response step {step_index + 1}"
            )
        except PollingReplayError:
            continue
        read_candidates.append((step_index, pattern, offset))

    if len(read_candidates) != 1:
        raise PollingReplayError(
            f"expected one polling readback response step, found {len(read_candidates)}"
        )
    read_step, read_pattern, read_offset = read_candidates[0]

    steps: list[ReplayStep] = []
    for step_index in range(step_count):
        windows = tuple(demo[step_index].responses for demo in demonstrations)
        response_pattern = (
            read_pattern
            if step_index == read_step
            else _constant_response_pattern(
                windows, label=f"response step {step_index + 1}"
            )
        )
        steps.append(
            ReplayStep(
                request=request_patterns[step_index],
                response=response_pattern,
                request_semantic_offset=(
                    write_offset if step_index == write_step else None
                ),
                response_semantic_offset=(
                    read_offset if step_index == read_step else None
                ),
            )
        )

    return PollingReplayGrammar(
        steps=tuple(steps),
        write_step_index=write_step,
        read_step_index=read_step,
        raw_to_hz=dict(raw_to_hz),
        demonstrated_rates=tuple(sorted(rates)),
    )


def load_polling_corpus(path: Path) -> Mapping[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PollingReplayError(f"could not load polling corpus {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PollingReplayError("polling corpus root must be an object")
    return data


def matching_interface_node(profile: Mapping[str, object], physical):
    interface = profile.get("interface")
    if not isinstance(interface, Mapping):
        raise PollingReplayError("polling corpus has no stable interface identity")

    candidates = []
    for node in physical.hidraw_nodes:
        expected = (
            interface.get("bus"),
            interface.get("vendor_id"),
            interface.get("product_id"),
            interface.get("interface_number"),
            interface.get("descriptor_sha256"),
        )
        actual = (
            node.bus,
            node.vendor_id,
            node.product_id,
            node.interface_number,
            node.descriptor_sha256,
        )
        if all(want is None or want == have for want, have in zip(expected, actual)):
            candidates.append(node)
    if len(candidates) != 1:
        raise PollingReplayError(
            f"expected exactly one live interface matching the polling corpus, "
            f"found {len(candidates)}"
        )
    return candidates[0]


class GenericPollingReplayAdapter:
    """Persistent raw HID session for one inferred polling replay experiment."""

    def __init__(
        self,
        path: str | Path,
        grammar: PollingReplayGrammar,
        *,
        io_factory=HidrawIo,
        timeout: float = 0.40,
    ) -> None:
        self.path = Path(path)
        self.grammar = grammar
        self.timeout = float(timeout)
        self._io = io_factory(self.path)

    def close(self) -> None:
        self._io.close()

    def _render_request(self, step_index: int, target_hz: int) -> bytes:
        step = self.grammar.steps[step_index]
        values = list(step.request.bytes_)
        if step.request_semantic_offset is not None:
            raw = self.grammar.raw_for_rate(target_hz)
            values[step.request_semantic_offset] = raw
        if any(value is None for value in values):
            raise PollingReplayError(
                f"request step {step_index + 1} contains unresolved wildcard bytes"
            )
        return bytes(int(value) for value in values)

    def _exchange(self, request: bytes, response: PacketPattern) -> bytes:
        self._io.write(request)
        deadline = time.monotonic() + self.timeout
        unrelated = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PollingReplayError(
                    f"timed out waiting for inferred response after "
                    f"{unrelated} unrelated packet(s)"
                )
            packet = self._io.read(remaining)
            if packet == b"":
                raise PollingReplayError("hidraw interface disconnected during replay")
            if packet is None:
                continue
            data = bytes(packet)
            if response.matches(data):
                return data
            unrelated += 1

    def execute_with_grammar(
        self,
        grammar: PollingReplayGrammar,
        target_hz: int,
    ) -> int:
        """Execute another inferred grammar on this exact open HID session.

        This is for state-machine laboratories where closing/reopening hidraw
        between control states could change behavior. The adapter's default
        grammar is restored even when execution fails.
        """
        previous = self.grammar
        self.grammar = grammar
        try:
            return self.execute(target_hz)
        finally:
            self.grammar = previous

    def execute(self, target_hz: int) -> int:
        target = int(target_hz)
        self.grammar.raw_for_rate(target)
        readback: int | None = None

        for index, step in enumerate(self.grammar.steps):
            request = self._render_request(index, target)
            reply = self._exchange(request, step.response)
            if step.response_semantic_offset is not None:
                raw = reply[step.response_semantic_offset]
                try:
                    readback = int(self.grammar.raw_to_hz[raw])
                except KeyError as exc:
                    raise PollingReplayError(
                        f"readback raw value 0x{raw:02x} was not demonstrated"
                    ) from exc
                if readback != target:
                    raise PollingReplayError(
                        f"generic polling readback requested {target} Hz, "
                        f"decoded {readback} Hz"
                    )

        if readback is None:
            raise PollingReplayError("transaction completed without semantic readback")
        return readback
