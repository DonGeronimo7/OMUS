"""Read-only HID++ report capture for validating native G305 DPI events."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import select
import sys
import threading
from typing import Callable


G305_HID_ID = "0003:0000046D:00004074"
HIDPP_REPORT_IDS = {0x10, 0x11, 0x12}
LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class HidppReport:
    report_id: int
    device_index: int
    feature_index: int
    function_or_event: int
    software_id: int
    parameters: bytes


@dataclass(frozen=True)
class DpiEventProfile:
    """Hardware-validated, device-specific meaning of a HID++ feature index."""
    vendor: int
    product: int
    device_index: int
    feature_index: int
    event: int


# Feature indices are assigned by each device, not global HID++ feature IDs.
# This value is intentionally scoped to the real-hardware-validated G305 only.
G305_DPI_PROFILE = DpiEventProfile(0x046D, 0x4074, 0x01, 0x07, 0x01)


def parse_hidpp_report(data: bytes) -> HidppReport | None:
    """Decode the common HID++ header while retaining raw parameters."""
    if len(data) < 4 or data[0] not in HIDPP_REPORT_IDS:
        return None
    return HidppReport(
        report_id=data[0],
        device_index=data[1],
        feature_index=data[2],
        function_or_event=data[3] >> 4,
        software_id=data[3] & 0x0F,
        parameters=data[4:],
    )


def find_hidraw(vendor: int, product: int, phys: str = "",
                sysfs: Path = Path("/sys/class/hidraw"),
                dev_root: Path = Path("/dev")) -> list[Path]:
    """Resolve hidraw nodes by exact HID identity, never by node number."""
    matches = []
    for entry in sorted(sysfs.glob("hidraw*")):
        try:
            fields = dict(line.split("=", 1) for line in
                          (entry / "device/uevent").read_text().splitlines()
                          if "=" in line)
        except OSError:
            continue
        expected = f"0003:0000{vendor:04X}:0000{product:04X}"
        if fields.get("HID_ID") == expected and (not phys or fields.get("HID_PHYS") == phys):
            matches.append(dev_root / entry.name)
    return matches


def find_g305_hidraw(sysfs: Path = Path("/sys/class/hidraw"),
                      dev_root: Path = Path("/dev")) -> list[Path]:
    return find_hidraw(0x046D, 0x4074, sysfs=sysfs, dev_root=dev_root)


def dpi_stage_event(data: bytes, profile: DpiEventProfile) -> int | None:
    """Return a stage index only for the hardware-validated DPI notification."""
    report = parse_hidpp_report(data)
    if (report is None or report.report_id != 0x11 or
            report.device_index != profile.device_index or
            report.feature_index != profile.feature_index or
            report.function_or_event != profile.event or
            report.software_id != 0 or not report.parameters):
        return None
    return report.parameters[0]


def watch_dpi_events(profile: DpiEventProfile, phys: str,
                     callback: Callable[[int], None], shutdown_event: threading.Event,
                     *, retry_interval: float = 1.0) -> None:
    """Passively watch DPI events, re-resolving hidraw after sleep/reconnect."""
    warned: str | None = None
    while not shutdown_event.is_set():
        nodes = find_hidraw(profile.vendor, profile.product, phys)
        if len(nodes) != 1:
            message = ("no matching hidraw node" if not nodes else
                       "multiple matching hidraw nodes; refusing an ambiguous capture")
            if warned != message:
                LOG.warning("HID++ DPI monitoring unavailable: %s", message)
                warned = message
            shutdown_event.wait(retry_interval)
            continue
        try:
            fd = os.open(nodes[0], os.O_RDONLY | os.O_NONBLOCK)
        except OSError as exc:
            message = f"cannot open {nodes[0]} read-only: {exc}"
            if warned != message:
                LOG.warning("HID++ DPI monitoring unavailable: %s", message)
                warned = message
            shutdown_event.wait(retry_interval)
            continue

        warned = None
        try:
            while not shutdown_event.is_set():
                readable, _, _ = select.select([fd], [], [], 0.25)
                if not readable:
                    continue
                data = os.read(fd, 64)
                if not data:
                    raise OSError("hidraw device closed")
                stage = dpi_stage_event(data, profile)
                if stage is not None:
                    callback(stage)
        except OSError as exc:
            LOG.warning("HID++ DPI monitor disconnected; retrying: %s", exc)
        except Exception:
            LOG.exception("HID++ DPI monitor failed; retrying")
        finally:
            os.close(fd)
        shutdown_event.wait(retry_interval)


def debug_dpi() -> int:
    """Passively print interrupt-IN reports without sending HID++ commands."""
    nodes = find_g305_hidraw()
    if not nodes:
        print("No Logitech G305 hidraw node found (expected USB 046d:4074).", file=sys.stderr)
        return 1
    node = nodes[0]
    try:
        fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
    except PermissionError:
        print(f"Cannot read {node}.", file=sys.stderr)
        print(f"Temporary test only: sudo setfacl -m u:$USER:r {node}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Cannot open {node}: {exc}", file=sys.stderr)
        return 1

    print(f"Passive HID++ capture from {node} ({G305_HID_ID})")
    print("No reports are written and the firmware button mapping is not changed.")
    print("Press the physical DPI button several times; press Ctrl+C to finish.")
    try:
        while True:
            readable, _, _ = select.select([fd], [], [], 1.0)
            if not readable:
                continue
            data = os.read(fd, 64)
            report = parse_hidpp_report(data)
            stage = dpi_stage_event(data, G305_DPI_PROFILE)
            raw = data.hex(" ")
            if stage is not None:
                print(f"G305 DPI stage event: {stage} | {raw}")
            elif report is None:
                continue
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
    return 0
