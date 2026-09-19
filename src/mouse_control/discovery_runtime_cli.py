"""Acceptance monitor for the Discovery-backed runtime path.

This deliberately bypasses native vendor backends so a known mouse can prove
that persisted calibrated evidence is sufficient for live DPI monitoring.
"""

from __future__ import annotations

import argparse
import sys
import threading

from .discovery import get_mouse_devices, select_mouse_device
from .cli import _resolve_runtime_device
from .hardware import HardwareSupervisor
from .hardware.discovery_backend import DiscoveryBackend
from .notifications import DpiMonitorSupervisor, FreedesktopNotifier


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-discovery-monitor",
        description="Monitor DPI using only the persisted Automatic Discovery read-side profile.",
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument(
        "--set-dpi",
        type=int,
        metavar="DPI",
        help=(
            "execute one PROVEN learned DPI write with vendor/native adapters "
            "bypassed, then read it back and exit"
        ),
    )
    return parser


def _pick(index: int | None):
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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    device, status = _pick(args.device)
    if device is None:
        return status

    # DiscoveryBackend defaults to no protocol factories here: this is the
    # teacher-free acceptance path for persisted calibrated/learned evidence.
    backend = DiscoveryBackend(allow_writes=args.set_dpi is not None)
    backend.supports_device(device)

    if args.set_dpi is not None:
        print("OMUS — Teacher-Free Learned Write Acceptance")
        print("=====================================================")
        print(f"Device: {backend.get_device_name(device)}")
        print("Vendor/native backend: BYPASSED")
        print("Execution path: PROVEN learned operation -> TransactionEngine -> raw HID")
        if not backend.supports_dpi(device):
            print(
                "Automatic Discovery has no PROVEN learned writable DPI operation.",
                file=sys.stderr,
            )
            backend.close()
            return 1
        try:
            state = backend.set_dpi(device, args.set_dpi)
            readback = backend.get_dpi_state(device)
        except Exception as exc:
            print(f"Teacher-free learned write failed: {exc}", file=sys.stderr)
            backend.close()
            return 1
        print(f"Requested DPI: {args.set_dpi}")
        print(f"Write readback: {state.display_value if state else 'unavailable'}")
        print(
            f"Independent learned read query: "
            f"{readback.display_value if readback else 'unavailable'}"
        )
        backend.close()
        return 0

    if not backend.supports_dpi_events(device):
        print(
            "Automatic Discovery has no persisted calibrated DPI mapping for this device.",
            file=sys.stderr,
        )
        return 1

    values = backend.get_dpi_values(device)
    print("OMUS — Automatic Discovery Runtime Monitor")
    print("===================================================")
    print(f"Device: {backend.get_device_name(device)}")
    print("Vendor/native backend: BYPASSED")
    print("Unknown HID writes: FORBIDDEN")
    print("Learned DPI values: " + ", ".join(str(value) for value in values))
    print("Press the physical DPI button. Ctrl+C exits.")

    desktop_notifier = FreedesktopNotifier()
    shutdown = threading.Event()

    class AcceptanceNotifier:
        def start(self):
            desktop_notifier.start()

        def notify_dpi(self, dpi):
            print(f"learned DPI event -> {dpi} DPI")
            desktop_notifier.notify_dpi(dpi)

        def close(self):
            desktop_notifier.close()

    def backend_factory(selected):
        replacement = DiscoveryBackend(allow_writes=False)
        replacement.supports_device(selected)
        return replacement

    hardware = HardwareSupervisor(
        backend,
        device,
        backend_factory,
        device_resolver=_resolve_runtime_device,
        discovery_pending=True,
    )
    monitor = DpiMonitorSupervisor(
        hardware,
        device,
        lambda _device: hardware,
        values,
        0,
        shutdown,
        notifier=AcceptanceNotifier(),
    )

    try:
        monitor._run()
    except KeyboardInterrupt:
        shutdown.set()
        print("\nDiscovery runtime monitor stopped.")
    except Exception as exc:
        print(f"Discovery runtime monitor failed: {exc}", file=sys.stderr)
        return 1
    finally:
        monitor.stop()
        hardware.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
