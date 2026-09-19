"""Capture known-good polling transactions that begin in host control mode.

The original polling corpus intentionally demonstrated Onboard -> Host takeover.
This companion corpus teaches the steady-state Host -> Host branch needed for
later polling changes after takeover has already occurred.  The proven native
backend is the teacher; no generic write is performed and no authority is
persisted.
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
from .hidpp_driver import HOST_MODE


DEFAULT_RATES = (1000, 500, 250, 125)


def _positive_csv(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(',') if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError('rates must be comma-separated integers') from exc
    if not result or any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError('rates must be positive integers')
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError('rates must be unique')
    return result


def _anchor_for_target(target: int, rates: tuple[int, ...], preferred: int) -> int:
    """Choose a demonstrated host-state rate different from the target."""
    candidates = tuple(rate for rate in rates if rate != target)
    if not candidates:
        raise HardwareError('host-state demonstration requires at least two rates')
    if preferred in candidates:
        return preferred
    return max(candidates)


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
        prog='mouse-control-polling-host-trace',
        description=(
            'Capture complete proven polling transactions while control is already '
            'in Host mode. No generic polling write is performed.'
        ),
    )
    parser.add_argument('--device', type=int, metavar='N')
    parser.add_argument('--rates', type=_positive_csv, default=DEFAULT_RATES,
                        metavar='HZ,...', help='rates to demonstrate (default: 1000,500,250,125)')
    parser.add_argument('--anchor', type=int, default=1000,
                        help='preferred pre-capture Host-mode rate (default: 1000)')
    parser.add_argument('--i-understand-this-writes-hardware', action='store_true')
    return parser


def _pick(index: int | None):
    mice = get_mouse_devices()
    if not mice:
        raise HardwareError('no mouse devices found')
    if index is None:
        return select_mouse_device(mice)
    if index < 1 or index > len(mice):
        raise HardwareError(f'--device must be between 1 and {len(mice)}')
    return mice[index - 1]


def _render_trace(events: tuple[RawHidTraceEvent, ...]) -> str:
    if not events:
        return '  (no raw HID traffic captured)'
    start = events[0].timestamp_ns
    lines = []
    for event in events:
        delta_us = (event.timestamp_ns - start) / 1000
        lines.append(
            f'  +{delta_us:9.1f} us {event.direction.upper():2} '
            f'[{len(event.data):2d}] {event.data.hex(" ")}'
        )
    return '\n'.join(lines)


def _stable_interface(physical, events):
    paths = {Path(event.path) for event in events}
    nodes = [node for node in physical.hidraw_nodes if node.path in paths]
    unique = []
    for node in nodes:
        if node not in unique:
            unique.append(node)
    if len(unique) != 1:
        raise HardwareError(
            f'expected one stable host-state polling interface, found {len(unique)}'
        )
    return unique[0]


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    os.replace(temporary, path)
    if os.geteuid() == 0:
        try:
            uid = int(os.environ['SUDO_UID'])
            gid = int(os.environ['SUDO_GID'])
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
        print('Refusing to run without --i-understand-this-writes-hardware.', file=sys.stderr)
        return 2
    if args.anchor <= 0:
        print('--anchor must be positive', file=sys.stderr)
        return 2

    mouse = None
    backend = None
    original_rate = None
    original_mode = None

    try:
        mouse = _pick(args.device)
        if mouse is None:
            return 0
        physical = build_device_graph(mouse)
        if physical.ambiguous:
            raise HardwareError('physical identity is ambiguous')

        trace = TraceBuffer()

        def session_factory(path):
            return HidSession(path, trace_callback=trace.append)

        backend = NativeHidBackend(session_factory=session_factory)
        if not backend.supports_device(mouse):
            raise HardwareError('selected device has no proven native polling teacher')

        supported = tuple(backend.get_polling_rates(mouse))
        missing = [rate for rate in args.rates if rate not in supported]
        if missing:
            raise HardwareError(
                f'requested rates are not proven supported: {missing}; supported={supported}'
            )
        if len(args.rates) < 3:
            raise HardwareError('at least three distinct rates are required for grammar inference')

        driver = backend._driver(mouse)
        original_mode = driver.get_control_mode()
        original_rate = driver.get_report_rate()
        trace.clear()

        print('OMUS — Host-State Polling Demonstration')
        print('================================================')
        print(
            f'Device: {mouse.name} '
            f'[{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]'
        )
        print(f'Original control mode: 0x{original_mode:02x}')
        print(f'Original polling rate: {original_rate} Hz')
        print('Teacher: proven native backend')
        print('Generic polling write authority: NONE')
        print(
            'Each capture begins with control already in Host mode. The anchor '
            'rate is established outside the capture window so only the Host-start '
            'transaction needed for a later rate change is recorded.'
        )

        demonstrations = []
        all_events = []
        for index, target in enumerate(args.rates, start=1):
            anchor = _anchor_for_target(target, args.rates, args.anchor)

            # Establish Host mode + a different known rate outside capture.
            backend.set_polling_rate(mouse, anchor)
            if driver.get_control_mode() != HOST_MODE:
                raise HardwareError('teacher failed to establish Host control mode')
            if driver.get_report_rate() != anchor:
                raise HardwareError(
                    f'teacher anchor readback expected {anchor}, got {driver.get_report_rate()}'
                )
            trace.clear()

            backend.set_polling_rate(mouse, target)
            events = trace.snapshot()
            all_events.extend(events)

            # Verify after snapshot so post-check traffic is not training data.
            trace.clear()
            actual_mode = driver.get_control_mode()
            actual_rate = driver.get_report_rate()
            trace.clear()
            if actual_mode != HOST_MODE:
                raise HardwareError(
                    f'host-state demonstration ended in mode 0x{actual_mode:02x}'
                )
            if actual_rate != target:
                raise HardwareError(
                    f'host-state demonstration requested {target}, read {actual_rate}'
                )

            print(f'\n[{index}/{len(args.rates)}] Host {anchor} Hz -> {target} Hz')
            print(_render_trace(events))
            demonstrations.append(
                {
                    'target_hz': int(target),
                    'anchor_hz': int(anchor),
                    'start_control': 'host',
                    'end_control': 'host',
                    'events': [
                        {
                            'direction': event.direction,
                            'length': len(event.data),
                            'data_hex': event.data.hex(),
                            'relative_us': (
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
            'schema_version': 1,
            'profile_kind': 'polling-host-demonstrations',
            'write_authorized': False,
            'prerequisite_control': 'host',
            'resulting_control': 'host',
            'identity': {
                'bus': physical.bus,
                'vendor_id': physical.vendor_id,
                'product_id': physical.product_id,
            },
            'fingerprints': {
                'model': physical.model_fingerprint,
                'instance': physical.instance_fingerprint,
            },
            'interface': {
                'bus': node.bus,
                'vendor_id': node.vendor_id,
                'product_id': node.product_id,
                'interface_number': node.interface_number,
                'descriptor_sha256': node.descriptor_sha256,
            },
            'demonstrations': demonstrations,
        }
        vendor = physical.vendor_id or 0
        product = physical.product_id or 0
        destination = (
            get_profile_directory()
            / 'polling-host-demonstrations'
            / f'{vendor:04x}-{product:04x}-{physical.model_fingerprint[:16]}.json'
        )
        _atomic_json(destination, payload)

        print('\nHost-state polling demonstration capture complete')
        print('-------------------------------------------------')
        print(f'Saved raw corpus: {destination}')
        print('Write authority: false')
        print(
            'Next step: infer the Host-start branch and prove a second generic '
            'rate change after the already-proven Onboard-start takeover.'
        )
        return 0

    except KeyboardInterrupt:
        print('\nHost-state polling trace cancelled.', file=sys.stderr)
        return 130
    except (HardwareError, OSError, PermissionError) as exc:
        print(f'Host-state polling trace failed: {exc}', file=sys.stderr)
        return 1
    finally:
        if backend is not None and mouse is not None:
            try:
                driver = backend._driver(mouse)
                if original_rate is not None:
                    backend.set_polling_rate(mouse, original_rate)
                if original_mode is not None and driver.get_control_mode() != original_mode:
                    driver.set_control_mode(original_mode)
                    restored = driver.get_control_mode()
                    if restored != original_mode:
                        raise HardwareError(
                            f'control-mode restoration read 0x{restored:02x}'
                        )
                if original_rate is not None and original_mode is not None:
                    print(
                        f'\nRestored polling/control state: {original_rate} Hz, '
                        f'mode 0x{original_mode:02x}'
                    )
            except Exception as exc:
                print(f'\nWARNING: polling restoration failed: {exc}', file=sys.stderr)
            backend.close()


if __name__ == '__main__':
    raise SystemExit(main())
