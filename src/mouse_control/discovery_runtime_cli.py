"""Acceptance monitor for the Discovery-backed runtime path.

This deliberately bypasses native vendor backends so a known mouse can prove
that persisted calibrated evidence is sufficient for live DPI monitoring.
"""

from __future__ import annotations

import argparse
import sys
import threading

from .discovery import get_mouse_devices, select_mouse_device
from .hardware.discovery_backend import DiscoveryBackend
from .notifications import FreedesktopNotifier


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-discovery-monitor",
        description="Monitor DPI using only the persisted Automatic Discovery read-side profile.",
    )
    parser.add_argument("--device", type=int, metavar="N")
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

    backend = DiscoveryBackend()
    backend.supports_device(device)
    if not backend.supports_dpi_events(device):
        print(
            "Automatic Discovery has no persisted calibrated DPI mapping for this device.",
            file=sys.stderr,
        )
        return 1

    values = backend.get_dpi_values(device)
    print("Mouse Control — Automatic Discovery Runtime Monitor")
    print("===================================================")
    print(f"Device: {backend.get_device_name(device)}")
    print("Vendor/native backend: BYPASSED")
    print("Unknown HID writes: FORBIDDEN")
    print("Learned DPI values: " + ", ".join(str(value) for value in values))
    print("Press the physical DPI button. Ctrl+C exits.")

    notifier = FreedesktopNotifier()
    shutdown = threading.Event()

    def on_state(state):
        dpi = state.display_value
        print(f"learned DPI event -> {dpi} DPI")
        notifier.notify_dpi(dpi)

    try:
        backend.watch_dpi_events(device, on_state, shutdown)
    except KeyboardInterrupt:
        shutdown.set()
        print("\nDiscovery runtime monitor stopped.")
    except Exception as exc:
        print(f"Discovery runtime monitor failed: {exc}", file=sys.stderr)
        return 1
    finally:
        notifier.close()
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
