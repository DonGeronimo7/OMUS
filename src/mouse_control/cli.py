"""Command-line interface for mouse-control."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading

from .config import (DEFAULT_DPI, DEFAULT_DPI_STAGES, get_config_path,
                     load_config, merge_setup_config, save_config)
from .discovery import MouseDevice, get_mouse_devices, select_mouse_device
from .hardware import (DesiredHardwareState, HardwareBackend, HardwareError,
                       HardwareSupervisor, get_backend)
from .hardware.discovery_backend import DiscoveryBackend
from .remapper import DpiCycler, MouseRemapper
from .notifications import DpiMonitorSupervisor
from .battery import BatteryMonitorSupervisor
from .hidpp_debug import debug_dpi
from .generic_hid import capture_input_reports, discover_hid_devices
from .setup_flow import SetupChoices

from .service import (install_service, is_service_active, start_service, stop_service,
                      restart_service, status_service, ServiceNotInstalled)
from .permissions import permission_report
from .doctor import doctor_fix, print_doctor
from . import __version__
from .branding import print_banner, style
from .updater import run_update


LOG = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mouse-control")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="run the interactive setup wizard")
    run_parser = sub.add_parser("run", help="apply the saved configuration")
    run_parser.add_argument("--config", type=Path,
                            help="use an explicit configuration file instead of the default")
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
    research = sub.add_parser("research", help="read-only HID semantic research tools")
    research_sub = research.add_subparsers(dest="research_command")
    capture = research_sub.add_parser("hid-capture", help="capture one sanitized, labelled HID corpus experiment")
    capture.add_argument("destination", type=Path, help="new or existing corpus-device directory")
    capture.add_argument("--mode", required=True, choices=("descriptor-only", "idle", "pointer-movement", "left-click", "right-click", "middle-click", "wheel", "side-buttons", "dpi-button", "guided-action"))
    capture.add_argument("--seconds", type=float, default=10.0)
    explain = research_sub.add_parser("hid-explain", help="render descriptor-derived semantic inventory from a corpus")
    explain.add_argument("corpus", type=Path)
    explain.add_argument("--negative-control", action="append", type=Path, default=[],
                         help="same-device labelled corpus to use as a clean negative control")
    explain.add_argument("--calibrated-profile", type=Path,
                         help="read-only physical CPI profile used to validate an exact member")
    explain.add_argument("--persist-validated-binding", action="store_true",
                         help="persist one clean physically validated descriptor member")
    doctor = sub.add_parser("doctor", help="read-only environment and hardware diagnostics")
    doctor.add_argument("--report", action="store_true", help="format a privacy-safe compatibility report")
    doctor.add_argument("--fix", action="store_true", help="offer safe dependency-installation guidance")
    support = sub.add_parser("support", help="create a privacy-safe hardware support report")
    support.add_argument("--guided", action="store_true", help="also capture one optional button press")
    discover = sub.add_parser("discover", help="generate a structured read-only discovery report")
    discover.add_argument("--device", type=int, metavar="N")
    discover.add_argument("--output", type=Path, required=True, metavar="FILE")
    discover.add_argument("--generic-only", action="store_true")

    sub.add_parser("install-service", help="install and enable the systemd user service")
    sub.add_parser("start", help="start the background service")
    sub.add_parser("stop", help="stop the background service")
    sub.add_parser("restart", help="restart the background service")
    sub.add_parser("status", help="show the background service status")
    update = sub.add_parser("update", help="check for and safely install an update")
    update.add_argument("--check", action="store_true", help="only check whether an update is available")
    update.add_argument("--yes", action="store_true", help="do not ask before updating")

    return parser


def _default_mappings() -> dict[str, str]:
    return {
        "BTN_LEFT": "passthrough",
        "BTN_RIGHT": "passthrough",
        "BTN_MIDDLE": "passthrough",
    }


def _load_setup_config() -> dict[str, object]:
    """Load an existing configuration once; absence means first-run defaults."""
    path = get_config_path()
    if not path.exists():
        return {}
    existing = load_config(path)
    if not isinstance(existing, dict):
        raise ValueError("Existing configuration is invalid")
    return existing


def _initial_mappings(existing: dict[str, object]) -> dict[str, str]:
    """Keep an existing remap table intact until the wizard edits a button."""
    if "remap" not in existing:
        return _default_mappings()
    mappings = existing["remap"]
    if not isinstance(mappings, dict) or not all(
            isinstance(button, str) and isinstance(action, str)
            for button, action in mappings.items()):
        raise ValueError("Existing [remap] configuration is invalid")
    return dict(mappings)


def _initial_choices(existing: dict[str, object]) -> SetupChoices:
    dpi = existing.get("dpi", {})
    polling = existing.get("polling", {})
    if not isinstance(dpi, dict) or not isinstance(polling, dict):
        raise ValueError("Existing DPI or polling configuration is invalid")
    stages = dpi.get("stages", DEFAULT_DPI_STAGES)
    active = dpi.get("active", DEFAULT_DPI)
    if (not isinstance(stages, list) or
            any(not isinstance(value, int) or value <= 0 for value in stages) or
            not isinstance(active, int) or active <= 0):
        raise ValueError("Existing DPI configuration is invalid")
    rate = polling.get("rate_hz")
    if rate is not None and (not isinstance(rate, int) or rate <= 0):
        raise ValueError("Existing polling configuration is invalid")
    return SetupChoices(stages=list(stages), active_dpi=active, polling_rate=rate,
                        mappings=_initial_mappings(existing))


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


def run_support(*, guided: bool = False) -> int:
    """Create an explicitly requested local report without hardware writes."""
    from .support import capture_button, probe, render_report

    print_banner()
    print(style("Mouse Control Hardware Support", "purple") + "\n" + "─" * 31)
    mice = get_mouse_devices()
    if not mice:
        print("No mouse devices were detected. Check that your mouse is connected and try again.")
        return 1
    print("\nSelect the mouse you're having trouble with:")
    for index, mouse in enumerate(mice, 1):
        print(f"  {index}. {mouse.name}")
    try:
        selected = mice[int(input("\n> ").strip()) - 1]
    except (ValueError, IndexError, EOFError, KeyboardInterrupt):
        print("\nSupport report cancelled.")
        return 0
    print(f"\nChecking {selected.name}...")
    report = probe(selected, get_backend(selected))
    if guided:
        print("\nOptional button test: press the BACK or FORWARD button now (10 seconds)...")
        event = capture_button(selected)
        report["guided"]["Requested action"] = "Press a side button"
        report["guided"]["Detected event"] = event or "No event detected"
    try:
        answer = input("Create support report? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    if answer not in ("", "y", "yes"):
        print("Support report cancelled.")
        return 0
    slug = "".join(char.lower() if char.isalnum() else "-" for char in selected.name).strip("-") or "mouse"
    destination = Path.home() / f"mouse-control-{slug}-report.txt"
    try:
        destination.write_text(render_report(report), encoding="utf-8")
    except OSError as exc:
        print(f"Could not save support report: {exc}", file=sys.stderr)
        return 1
    print(f"Report saved: {destination}\nPlease attach this report to a GitHub issue.")
    return 0


def run_setup_wizard() -> int:
    """Run the sole supported interactive setup UI.

    Redirected and programmatic CLI execution is intentionally rejected before
    importing curses. Such callers should use configuration/runtime APIs rather
    than attempting to drive an interactive setup session.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "Mouse Control setup requires an interactive terminal. "
            "No legacy prompt fallback is available.",
            file=sys.stderr,
        )
        return 2

    from .setup_entry import run_tui_setup_wizard

    return run_tui_setup_wizard()


def _apply_hardware(backend: HardwareBackend, device: MouseDevice,
                    stages: list[int], active_dpi: int, polling_rate_hz: int | None,
                    *, setup: bool = False) -> None:
    """Apply independent capabilities; a hardware failure never blocks remapping."""
    try:
        if active_dpi > 0 and backend.supports_dpi(device):
            applied_directly = False
            if backend.supports_dpi_stages(device):
                slot = backend.apply_dpi_stages(device, stages, active_dpi)
                if slot is not None:
                    print(f"Hardware DPI stages applied; {active_dpi} DPI is active/default "
                          f"through {backend.name} (resolution {slot}).")
                elif setup:
                    print("Warning: the mouse did not expose a resolution slot for the requested active DPI.")
                else:
                    backend.set_dpi(device, active_dpi)
                    applied_directly = True
            else:
                backend.set_dpi(device, active_dpi)
                applied_directly = True
            if applied_directly:
                actual = backend.get_dpi(device)
                matches = (actual == active_dpi or
                           isinstance(actual, tuple) and actual[0] == active_dpi and
                           actual[1] in (0, active_dpi))
                if actual is None:
                    print(f"Hardware DPI requested at {active_dpi} through {backend.name}; "
                          "readback is unavailable.")
                elif matches:
                    print(f"Hardware DPI set and verified at {active_dpi} through {backend.name}.")
                else:
                    raise HardwareError(
                        f"DPI verification requested {active_dpi}, read {actual}")
        elif setup and active_dpi > 0:
            print(f"DPI control is unsupported by {backend.name}; hardware DPI was unchanged.")
    except HardwareError as exc:
        logging.warning("Could not apply %s DPI settings: %s", backend.name, exc)

    try:
        if polling_rate_hz is not None and backend.supports_polling_rate_writes(device):
            backend.set_polling_rate(device, int(polling_rate_hz))
            actual = backend.get_polling_rate(device)
            if actual is None:
                print(f"Hardware polling rate requested at {polling_rate_hz} Hz through "
                      f"{backend.name}; readback is unavailable.")
            elif actual == int(polling_rate_hz):
                print(f"Hardware polling rate set and verified at {actual} Hz through {backend.name}.")
            else:
                raise HardwareError(
                    f"polling verification requested {polling_rate_hz} Hz, read {actual} Hz")
        elif setup and polling_rate_hz is not None:
            print(f"Polling-rate writes are unsupported by {backend.name}; hardware was unchanged.")
    except (HardwareError, ValueError, TypeError) as exc:
        logging.warning("Could not apply %s polling settings: %s", backend.name, exc)


def _resolve_runtime_device(configured: MouseDevice) -> MouseDevice:
    """Resolve reconnect identity without guessing among matching devices."""
    mice = get_mouse_devices()
    by_path = [mouse for mouse in mice
               if os.path.realpath(mouse.path) == os.path.realpath(configured.path) and
               (configured.vendor is None or mouse.vendor == configured.vendor) and
               (configured.product is None or mouse.product == configured.product) and
               (configured.bustype is None or mouse.bustype == configured.bustype)]
    if len(by_path) == 1:
        return by_path[0]
    if configured.vendor is None or configured.product is None:
        return configured
    candidates = [mouse for mouse in mice
                  if mouse.vendor == configured.vendor and
                  mouse.product == configured.product and
                  (configured.bustype is None or mouse.bustype == configured.bustype)]
    if configured.phys:
        physical = [mouse for mouse in candidates if mouse.phys == configured.phys]
        if len(physical) == 1:
            return physical[0]
    return candidates[0] if len(candidates) == 1 else configured


def run_from_config(path: Path | None = None) -> int:
    try:
        config = load_config(path)
    except OSError as exc:
        print(f"Could not read configuration: {exc}", file=sys.stderr)
        return 1
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
    configured_mouse = MouseDevice(
        str(device.get("name", "")), event_path,
        phys=str(device.get("phys", "") or ""),
        vendor=device.get("vendor") if isinstance(device.get("vendor"), int) else None,
        product=device.get("product") if isinstance(device.get("product"), int) else None,
        bustype=device.get("bustype") if isinstance(device.get("bustype"), int) else None,
    )
    monitor = None
    dpi_cycler = None
    shutdown_event = threading.Event()
    enabled = config.get("notifications", {}).get("dpi_changes", True)
    if isinstance(enabled, bool):
        notifications_enabled = enabled
    else:
        logging.warning("Invalid notifications.dpi_changes; using enabled default")
        notifications_enabled = True
    cycle_device = mouse or configured_mouse
    g305_hidpp = (cycle_device.vendor == 0x046d and cycle_device.product == 0x4074 and
                   cycle_device.bustype in (None, 3))
    hardware_device = mouse or configured_mouse
    initial_backend = get_backend(hardware_device, log_failures=mouse is not None)
    discovery_pending = (
        mouse is None or
        (isinstance(initial_backend, DiscoveryBackend) and
         initial_backend.protocol_adapter_name is None)
    )
    hardware = HardwareSupervisor(
        initial_backend, hardware_device,
        lambda selected: get_backend(selected, log_failures=False),
        DesiredHardwareState(active_dpi=active_dpi,
                             dpi_stages=tuple(dpi_stages),
                             polling_rate_hz=polling_rate_hz),
        device_resolver=_resolve_runtime_device,
        discovery_pending=discovery_pending)
    if mouse is not None:
        identity = (f"{mouse.vendor:04x}:{mouse.product:04x}"
                    if mouse.vendor is not None and mouse.product is not None
                    else "identity unavailable")
        LOG.info("Selected mouse: %s (%s, %s)", mouse.name, mouse.path, identity)
        LOG.info("Selected hardware backend: %s (%s)", initial_backend.name,
                 type(initial_backend).__name__)
    hardware.reconcile()
    try:
        learned_cycle_trigger = (
            hardware.supports_dpi_cycle_trigger(hardware_device) is True
        )
    except HardwareError as exc:
        LOG.warning("Learned DPI-cycle trigger unavailable: %s", exc)
        learned_cycle_trigger = False
    if "dpi-cycle" in mappings.values() or g305_hidpp or learned_cycle_trigger:
        dpi_cycler = DpiCycler(hardware, hardware_device, dpi_stages, active_dpi,
                               notifications_enabled)

    if notifications_enabled or g305_hidpp or learned_cycle_trigger:
        monitor_kwargs = ({"dpi_cycler": dpi_cycler,
                           "notifications_enabled": notifications_enabled}
                          if (g305_hidpp or learned_cycle_trigger) else {})
        monitor = DpiMonitorSupervisor(hardware, hardware_device,
                                       lambda _device: hardware,
                                       dpi_stages, active_dpi, shutdown_event, **monitor_kwargs)
        if dpi_cycler is not None:
            dpi_cycler.notifier = monitor
        LOG.info("DPI notification monitor: %s", type(monitor).__name__)
    else:
        LOG.info("DPI notification monitor: disabled")

    battery_monitor = BatteryMonitorSupervisor(
        hardware, hardware_device, lambda _selected: hardware, shutdown_event)

    if monitor is not None:
        LOG.info("Starting DPI notification monitor")
        monitor.start()
    battery_monitor.start()
    try:
        MouseRemapper(event_path, mappings, shutdown_event, dpi_cycler,
                      target_device=mouse or configured_mouse,
                      event_observer=hardware).run()
    finally:
        if monitor is not None:
            monitor.stop()
        battery_monitor.stop()
        hardware.close()
    return 0


def _run_service_action(action: str) -> int:
    actions = {
        "1": ("Status", status_service),
        "2": ("Start", start_service),
        "3": ("Restart", restart_service),
        "4": ("Stop", stop_service),
        "5": ("Install and enable", install_service),
    }
    label, operation = actions[action]
    try:
        result = operation()
        return int(result) if isinstance(result, int) else 0
    except (ServiceNotInstalled, OSError, subprocess.CalledProcessError) as exc:
        print(f"Service {label.lower()} unavailable: {exc}", file=sys.stderr)
        return 1


def _service_menu(input_func=input) -> int:
    print("\nService controls")
    print("  1. Service status")
    print("  2. Start service")
    print("  3. Restart service")
    print("  4. Stop service")
    print("  5. Install and enable service")
    print("  B. Back")
    try:
        choice = input_func("Service action: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    if choice in {"b", "", "q"}:
        return 0
    if choice in {"1", "2", "3", "4", "5"}:
        return _run_service_action(choice)
    print("Please choose a numbered service action or B to go back.")
    return 0


def run_home_screen(*, input_func=input, columns: int | None = None) -> int:
    """Present a lightweight, keyboard-first terminal home screen."""
    print_banner(columns=columns)
    try:
        active = is_service_active()
    except (OSError, subprocess.CalledProcessError):
        active = None
    status = "Running" if active else "Not running" if active is False else "Unknown"
    status_style = "success" if active else "muted" if active is False else "warning"
    print(f"\nService: {style(status, status_style)}")
    print("\n  1. Configure mouse")
    print("  2. Button remapping")
    print("  3. DPI & polling")
    print("  4. Hardware support")
    print("  5. Service controls")
    print("  6. Diagnostics")
    print("  7. Help / About")
    print("  Q. Quit")

    routes = {
        "1": run_setup_wizard,
        "2": run_setup_wizard,
        "3": run_setup_wizard,
        "4": run_support,
        "6": print_doctor,
    }
    while True:
        try:
            choice = input_func("\nChoose an option: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0
        if choice in {"q", "quit"}:
            print("Goodbye.")
            return 0
        if choice == "5":
            _service_menu(input_func)
            return 0
        if choice == "7":
            _build_parser().print_help()
            return 0
        route = routes.get(choice)
        if route is not None:
            return int(route() or 0)
        print("Please choose 1–7 or Q to quit.")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    supplied_argv = sys.argv[1:] if argv is None else argv
    if not supplied_argv:
        if sys.stdin.isatty() and sys.stdout.isatty():
            return run_setup_wizard()
        _build_parser().print_help()
        return 0

    args = _build_parser().parse_args(supplied_argv)

    if args.command == "setup":
        return run_setup_wizard()

    if args.command == "run":
        return run_from_config(args.config)

    if args.command == "show-config":
        print(get_config_path())
        return 0

    if args.command == "check-permissions":
        return permission_report()

    if args.command == "debug-dpi":
        return debug_dpi()

    if args.command == "debug-hid":
        return debug_hid(args.seconds)

    if args.command == "research":
        from .hid_capture_cli import capture_hid_corpus, explain_hid_corpus
        if args.research_command == "hid-capture":
            return capture_hid_corpus(args.destination, args.mode, args.seconds)
        if args.research_command == "hid-explain":
            return explain_hid_corpus(
                args.corpus, tuple(args.negative_control), args.calibrated_profile,
                args.persist_validated_binding)

    if args.command == "doctor":
        if args.fix:
            return doctor_fix()
        return print_doctor(report=args.report)

    if args.command == "support":
        return run_support(guided=args.guided)

    if args.command == "discover":
        from .discovery_cli import main as discovery_main
        command = ["--community-report", os.fspath(args.output)]
        if args.device is not None:
            command.extend(("--device", str(args.device)))
        if args.generic_only:
            command.append("--generic-only")
        return discovery_main(command)

    if args.command == "update":
        return run_update(check=args.check, assume_yes=args.yes)

    try:
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
    except ServiceNotInstalled as exc:
        print(exc, file=sys.stderr)
        return 1

    _build_parser().print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
