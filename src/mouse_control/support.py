# SPDX-License-Identifier: AGPL-3.0-or-later
"""On-demand, privacy-safe hardware support reports."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import select
from typing import Any

from evdev import InputDevice, ecodes

from . import __version__
from .discovery import MouseDevice
from .hardware import HardwareBackend, HardwareError


def _read(path: Path, limit: int = 4096) -> str | None:
    try:
        return path.read_text(errors="replace")[:limit].strip()
    except (OSError, UnicodeError):
        return None


def _system() -> str:
    data = _read(Path("/etc/os-release")) or ""
    values = dict(line.split("=", 1) for line in data.splitlines() if "=" in line)
    return values.get("PRETTY_NAME", values.get("NAME", "Unknown")).strip('"')


def _sysfs(device: MouseDevice) -> tuple[dict[str, str], list[str], list[str]]:
    """Return selected-device identity, hidraw names, and drivers only."""
    start = Path("/sys/class/input") / Path(device.path).resolve().name / "device"
    fields: dict[str, str] = {}
    hidraw: list[str] = []
    drivers: list[str] = []
    for parent in [start, *start.parents][:8]:
        vendor, product = _read(parent / "idVendor"), _read(parent / "idProduct")
        if vendor and product:
            fields["USB VID:PID"] = f"{vendor.lower()}:{product.lower()}"
            fields["Manufacturer"] = _read(parent / "manufacturer") or "Unknown"
            fields["Product"] = _read(parent / "product") or device.name
        try:
            driver = (parent / "driver").resolve().name if (parent / "driver").exists() else None
            if driver and driver not in drivers:
                drivers.append(driver)
            for node in parent.glob("hidraw/hidraw*"):
                if node.name not in hidraw:
                    hidraw.append(node.name)
        except OSError:
            pass
    return fields, hidraw, drivers


def _capabilities(device: MouseDevice) -> tuple[dict[str, str], list[str]]:
    result: dict[str, str] = {}
    errors: list[str] = []
    try:
        with InputDevice(device.path) as input_device:
            caps = input_device.capabilities(verbose=False)
        names = [ecodes.KEY.get(code, f"KEY_{code}") for code in caps.get(ecodes.EV_KEY, [])]
        buttons = sorted(name for name in names if name.startswith("BTN_"))
        result["Buttons"] = ", ".join(buttons) if buttons else "Unknown"
        result["Relative motion"] = "yes" if ecodes.EV_REL in caps else "no"
    except (OSError, PermissionError) as exc:
        errors.append(f"evdev capabilities unavailable: {exc.__class__.__name__}")
    return result, errors


def _backend(backend: HardwareBackend, device: MouseDevice) -> tuple[dict[str, str], list[str]]:
    fields, errors = {"Selected backend": backend.name}, []
    for label, supported, reader in (("DPI", backend.supports_dpi, backend.get_dpi),
                                     ("Polling rate", backend.supports_polling_rate, backend.get_polling_rate)):
        try:
            fields[label] = (str(reader(device)) if supported(device) and reader(device) is not None
                             else ("Supported (readback unavailable)" if supported(device) else "Unsupported"))
        except (HardwareError, OSError, PermissionError) as exc:
            fields[label] = "Unknown"
            errors.append(f"{label} probe failed: {exc.__class__.__name__}")
    fields["Hardware control"] = "native/vendor-specific" if backend.name != "Generic HID / evdev" else "generic input/remapping only"
    return fields, errors


def _descriptor_details(content: bytes) -> dict[str, str]:
    """Summarise HID descriptor items without issuing HID requests."""
    page = report_id = report_size = report_count = 0
    usages: list[str] = []; reports: list[str] = []; collections: list[str] = []
    page_name = lambda value: f"vendor-defined page 0x{value:04x}" if value >= 0xFF00 else f"page 0x{value:04x}"
    index = 0
    while index < len(content):
        prefix = content[index]; index += 1
        if prefix == 0xFE:
            if index + 2 > len(content): break
            size = content[index]; index += 2 + size; continue
        size = (0, 1, 2, 4)[prefix & 0x03]
        item_type, tag = (prefix >> 2) & 3, (prefix >> 4) & 15
        value = int.from_bytes(content[index:index + size], "little"); index += size
        if item_type == 1:
            if tag == 0: page = value
            elif tag == 7: report_size = value
            elif tag == 8: report_id = value
            elif tag == 9: report_count = value
        elif item_type == 2 and tag in (0, 1, 2):
            usages.append(f"{('Usage', 'Usage minimum', 'Usage maximum')[tag]} {page_name(page)}:0x{value:04x}")
        elif item_type == 0:
            if tag == 10: collections.append(f"{page_name(page)}, usage 0x{value:04x}")
            elif tag in (8, 9, 11): reports.append(f"ID {report_id}: { {8: 'Input', 9: 'Output', 11: 'Feature'}[tag]} {report_count} × {report_size} bits")
    unique = lambda values: list(dict.fromkeys(values))
    return {"Descriptor SHA-256": hashlib.sha256(content).hexdigest(), "Descriptor bytes": str(len(content)),
            "Report layout": "; ".join(unique(reports)) or "No main report items parsed",
            "Usages": "; ".join(unique(usages)) or "None parsed", "Collections": "; ".join(unique(collections)) or "None parsed",
            "Raw descriptor (hex)": content.hex()}


def _hid_descriptor(raw: str) -> bytes | None:
    try: return (Path("/sys/class/hidraw") / raw / "device" / "report_descriptor").read_bytes()
    except (OSError, PermissionError): return None


def probe(device: MouseDevice, backend: HardwareBackend) -> dict[str, Any]:
    """Collect an allowlisted report model. All probes are read-only."""
    identity, hidraw, drivers = _sysfs(device)
    capabilities, errors = _capabilities(device)
    backend_fields, backend_errors = _backend(backend, device); errors.extend(backend_errors)
    identity.setdefault("Manufacturer", "Unknown"); identity.setdefault("Product", device.name)
    identity.setdefault("USB VID:PID", f"{device.vendor:04x}:{device.product:04x}" if device.vendor is not None and device.product is not None else "Unknown")
    hid: dict[str, str] = {"Report descriptor": "Unavailable (no selected-mouse hidraw interface detected)"}
    for raw in hidraw:
        content = _hid_descriptor(raw)
        hid = _descriptor_details(content) if content is not None else {"Report descriptor": "Unavailable or inaccessible"}
        if content is not None: break
    return {"mouse_control": {"Version": __version__}, "system": {"Distribution": _system(), "Kernel": platform.release()}, "device": identity,
            "interfaces": {"evdev": "accessible" if os.access(device.path, os.R_OK) else "inaccessible", "hidraw": ", ".join(hidraw) if hidraw else "None detected", "Kernel driver": ", ".join(drivers) if drivers else "Unknown"},
            "input": capabilities, "hid": hid, "backend": backend_fields, "guided": {}, "errors": errors}


def capture_button(device: MouseDevice, seconds: float = 10) -> str | None:
    try:
        with InputDevice(device.path) as input_device:
            ready, _, _ = select.select([input_device.fd], [], [], seconds)
            if ready:
                for event in input_device.read():
                    if event.type == ecodes.EV_KEY and event.value == 1: return ecodes.KEY.get(event.code, f"KEY_{event.code}")
    except (OSError, PermissionError): pass
    return None


def render_report(report: dict[str, Any]) -> str:
    titles = (("mouse_control", "OMUS"), ("system", "System"), ("device", "Device"), ("interfaces", "Interfaces"), ("input", "Input Capabilities"), ("hid", "HID"), ("backend", "Backend"), ("guided", "Guided Tests"))
    lines = ["OMUS Hardware Support Report", "", "Generated by OMUS. This report is intended to be safe to share publicly.", "It contains only selected-mouse and basic system compatibility information.", ""]
    for key, title in titles:
        lines.append(f"[{title}]"); lines.extend(f"{name}: {value}" for name, value in report[key].items()); lines.append("")
    return "\n".join(lines + ["[Probe Results / Errors]", *(report["errors"] or ["None"])]) + "\n"
