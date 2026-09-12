"""Command-line interface for mouse-control."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
import threading

from .config import DEFAULT_DPI, DEFAULT_DPI_STAGES, generate_config, get_config_path, load_config, save_config
from .discovery import MouseDevice, get_mouse_devices, select_mouse_device
from .hardware import HardwareBackend, HardwareError, get_backend
from .remapper import DpiCycler, MouseRemapper
from .notifications import create_dpi_monitor
from .hidpp_debug import debug_dpi
from .generic_hid import capture_input_reports, discover_hid_devices
from .wizard import ButtonCaptureError, map_mouse_buttons

from .service import (install_service, is_service_active, start_service, stop_service,
                      restart_service, status_service,)
from .permissions import permission_report
from .doctor import doctor_fix, print_doctor


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mouse-control")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="run the interactive setup wizard")
    sub.add_parser("run", help="apply the saved configuration")
    sub.add_parser("show-config", help="print the active configuration path")
    sub.add_parser("check-permissions", help="check mouse and uinput access for this session")
    sub.add_parser("debug-dpi", help="discover Logitech HID++ capabilities and capture reports")
    debug_hid = sub.add_parser(
        "debug-hid", help="read-only generic HID discovery and report capture"
    )
    debug_hid.add_argument(
        "--seconds", type=float, default=10.0,
        help="seconds to capture each matching hidraw interface (default: 10)",
    )
    doctor = sub.add_parser("doctor", help="read-only environment and hardware diagnostics")
    doctor.add_argument("--report", action="store_true", help="format a privacy-safe compatibility report")
    doctor.add_argument("--fix", action="store_true", help="offer safe dependency-installation guidance")

    sub.add_parser("install-service", help="install and enable the systemd user service")
    sub.add_parser("start", help="start the background service")
    sub.add_parser("stop", help="stop the background service")
    sub.add_parser("restart", help="restart the background service")
    sub.add_parser("status", help="show the background service status")

    return parser


def _default_mappings() -> dict[str, str]:
    return {
        "BTN_LEFT": "passthrough",
        "BTN_RIGHT": "passthrough",
        "BTN_MIDDLE": "passthrough",
    }


def debug_hid(seconds: float = 10.0) -> int:
    """Identify matching HID interfaces and capture reports without writes."""
    if seconds <= 0:
        print("--seconds must be greater than zero", file=sys.stderr)
        return 2
    mice = get_mouse_devices()
    if not mice:
        print("No mouse devices found. Check input permissions.", file=sys.stderr)
        return 1
    selected = select_mouse_device(mice)
    if selected is None:
        return 0
    identity = (f"{selected.vendor:04x}:{selected.product:04x}"
                if selected.vendor is not None and selected.product is not None
                else "unavailable")
    print(f"Selected: {selected.name} [{identity}]")
    interfaces = discover_hid_devices(selected)
    if not interfaces:
        print("No matching hidraw interfaces were found.", file=sys.stderr)
        return 1
    print(f"Matching hidraw interfaces: {len(interfaces)}")
    for interface in interfaces:
        print(f"\n{interface.path}: {interface.name}")
        print(f"  physical path: {interface.phys or 'unavailable'}")
        print(f"  report descriptor ({len(interface.report_descriptor)} bytes): "
              f"{interface.report_descriptor.hex(' ')}")
        print(f"  capturing input reports read-only for {seconds:g} seconds; "
              "press the DPI and extra buttons now")
        seen: set[bytes] = set()
        try:
            capture_input_reports(interface, seconds, lambda report: seen.add(report))
        except PermissionError as exc:
            print(f"  permission denied: {exc}", file=sys.stderr)
            continue
        except OSError as exc:
            print(f"  capture unavailable: {exc}", file=sys.stderr)
            continue
        if seen:
            for report in sorted(seen):
                print(f"  input: {report.hex(' ')}")
        else:
            print("  no input reports observed")
    print("\nNo HID feature or output reports were sent.")
    return 0


def _choose_default_dpi(backend: HardwareBackend, device: MouseDevice) -> tuple[list[int], int]:
    """Use the project's preferred DPI stages, adapting only when hardware rejects them."""
    try:
        supported = backend.get_dpi_values(device)
    except HardwareError as exc:
        print(f"{backend.name} DPI query unavailable: {exc}")
        return DEFAULT_DPI_STAGES, DEFAULT_DPI

    print(f"\nDefault DPI stages: {', '.join(map(str, DEFAULT_DPI_STAGES))}")
    if supported:
        print(f"Mouse-reported DPI values: {', '.join(map(str, supported))}")
        unsupported = [value for value in DEFAULT_DPI_STAGES if value not in supported]
        if unsupported:
            print(
                "Note: the mouse does not currently report all preferred stages; "
                "available hardware slots will be used where possible."
            )
    return DEFAULT_DPI_STAGES, DEFAULT_DPI

def _select_max_polling_rate(backend: HardwareBackend, device: MouseDevice) -> int | None:
    """Select the highest reported rate for subsequent application."""
    try:
        supported = backend.get_polling_rates(device)
        current = backend.get_polling_rate(device)
    except HardwareError as exc:
        print(f"{backend.name} polling-rate query unavailable: {exc}")
        return None

    if not supported:
        print(f"No supported polling rates were reported by {backend.name}.")
        return current

    maximum = max(supported)
    print(f"Supported polling rates: {', '.join(str(value) + ' Hz' for value in supported)}")
    print(f"Setting polling rate to maximum: {maximum} Hz")
    return maximum

def _ask_enable_service() -> bool:
    """Ask whether mouse-control should start automatically at login."""
    while True:
        answer = input(
            "\nEnable Mouse Control to run automatically at login? [Y/n]: "
        ).strip().lower()

        if answer in ("", "y", "yes"):
            return True

        if answer in ("n", "no"):
            return False

        print("Please enter Y or N.")


def run_setup_wizard() -> int:
    print("=== Mouse Control Setup Wizard ===")
    # Read-only readiness information: optional backends never block remapping.
    print("Native HID discovery enabled; unsupported mice retain generic remapping.")
    was_active = is_service_active()
    service_restored = False
    if was_active:
        print("Mouse Control background service is running.")
        print("Temporarily stopping it for setup...")
        try:
            stop_service()
        except Exception as exc:
            print(f"Could not stop the background service: {exc}", file=sys.stderr)
            return 1

    try:
        mice = get_mouse_devices()
        if not mice:
            print("No mouse devices found. Check input permissions.")
            return 1

        selected = select_mouse_device(mice)
        if selected is None:
            print("Setup cancelled.")
            return 0

        print(f"\nSelected: {selected.name}")
        backend = get_backend(selected)
        try:
            hardware_name = backend.get_device_name(selected)
            if hardware_name and hardware_name != selected.name:
                identity = (f" [{selected.vendor:04x}:{selected.product:04x}]"
                            if selected.vendor is not None and selected.product is not None else "")
                print(f"Hardware name: {hardware_name}{identity}")
        except HardwareError as exc:
            logging.info("Hardware name lookup unavailable: %s", exc)
        mappings = _default_mappings()
        mappings.update(map_mouse_buttons(selected.path))
        dpi_stages = DEFAULT_DPI_STAGES
        active_dpi = DEFAULT_DPI
        polling_rate_hz: int | None = None
        try:
            if backend.supports_dpi(selected):
                dpi_stages, active_dpi = _choose_default_dpi(backend, selected)
        except HardwareError as exc:
            logging.warning("DPI capability query failed: %s", exc)
        try:
            if backend.supports_polling_rate(selected):
                polling_rate_hz = _select_max_polling_rate(backend, selected)
        except HardwareError as exc:
            logging.warning("Polling capability query failed: %s", exc)

        enable_service = _ask_enable_service()
        content = generate_config(
            selected, mappings, dpi_stages=dpi_stages, active_dpi=active_dpi,
            polling_rate_hz=polling_rate_hz,
        )
        _apply_hardware(
            backend, selected, dpi_stages, active_dpi, polling_rate_hz, setup=True
        )
        path = save_config(content)
        print(f"\nConfiguration saved to: {path}")

        if enable_service:
            try:
                install_service()
                service_restored = True
                print("Mouse Control background service enabled and started.")
            except Exception as exc:
                print(f"Warning: could not enable background service: {exc}")
                print("Your mouse configuration was still saved successfully.")
        else:
            print(
                "Background service not enabled. "
                "You can enable it later with: mouse-control install-service"
            )
        return 0
    except ButtonCaptureError:
        print("Setup failed; the existing configuration was not changed.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSetup cancelled; the existing configuration was not changed.")
        return 1
    except Exception as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        print("The existing configuration was not changed.", file=sys.stderr)
        return 1
    finally:
        if was_active and not service_restored:
            try:
                restart_service()
            except Exception as exc:
                print(f"Warning: could not restart the background service: {exc}",
                      file=sys.stderr)


def _apply_hardware(backend: HardwareBackend, device: MouseDevice,
                    stages: list[int], active_dpi: int, polling_rate_hz: int | None,
                    *, setup: bool = False) -> None:
    """Apply independent capabilities; a hardware failure never blocks remapping."""
    try:
        if active_dpi > 0 and backend.supports_dpi(device):
            if backend.supports_dpi_stages(device):
                slot = backend.apply_dpi_stages(device, stages, active_dpi)
                if slot is not None:
                    print(f"Hardware DPI stages applied; {active_dpi} DPI is active/default "
                          f"through {backend.name} (resolution {slot}).")
                elif setup:
                    print("Warning: the mouse did not expose a resolution slot for the requested active DPI.")
                else:
                    backend.set_dpi(device, active_dpi)
            else:
                backend.set_dpi(device, active_dpi)
    except HardwareError as exc:
        logging.warning("Could not apply %s DPI settings: %s", backend.name, exc)

    try:
        if polling_rate_hz is not None and backend.supports_polling_rate_writes(device):
            backend.set_polling_rate(device, int(polling_rate_hz))
            print(f"Hardware polling rate set to {polling_rate_hz} Hz through {backend.name}.")
    except (HardwareError, ValueError, TypeError) as exc:
        logging.warning("Could not apply %s polling settings: %s", backend.name, exc)


def run_from_config(path: Path | None = None) -> int:
    config = load_config(path)
    device = config.get("device", {})
    mappings = config.get("remap", {})
    event_path = device.get("event_path")
    if not event_path:
        print("Configuration is missing [device].event_path", file=sys.stderr)
        return 1

    dpi_config = config.get("dpi", {})
    try:
        dpi_stages = [int(value) for value in dpi_config.get("stages", DEFAULT_DPI_STAGES)]
        active_dpi = int(dpi_config.get("active", DEFAULT_DPI))
        if active_dpi <= 0:
            raise ValueError("Active DPI must be greater than zero")
    except (ValueError, TypeError) as exc:
        logging.warning("Invalid DPI configuration; skipping DPI settings: %s", exc)
        dpi_stages, active_dpi = [], 0
    polling_rate_hz = config.get("polling", {}).get("rate_hz")

    mouse = next((m for m in get_mouse_devices()
                  if os.path.realpath(m.path) == os.path.realpath(event_path)), None)
    monitor = None
    dpi_cycler = None
    shutdown_event = threading.Event()
    if mouse is not None:
        backend = get_backend(mouse)
        _apply_hardware(backend, mouse, dpi_stages, active_dpi, polling_rate_hz)
        enabled = config.get("notifications", {}).get("dpi_changes", True)
        if isinstance(enabled, bool):
            notifications_enabled = enabled
        else:
            logging.warning("Invalid notifications.dpi_changes; using enabled default")
            notifications_enabled = True
        if "dpi-cycle" in mappings.values():
            dpi_cycler = DpiCycler(backend, mouse, dpi_stages, active_dpi,
                                   notifications_enabled)
        else:
            monitor = create_dpi_monitor(backend, mouse, notifications_enabled,
                                         shutdown_event, dpi_stages, active_dpi)

    if monitor is not None:
        monitor.start()
    try:
        MouseRemapper(event_path, mappings, shutdown_event, dpi_cycler).run()
    finally:
        if monitor is not None:
            monitor.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    args = _build_parser().parse_args(argv)

    if args.command == "setup":
        return run_setup_wizard()

    if args.command == "run":
        return run_from_config()

    if args.command == "show-config":
        print(get_config_path())
        return 0

    if args.command == "check-permissions":
        return permission_report()

    if args.command == "debug-dpi":
        return debug_dpi()

    if args.command == "debug-hid":
        return debug_hid(args.seconds)

    if args.command == "doctor":
        if args.fix:
            return doctor_fix()
        return print_doctor(report=args.report)

    if args.command == "install-service":
        install_service()
        return 0

    if args.command == "start":
        start_service()
        return 0

    if args.command == "stop":
        stop_service()
        return 0

    if args.command == "restart":
        restart_service()
        return 0

    if args.command == "status":
        return status_service()

    _build_parser().print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
