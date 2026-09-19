"""Read-only, privacy-conscious diagnostics for hardware reports."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Callable

from . import __version__
from .discovery import MouseDevice, get_mouse_devices
from .permissions import UINPUT_PATH
from .service import is_service_active, service_path


def distribution() -> str:
    """Return only the public OS identity, with a portable fallback."""
    try:
        values = {}
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"')
        return values.get("PRETTY_NAME") or values.get("NAME") or "Unknown Linux distribution"
    except OSError:
        return "Unknown Linux distribution"


def package_manager() -> str | None:
    return next((name for name in ("dnf", "apt", "pacman") if shutil.which(name)), None)


def _status(label: str, state: str, detail: str = "") -> str:
    return f"{state:<8} {label}" + (f": {detail}" if detail else "")


def _command_ok(command: list[str]) -> bool:
    try:
        return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              check=False).returncode == 0
    except OSError:
        return False


def _mouse_lines(mice: list[MouseDevice]) -> list[str]:
    lines: list[str] = []
    for mouse in mice:
        identity = (f"{mouse.vendor:04x}:{mouse.product:04x}"
                    if mouse.vendor is not None and mouse.product is not None else "unknown")
        lines.append(f"- {mouse.name} (VID:PID {identity})")
        lines.append("  hardware backend: not probed (doctor is read-only)")
    return lines


def doctor_lines(mice: list[MouseDevice] | None = None) -> list[str]:
    """Collect diagnostics without opening hidraw or issuing hardware requests."""
    mice = get_mouse_devices() if mice is None else mice
    evdev = importlib.util.find_spec("evdev") is not None
    dbus = importlib.util.find_spec("dbus_next") is not None
    systemd = shutil.which("systemctl") is not None
    udev = shutil.which("udevadm") is not None or Path("/run/udev").exists()
    input_ok = bool(mice) and UINPUT_PATH.exists() and os.access(UINPUT_PATH, os.R_OK | os.W_OK)
    service_installed = service_path().is_file()
    service_running = is_service_active() if service_installed and systemd else False
    rule_paths = (Path("/usr/lib/udev/rules.d/71-mouse-control-uaccess.rules"),
                  Path("/etc/udev/rules.d/71-mouse-control-uaccess.rules"))

    lines = [
        "OMUS diagnostic (read-only)",
        _status("OMUS", "PASS", __version__),
        _status("Linux", "PASS", f"{distribution()} / {platform.release()}"),
        _status("Architecture", "PASS", platform.machine()),
        _status("Python", "PASS", platform.python_version()),
        _status("evdev", "PASS" if evdev else "MISSING"),
        _status("dbus-next", "PASS" if dbus else "MISSING"),
        _status("systemd user services", "PASS" if systemd else "WARNING", "available" if systemd else "unavailable"),
        _status("udev", "PASS" if udev else "WARNING", "available" if udev else "unavailable"),
        _status("input permissions", "PASS" if input_ok else "WARNING",
                "usable" if input_ok else "no readable mouse and writable /dev/uinput combination"),
        _status("Native HID", "PASS", "protocol drivers enabled"),
        _status("Native Razer", "PASS", "exact-model protocol driver enabled"),
        _status("OMUS user service", "PASS" if service_running else ("WARNING" if service_installed else "MISSING"),
                "running" if service_running else ("stopped" if service_installed else "not installed")),
        _status("OMUS udev rule", "PASS" if any(path.is_file() for path in rule_paths) else "MISSING"),
        "Detected mouse devices:",
    ]
    lines.extend(_mouse_lines(mice) or ["- none safely readable"])
    return lines


def print_doctor(*, report: bool = False, mice: list[MouseDevice] | None = None) -> int:
    title = "OMUS hardware compatibility report" if report else None
    if title:
        print(title)
        print("=" * len(title))
    print("\n".join(doctor_lines(mice)))
    if report:
        print("\nPrivacy: this report excludes usernames, paths, serial numbers, cache contents, and unrelated USB devices.")
    return 0


def doctor_fix(confirm: Callable[[str], str] = input) -> int:
    """Offer a command only; never performs privileged mutation itself."""
    manager = package_manager()
    if manager is None:
        print("WARNING  No supported package manager detected; no changes made.")
        return 0
    commands = {
        "dnf": "sudo dnf install python3-evdev python3-dbus-next",
        "apt": "sudo apt install python3-evdev python3-dbus-next",
        "pacman": "sudo pacman -S python-evdev python-dbus-next",
    }
    command = commands[manager]
    print("These packages provide remapping and desktop notifications.")
    print(f"Proposed command ({manager}): {command}")
    answer = confirm("Run this command yourself? [y/N]: ").strip().lower()
    if answer not in ("y", "yes"):
        print("No changes made.")
        return 0
    print("For safety, OMUS does not run privileged package commands. Copy and run the proposed command yourself.")
    return 0
