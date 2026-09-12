"""Interactive Logitech HID++ discovery and passive report capture."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
import select
import sys
from typing import Callable

from .hidpp import (ADJUSTABLE_DPI_FEATURE_ID, DEVICE_NAME_FEATURE_ID,
                    DpiEventMetadata, discover_hidpp_device,
                    dpi_event_candidate, parse_hidpp_report,
                    save_hidpp_device, validated_dpi_decoder_profile,
                    HidppDevice)


def _candidate_identities(sysfs: Path = Path("/sys/class/hidraw")) -> list[tuple[int, int]]:
    identities: set[tuple[int, int]] = set()
    for entry in sysfs.glob("hidraw*"):
        try:
            fields = dict(line.split("=", 1) for line in
                          (entry / "device/uevent").read_text().splitlines() if "=" in line)
            _bus, vendor, product = fields.get("HID_ID", "").split(":")
            identity = int(vendor, 16), int(product, 16)
        except (OSError, ValueError):
            continue
        if identity[0] == 0x046D:
            identities.add(identity)
    return sorted(identities)


def coordinated_discovery(
    *,
    discover: Callable[..., HidppDevice | None] = discover_hidpp_device,
    save: Callable[[HidppDevice], Path] = save_hidpp_device,
) -> list[HidppDevice]:
    """Perform explicit live discovery; mouse-control owns HID++ traffic."""
    devices = [device for vendor, product in _candidate_identities()
               if (device := discover(vendor, product)) is not None]
    for device in devices:
        path = save(device)
        print(f"Saved HID++ capability metadata to {path}")
    return devices


def debug_dpi() -> int:
    try:
        devices = coordinated_discovery()
    except KeyboardInterrupt:
        print("\nHID++ discovery interrupted.", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"Could not perform HID++ discovery: {exc}", file=sys.stderr)
        return 1
    if not devices:
        print("No unambiguous Logitech HID++ device could be discovered.", file=sys.stderr)
        return 1
    if len(devices) > 1:
        print("Multiple Logitech HID++ devices found; refusing ambiguous capture.", file=sys.stderr)
        return 1
    device = devices[0]
    name_feature = device.feature(DEVICE_NAME_FEATURE_ID)
    dpi_feature = device.feature(ADJUSTABLE_DPI_FEATURE_ID)
    profile = validated_dpi_decoder_profile(device)
    protocol = (f"{device.protocol_version[0]}.{device.protocol_version[1]}"
                if device.protocol_version else "unknown")
    print(f"Logitech HID++ device: {device.name or 'name unavailable'}")
    print(f"VID:PID: {device.vendor_id:04x}:{device.product_id:04x}")
    print(f"HID++ protocol: {protocol}")
    print("Device Name feature: " +
          (f"0x0005 -> index 0x{name_feature.index:02x}, version {name_feature.version}"
           if name_feature else "0x0005 -> unavailable"))
    print("Adjustable DPI feature: " +
          (f"0x2201 -> index 0x{dpi_feature.index:02x}, version {dpi_feature.version}"
           if dpi_feature else "0x2201 -> unavailable"))
    print(f"DPI event decoder: {'validated' if profile else 'unsupported/unvalidated'}")
    try:
        fd = os.open(device.hidraw_path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as exc:
        print(f"Cannot open {device.hidraw_path} read-only: {exc}", file=sys.stderr)
        return 1
    print(f"Passive HID++ capture from {device.hidraw_path}; no reports will be written.")
    if profile is not None:
        print("Press the physical DPI button several times to learn the passive event index.")
    print("Press Ctrl+C to finish.")
    candidate_indexes: set[int] = set()
    try:
        while True:
            readable, _, _ = select.select([fd], [], [], 1.0)
            if not readable:
                continue
            data = os.read(fd, 64)
            report = parse_hidpp_report(data)
            if report is None:
                continue
            candidate = dpi_event_candidate(data, device, profile) if profile else None
            if candidate is not None:
                candidate_indexes.add(candidate)
            stage = report.parameters[0] if candidate is not None else None
            raw = data.hex(" ")
            if stage is not None:
                print(f"DPI stage event: {stage} | {raw}")
            else:
                kind = "notification candidate" if report.software_id == 0 else "response/request"
                print(f"HID++ {kind}: report=0x{report.report_id:02x} "
                      f"device=0x{report.device_index:02x} feature-index=0x{report.feature_index:02x} "
                      f"function/event=0x{report.function_or_event:x} swid=0x{report.software_id:x} "
                      f"params={report.parameters.hex(' ')} | {raw}")
    except KeyboardInterrupt:
        print("\nCapture finished.")
    finally:
        os.close(fd)
    if len(candidate_indexes) == 1 and profile is not None:
        event_index = next(iter(candidate_indexes))
        device = replace(device, dpi_event=DpiEventMetadata(
            event_index, profile.report_id, profile.event
        ))
        path = save_hidpp_device(device)
        print(f"Learned passive DPI event feature index 0x{event_index:02x}; saved to {path}")
    elif len(candidate_indexes) > 1:
        indexes = ", ".join(f"0x{index:02x}" for index in sorted(candidate_indexes))
        print(f"Conflicting passive DPI event indexes observed ({indexes}); none was saved.",
              file=sys.stderr)
    elif profile is not None:
        print("No validated passive DPI event was observed; no event index was saved.",
              file=sys.stderr)
    return 0
