"""Experimental raw HID demonstration capture feeding generic write discovery.

A proven native backend acts only as a teacher/actuator. The learned pipeline
receives opaque raw TX/RX packets plus semantic target labels; it does not
receive HID++ feature/function names.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import os
import sys
import threading

from .device_topology import build_device_graph
from .discovery import get_mouse_devices, select_mouse_device
from .hardware.base import HardwareError
from .hardware.native_hid import NativeHidBackend
from .hid_session import HidSession, RawHidTraceEvent
from .learned_operations import (
    LearnedOperationStore,
    StableDeviceIdentity,
    StableInterfaceIdentity,
    operation_from_grammar,
)
from .transaction_inference import (
    DemonstratedTransaction,
    TransactionInferenceError,
    demonstration_from_trace,
    infer_transaction_grammar,
)


DEFAULT_DPI_VALUES = (800, 1500, 2000, 2500, 3000)


def _dpi_values(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("DPI values must be comma-separated integers") from exc
    if not result or any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError("DPI values must contain positive integers")
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("DPI values must be unique")
    return result


@dataclass
class TraceBuffer:
    _events: list[RawHidTraceEvent] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, event: RawHidTraceEvent) -> None:
        with self._lock:
            self._events.append(event)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def snapshot(self) -> tuple[RawHidTraceEvent, ...]:
        with self._lock:
            return tuple(self._events)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-write-trace",
        description=(
            "Capture proven semantic writes as opaque raw HID demonstrations, "
            "infer a protocol-neutral transaction grammar, and persist it as "
            "DEMONSTRATED with no write authority."
        ),
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument(
        "--dpi-values",
        type=_dpi_values,
        default=DEFAULT_DPI_VALUES,
        metavar="DPI,...",
    )
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument(
        "--i-understand-this-writes-hardware",
        action="store_true",
        help="required acknowledgement that the proven teacher changes live DPI",
    )
    return parser


def _pick_mouse(index: int | None):
    mice = get_mouse_devices()
    if not mice:
        print("No mouse devices found.", file=sys.stderr)
        return None, 1
    if index is None:
        return select_mouse_device(mice), 0
    if index < 1 or index > len(mice):
        print(f"--device must be between 1 and {len(mice)}", file=sys.stderr)
        return None, 2
    return mice[index - 1], 0


def _render_trace(events: tuple[RawHidTraceEvent, ...]) -> str:
    if not events:
        return "  (no raw HID traffic captured)"
    start = events[0].timestamp_ns
    lines = []
    for event in events:
        delta_us = (event.timestamp_ns - start) / 1000
        lines.append(
            f"  +{delta_us:9.1f} us {event.direction.upper():2} "
            f"{event.path} [{len(event.data):2d}] {event.data.hex(' ')}"
        )
    return "\n".join(lines)


def _stable_interface(physical, demonstrations):
    paths = {
        os.path.realpath(event.path)
        for _value, events in demonstrations
        for event in events
        if event.direction in {"tx", "rx"}
    }
    if len(paths) != 1:
        raise TransactionInferenceError(
            f"demonstrations used {len(paths)} live hidraw paths; refusing ambiguous persistence"
        )
    live_path = next(iter(paths))
    candidates = [
        node for node in physical.hidraw_nodes
        if os.path.realpath(os.fspath(node.path)) == live_path
    ]
    if len(candidates) != 1:
        raise TransactionInferenceError(
            "could not map the demonstrated hidraw transport to one stable physical interface"
        )
    node = candidates[0]
    if not node.descriptor_sha256:
        raise TransactionInferenceError(
            "demonstrated interface lacks descriptor fingerprint; refusing writable learning"
        )
    return node


def _print_grammar(grammar) -> None:
    field = grammar.write_field
    print("\nLearned protocol-neutral candidate")
    print("----------------------------------")
    print(f"Demonstrations: {grammar.demonstration_count}")
    print(f"Frame length: {grammar.write_request.length} bytes")
    print(
        f"Write semantic field: offset {field.offset}, width {field.width}, "
        f"codec {field.codec.kind.value}"
    )
    print(
        f"Readback semantic field: offset {grammar.read_field.offset}, "
        f"width {grammar.read_field.width}, codec {grammar.read_field.codec.kind.value}"
    )
    print(
        f"Write invariant bytes: {grammar.write_request.constant_count}/"
        f"{grammar.write_request.length}"
    )
    print(
        "Demonstrated values: "
        + ", ".join(str(value) for value in grammar.demonstrated_values)
    )
    print("Status: DEMONSTRATED")
    print("Write authority: false")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.i_understand_this_writes_hardware:
        print(
            "Refusing to run without --i-understand-this-writes-hardware.",
            file=sys.stderr,
        )
        return 2

    selected, status = _pick_mouse(args.device)
    if selected is None:
        return status

    trace = TraceBuffer()

    def session_factory(path):
        return HidSession(path, trace_callback=trace.append)

    backend = NativeHidBackend(session_factory=session_factory)
    original_dpi: int | None = None
    demonstrations: list[tuple[int, tuple[RawHidTraceEvent, ...]]] = []

    print("Mouse Control — Raw DPI Write Demonstration")
    print("==========================================")
    print(
        f"Device: {selected.name} "
        f"[{(selected.vendor or 0):04x}:{(selected.product or 0):04x}]"
    )
    print("Actuator: existing proven protocol teacher")
    print("Learner input: semantic target + opaque raw TX/RX only")
    print("Generic write authority: NONE")

    try:
        if not backend.supports_device(selected):
            print(
                "Selected device did not bind to the proven teacher. No write attempted.",
                file=sys.stderr,
            )
            return 1

        initial = backend.get_dpi_state(selected)
        if initial is None:
            print("Could not read initial DPI state.", file=sys.stderr)
            return 1
        original_dpi = initial.x_dpi
        supported = set(backend.get_dpi_values(selected))
        unsupported = tuple(value for value in args.dpi_values if value not in supported)
        if unsupported:
            print(
                f"Requested values are not proven supported: {unsupported}",
                file=sys.stderr,
            )
            return 1

        print(f"Original confirmed DPI: {original_dpi}")
        print(f"Demonstration targets: {', '.join(str(v) for v in args.dpi_values)}")

        for index, target in enumerate(args.dpi_values, start=1):
            before = backend.get_dpi_state(selected)
            if before is None:
                raise HardwareError("pre-write DPI readback unavailable")
            trace.clear()
            confirmed = backend.set_dpi(selected, target)
            events = trace.snapshot()
            demo = demonstration_from_trace(target, events)
            if len(demo.tx_packets) != 2 or len(demo.rx_packets) != 2:
                raise TransactionInferenceError(
                    f"target {target}: expected 2 TX + 2 RX packets, "
                    f"observed {len(demo.tx_packets)} TX + {len(demo.rx_packets)} RX"
                )
            demonstrations.append((target, events))

            print()
            print(
                f"[{index}/{len(args.dpi_values)}] "
                f"{before.x_dpi} -> target {target} -> confirmed {confirmed.x_dpi}"
            )
            print(_render_trace(events))

        learned = tuple(
            demonstration_from_trace(value, events)
            for value, events in demonstrations
        )
        grammar = infer_transaction_grammar(learned)
        _print_grammar(grammar)

        physical = build_device_graph(selected)
        node = _stable_interface(physical, demonstrations)
        operation = operation_from_grammar(
            grammar,
            identity=StableDeviceIdentity(
                bus=physical.bus,
                vendor_id=physical.vendor_id,
                product_id=physical.product_id,
                model_fingerprint=physical.model_fingerprint,
                instance_fingerprint=physical.instance_fingerprint,
            ),
            interface=StableInterfaceIdentity(
                bus=node.bus,
                vendor_id=node.vendor_id,
                product_id=node.product_id,
                interface_number=node.interface_number,
                descriptor_sha256=node.descriptor_sha256,
            ),
        )

        if args.no_save:
            print("Learned operation not saved (--no-save).")
        else:
            destination = LearnedOperationStore().save(operation)
            print(f"Saved DEMONSTRATED learned operation: {destination}")

        print(
            "\nNo generic write was executed. Promotion requires a separate "
            "exact-model reversible replay plus physical CPI verification."
        )
        return 0

    except (HardwareError, OSError, PermissionError, TransactionInferenceError) as exc:
        print(f"Write-learning experiment failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nWrite-learning experiment cancelled.", file=sys.stderr)
        return 130
    finally:
        if original_dpi is not None:
            try:
                current = backend.get_dpi_state(selected)
                if current is not None and current.x_dpi != original_dpi:
                    trace.clear()
                    backend.set_dpi(selected, original_dpi)
                    print(f"\nRestored original DPI: {original_dpi}")
            except Exception as exc:
                print(
                    f"\nWARNING: failed to restore original DPI {original_dpi}: {exc}",
                    file=sys.stderr,
                )
        backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
