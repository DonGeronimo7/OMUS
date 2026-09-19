"""Capture complete known-good polling-rate transactions for inference.

The proven native backend acts only as a teacher. Raw HidSession TX/RX is
recorded without protocol labels, and Linux evdev timestamps independently
measure the resulting report rate. No generic polling write is performed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
import threading

from .device_profiles import get_profile_directory
from .device_topology import build_device_graph
from .discovery import get_mouse_devices, select_mouse_device
from .hardware.base import HardwareError
from .hardware.native_hid import NativeHidBackend
from .hid_session import HidSession, RawHidTraceEvent
from .hidpp_driver import ONBOARD_MODE
from .sensor_calibration import (
    EV_REL,
    EV_SYN,
    REL_X,
    REL_Y,
    SYN_REPORT,
    capture_evdev_motion,
    estimate_peak_polling_hz,
    normalize_event,
)


DEFAULT_RATES = (1000, 500, 250, 125)


def _positive_csv(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("rates must be comma-separated integers") from exc
    if not result or any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError("rates must be positive")
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("rates must be unique")
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
        prog="mouse-control-polling-trace",
        description=(
            "Capture complete proven polling-rate transactions plus independent "
            "evdev timing evidence for later generic inference."
        ),
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument(
        "--rates",
        type=_positive_csv,
        default=DEFAULT_RATES,
        metavar="HZ,...",
        help="teacher demonstration rates (default: 1000,500,250,125)",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=4.0,
        help="evdev physical verification capture window (default: 4 seconds)",
    )
    parser.add_argument(
        "--i-understand-this-writes-hardware",
        action="store_true",
    )
    return parser


def _pick(index: int | None):
    mice = get_mouse_devices()
    if not mice:
        raise HardwareError("no mouse devices found")
    if index is None:
        return select_mouse_device(mice)
    if index < 1 or index > len(mice):
        raise HardwareError(f"--device must be between 1 and {len(mice)}")
    return mice[index - 1]


def estimate_polling_from_events(events):
    """Return raw peak Hz, nearest standard rate, and relative error."""

    timestamps = []
    motion = False
    for raw in events:
        event = normalize_event(raw)
        if event.event_type == EV_REL and event.code in (REL_X, REL_Y):
            motion = motion or event.value != 0
        elif event.event_type == EV_SYN and event.code == SYN_REPORT:
            if motion:
                timestamps.append(event.timestamp_ns)
            motion = False
    return estimate_peak_polling_hz(timestamps)


def _render_trace(events: tuple[RawHidTraceEvent, ...]) -> str:
    if not events:
        return "  (no raw HID traffic captured)"
    start = events[0].timestamp_ns
    lines = []
    for event in events:
        delta_us = (event.timestamp_ns - start) / 1000
        lines.append(
            f"  +{delta_us:9.1f} us {event.direction.upper():2} "
            f"[{len(event.data):2d}] {event.data.hex(' ')}"
        )
    return "\n".join(lines)


def _stable_interface(physical, events):
    paths = {Path(event.path) for event in events}
    nodes = [node for node in physical.hidraw_nodes if node.path in paths]
    # All recorded traffic should come from the one protocol responder.
    unique = []
    for node in nodes:
        if node not in unique:
            unique.append(node)
    if len(unique) != 1:
        raise HardwareError(
            f"expected one stable polling transport interface, found {len(unique)}"
        )
    return unique[0]


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    if os.geteuid() == 0:
        try:
            uid = int(os.environ["SUDO_UID"])
            gid = int(os.environ["SUDO_GID"])
        except (KeyError, ValueError):
            return
        try:
            os.chown(path.parent, uid, gid)
            os.chown(path, uid, gid)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.i_understand_this_writes_hardware:
        print(
            "Refusing to run without --i-understand-this-writes-hardware.",
            file=sys.stderr,
        )
        return 2
    if args.window <= 0:
        print("--window must be positive", file=sys.stderr)
        return 2

    mouse = None
    backend = None
    original_rate = None
    original_mode = None

    try:
        mouse = _pick(args.device)
        physical = build_device_graph(mouse)
        if physical.ambiguous:
            raise HardwareError("physical identity is ambiguous")

        trace = TraceBuffer()

        def session_factory(path):
            return HidSession(path, trace_callback=trace.append)

        backend = NativeHidBackend(session_factory=session_factory)
        if not backend.supports_device(mouse):
            raise HardwareError("selected device has no proven native polling teacher")

        supported = tuple(backend.get_polling_rates(mouse))
        missing = [rate for rate in args.rates if rate not in supported]
        if missing:
            raise HardwareError(
                f"requested teacher rates are not supported: {missing}; supported={supported}"
            )

        driver = backend._driver(mouse)
        original_mode = driver.get_control_mode()
        original_rate = driver.get_report_rate()
        trace.clear()

        print("Mouse Control — Raw Polling Write Demonstration")
        print("==============================================")
        print(
            f"Device: {mouse.name} "
            f"[{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]"
        )
        print(f"Original control mode: 0x{original_mode:02x}")
        print(f"Original polling rate: {original_rate} Hz")
        print(f"Teacher rates: {', '.join(map(str, args.rates))}")
        print("Generic polling write authority: NONE")
        print(
            "Each demonstration is reset to onboard mode before capture so the "
            "complete prerequisite -> write -> verification transaction is visible."
        )

        demonstrations = []
        all_events = []
        for index, target in enumerate(args.rates, start=1):
            # Reset outside the capture window. The demonstration itself must
            # show every prerequisite needed to move from the same known mode.
            if driver.get_control_mode() != ONBOARD_MODE:
                driver.set_control_mode(ONBOARD_MODE)
                if driver.get_control_mode() != ONBOARD_MODE:
                    raise HardwareError("failed to reset onboard mode before demonstration")
            trace.clear()

            backend.set_polling_rate(mouse, target)
            events = trace.snapshot()
            all_events.extend(events)

            print(f"\n[{index}/{len(args.rates)}] target {target} Hz")
            print(_render_trace(events))

            print(
                f"Physical verification: move the mouse rapidly and continuously "
                f"for {args.window:g} seconds."
            )
            input("Press Enter, then begin moving immediately... ")
            captured = capture_evdev_motion(
                mouse.path,
                seconds=args.window,
                exclusive=True,
            )
            peak_hz, standard_hz, error = estimate_polling_from_events(captured)
            if peak_hz is None:
                print("  observed polling: insufficient motion/timing data")
            elif standard_hz is None:
                print(f"  observed polling: {peak_hz:.1f} Hz (no standard-rate match)")
            else:
                print(
                    f"  observed polling: {peak_hz:.1f} Hz -> ~{standard_hz} Hz "
                    f"(error {error * 100:.1f}%)"
                )

            demonstrations.append(
                {
                    "target_hz": int(target),
                    "physical_peak_hz": peak_hz,
                    "physical_standard_hz": standard_hz,
                    "physical_error_fraction": error,
                    "events": [
                        {
                            "direction": event.direction,
                            "length": len(event.data),
                            "data_hex": event.data.hex(),
                            "relative_us": (
                                (event.timestamp_ns - events[0].timestamp_ns) / 1000
                                if events else 0.0
                            ),
                        }
                        for event in events
                    ],
                }
            )

        node = _stable_interface(physical, tuple(all_events))
        payload = {
            "schema_version": 1,
            "profile_kind": "polling-demonstrations",
            "write_authorized": False,
            "identity": {
                "bus": physical.bus,
                "vendor_id": physical.vendor_id,
                "product_id": physical.product_id,
            },
            "fingerprints": {
                "model": physical.model_fingerprint,
                "instance": physical.instance_fingerprint,
            },
            "interface": {
                "bus": node.bus,
                "vendor_id": node.vendor_id,
                "product_id": node.product_id,
                "interface_number": node.interface_number,
                "descriptor_sha256": node.descriptor_sha256,
            },
            "demonstrations": demonstrations,
        }
        vendor = physical.vendor_id or 0
        product = physical.product_id or 0
        destination = (
            get_profile_directory()
            / "polling-demonstrations"
            / f"{vendor:04x}-{product:04x}-{physical.model_fingerprint[:16]}.json"
        )
        _atomic_json(destination, payload)

        print("\nPolling demonstration capture complete")
        print("--------------------------------------")
        print(f"Saved raw corpus: {destination}")
        print("Write authority: false")
        print(
            "Next step: infer the prerequisite/mode grammar and rate codec from "
            "these complete transactions, then replay one transition generically."
        )
        return 0

    except KeyboardInterrupt:
        print("\nPolling trace cancelled.", file=sys.stderr)
        return 130
    except (HardwareError, OSError, PermissionError) as exc:
        print(f"Polling trace failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if backend is not None and mouse is not None:
            try:
                driver = backend._driver(mouse)
                if original_rate is not None:
                    # Native safe path establishes host mode as needed.
                    backend.set_polling_rate(mouse, original_rate)
                if original_mode is not None and driver.get_control_mode() != original_mode:
                    driver.set_control_mode(original_mode)
                    restored = driver.get_control_mode()
                    if restored != original_mode:
                        raise HardwareError(
                            f"control-mode restoration read 0x{restored:02x}"
                        )
                if original_rate is not None:
                    print(
                        f"\nRestored polling/control state: {original_rate} Hz, "
                        f"mode 0x{original_mode:02x}"
                    )
            except Exception as exc:
                print(f"\nWARNING: polling restoration failed: {exc}", file=sys.stderr)
            backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
