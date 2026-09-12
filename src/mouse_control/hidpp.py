"""Logitech HID++ packet primitives and diagnostic discovery helpers.

Feature indexes are assigned by each device and resolved through ROOT. Runtime
ownership and capability behavior live in :mod:`hid_session` and
:mod:`hidpp_driver`; the cache here is diagnostic metadata, never write authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import select
import threading
import time
from typing import Any, Callable, Protocol

LOG = logging.getLogger(__name__)
LOGITECH_VENDOR_ID = 0x046D
HIDPP_REPORT_IDS = {0x10, 0x11, 0x12}
HIDPP_LONG_REPORT_ID = 0x11
ROOT_FEATURE_INDEX = 0x00
DEVICE_NAME_FEATURE_ID = 0x0005
ADJUSTABLE_DPI_FEATURE_ID = 0x2201
DISCOVERY_SOFTWARE_ID = 0x0A
CACHE_SCHEMA_VERSION = 2
CACHE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


@dataclass(frozen=True)
class HidppReport:
    report_id: int
    device_index: int
    feature_index: int
    function_or_event: int
    software_id: int
    parameters: bytes


@dataclass(frozen=True)
class HidppFeature:
    feature_id: int
    index: int
    feature_type: int
    version: int


@dataclass(frozen=True)
class DpiEventMetadata:
    """Observed routing metadata for unsolicited passive DPI events."""
    feature_index: int
    report_id: int
    event: int


@dataclass(frozen=True)
class HidppDevice:
    vendor_id: int
    product_id: int
    device_index: int
    name: str | None
    hidraw_path: Path
    protocol_version: tuple[int, int] | None
    features: dict[int, HidppFeature]
    phys: str = ""
    dpi_event: DpiEventMetadata | None = None

    def feature(self, feature_id: int) -> HidppFeature | None:
        return self.features.get(feature_id)


@dataclass(frozen=True)
class DpiEventDecoderProfile:
    """Hardware validation metadata; the feature index is discovered."""
    vendor_id: int
    product_id: int
    feature_version: int
    event: int = 0x01
    report_id: int = HIDPP_LONG_REPORT_ID


# This event payload is physically validated only on this device/version.
VALIDATED_DPI_EVENT_PROFILES = {
    (0x046D, 0x4074): DpiEventDecoderProfile(0x046D, 0x4074, feature_version=1),
}


class HidppError(RuntimeError):
    pass


def get_hidpp_cache_path() -> Path:
    cache_home = os.environ.get("XDG_CACHE_HOME")
    root = Path(cache_home) if cache_home else Path.home() / ".cache"
    return root / "mouse-control" / "hidpp-capabilities.json"


def _cache_key(vendor_id: int, product_id: int) -> str:
    return f"{vendor_id:04x}:{product_id:04x}"


def _feature_to_json(feature: HidppFeature) -> dict[str, int]:
    return {"index": feature.index, "type": feature.feature_type,
            "version": feature.version}


def save_hidpp_device(device: HidppDevice, path: Path | None = None,
                      *, now: float | None = None) -> Path:
    """Atomically persist discovery metadata, never a transient hidraw number."""
    cache_path = path or get_hidpp_cache_path()
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != CACHE_SCHEMA_VERSION:
            data = {"schema": CACHE_SCHEMA_VERSION, "devices": {}}
    except (OSError, ValueError):
        data = {"schema": CACHE_SCHEMA_VERSION, "devices": {}}
    devices = data.setdefault("devices", {})
    devices[_cache_key(device.vendor_id, device.product_id)] = {
        "vendor_id": device.vendor_id,
        "product_id": device.product_id,
        "device_index": device.device_index,
        "name": device.name,
        "protocol": list(device.protocol_version) if device.protocol_version else None,
        "features": {f"{feature_id:04x}": _feature_to_json(feature)
                     for feature_id, feature in device.features.items()},
        "dpi_event": ({"feature_index": device.dpi_event.feature_index,
                       "report_id": device.dpi_event.report_id,
                       "event": device.dpi_event.event}
                      if device.dpi_event is not None else None),
        "discovered_at": time.time() if now is None else now,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(cache_path)
    return cache_path


def load_cached_hidpp_device(vendor_id: int, product_id: int, phys: str = "",
                             *, path: Path | None = None,
                             now: float | None = None,
                             sysfs: Path = Path("/sys/class/hidraw"),
                             dev_root: Path = Path("/dev")) -> HidppDevice | None:
    """Load fresh, structurally valid metadata and bind it to the current node."""
    cache_path = path or get_hidpp_cache_path()
    try:
        data: Any = json.loads(cache_path.read_text(encoding="utf-8"))
        entry = data["devices"][_cache_key(vendor_id, product_id)]
        timestamp = float(entry["discovered_at"])
        current_time = time.time() if now is None else now
        if (data.get("schema") != CACHE_SCHEMA_VERSION or timestamp > current_time + 60 or
                current_time - timestamp > CACHE_MAX_AGE_SECONDS or
                entry["vendor_id"] != vendor_id or entry["product_id"] != product_id):
            return None
        device_index = int(entry["device_index"])
        protocol_data = entry["protocol"]
        protocol = ((int(protocol_data[0]), int(protocol_data[1]))
                    if isinstance(protocol_data, list) and len(protocol_data) == 2 else None)
        if not 1 <= device_index <= 0xFF or protocol is None or protocol[0] < 2:
            return None
        features: dict[int, HidppFeature] = {}
        for feature_text, values in entry["features"].items():
            feature_id = int(feature_text, 16)
            feature = HidppFeature(feature_id, int(values["index"]),
                                   int(values["type"]), int(values["version"]))
            if not 1 <= feature.index < 0xFF:
                return None
            features[feature_id] = feature
        if any(feature_id not in (DEVICE_NAME_FEATURE_ID, ADJUSTABLE_DPI_FEATURE_ID)
               for feature_id in features):
            return None
        name = entry.get("name")
        if name is not None and (not isinstance(name, str) or not name.strip()):
            return None
        event_data = entry.get("dpi_event")
        dpi_event = None
        if event_data is not None:
            dpi_event = DpiEventMetadata(int(event_data["feature_index"]),
                                         int(event_data["report_id"]),
                                         int(event_data["event"]))
            if (not 1 <= dpi_event.feature_index < 0xFF or
                    dpi_event.report_id not in HIDPP_REPORT_IDS or
                    not 0 <= dpi_event.event <= 0x0F):
                return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    bound_phys = phys
    nodes = find_hidraw(vendor_id, product_id, bound_phys, sysfs, dev_root)
    if not nodes and phys:
        nodes = find_hidraw(vendor_id, product_id, "", sysfs, dev_root)
        bound_phys = ""
    if len(nodes) != 1:
        return None
    return HidppDevice(vendor_id, product_id, device_index, name, nodes[0],
                       protocol, features, bound_phys, dpi_event)


class HidppTransport(Protocol):
    def request(self, device_index: int, feature_index: int, function: int,
                parameters: bytes = b"") -> HidppReport: ...


def parse_hidpp_report(data: bytes) -> HidppReport | None:
    if len(data) < 4 or data[0] not in HIDPP_REPORT_IDS:
        return None
    return HidppReport(data[0], data[1], data[2], data[3] >> 4,
                       data[3] & 0x0F, data[4:])


def find_hidraw(vendor_id: int, product_id: int, phys: str = "",
                sysfs: Path = Path("/sys/class/hidraw"),
                dev_root: Path = Path("/dev")) -> list[Path]:
    """Resolve nodes by exact HID identity and optional physical path."""
    matches: list[Path] = []
    expected = f"0003:0000{vendor_id:04X}:0000{product_id:04X}"
    for entry in sorted(sysfs.glob("hidraw*")):
        try:
            fields = dict(line.split("=", 1) for line in
                          (entry / "device/uevent").read_text().splitlines() if "=" in line)
        except OSError:
            continue
        if fields.get("HID_ID") == expected and (not phys or fields.get("HID_PHYS") == phys):
            matches.append(dev_root / entry.name)
    return matches


class HidrawTransport:
    """Short-lived initialization transport with strict response matching."""

    def __init__(self, path: Path, timeout: float = 0.5) -> None:
        self.path, self.timeout, self.fd = path, timeout, None

    def __enter__(self) -> "HidrawTransport":
        self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        return self

    def __exit__(self, *_args: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def request(self, device_index: int, feature_index: int, function: int,
                parameters: bytes = b"") -> HidppReport:
        if self.fd is None:
            raise HidppError("HID++ transport is not open")
        packet = bytes((0x11, device_index, feature_index,
                        (function << 4) | DISCOVERY_SOFTWARE_ID)) + parameters[:16].ljust(16, b"\0")
        os.write(self.fd, packet)
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HidppError("timed out waiting for a matching HID++ response")
            readable, _, _ = select.select([self.fd], [], [], remaining)
            if not readable:
                continue
            report = parse_hidpp_report(os.read(self.fd, 64))
            if report is None:
                continue
            response_address = (function << 4) | DISCOVERY_SOFTWARE_ID
            if (report.feature_index == 0xFF and
                    ((report.function_or_event << 4) | report.software_id) == feature_index and
                    report.parameters and report.parameters[0] == response_address):
                code = report.parameters[1] if len(report.parameters) > 1 else 0
                raise HidppError(f"device returned HID++ error 0x{code:02x}")
            if (report.device_index == device_index and report.feature_index == feature_index and
                    report.function_or_event == function and
                    report.software_id == DISCOVERY_SOFTWARE_ID):
                return report


def lookup_feature(transport: HidppTransport, device_index: int,
                   feature_id: int) -> HidppFeature | None:
    """Resolve a HID++ 2.0 feature ID through ROOT getFeature."""
    response = transport.request(device_index, ROOT_FEATURE_INDEX, 0,
                                 bytes((feature_id >> 8, feature_id & 0xFF, 0)))
    if not response.parameters or response.parameters[0] == 0:
        return None
    parameters = response.parameters.ljust(3, b"\0")
    return HidppFeature(feature_id, parameters[0], parameters[1], parameters[2])


def get_protocol_version(transport: HidppTransport,
                         device_index: int) -> tuple[int, int] | None:
    response = transport.request(device_index, ROOT_FEATURE_INDEX, 1)
    if len(response.parameters) < 2 or response.parameters[0] < 2:
        return None
    return response.parameters[0], response.parameters[1]


def get_device_name(transport: HidppTransport, device_index: int,
                    feature: HidppFeature) -> str | None:
    count = transport.request(device_index, feature.index, 0).parameters
    if not count or count[0] == 0:
        return None
    length, raw = count[0], bytearray()
    while len(raw) < length:
        chunk = transport.request(device_index, feature.index, 1, bytes((len(raw),))).parameters
        if not chunk:
            break
        raw.extend(chunk[:length - len(raw)])
    name = bytes(raw).rstrip(b"\0").decode("utf-8", errors="replace").strip()
    return name or None


def discover_hidpp_device(vendor_id: int, product_id: int, phys: str = "",
                          *, device_index: int | None = None,
                          transport_factory: Callable[[Path], HidrawTransport] = HidrawTransport,
                          sysfs: Path = Path("/sys/class/hidraw"),
                          dev_root: Path = Path("/dev")) -> HidppDevice | None:
    """Discover one exact Logitech device without guessing ambiguous nodes."""
    if vendor_id != LOGITECH_VENDOR_ID:
        return None
    nodes = find_hidraw(vendor_id, product_id, phys, sysfs, dev_root)
    if len(nodes) != 1:
        return None
    path = nodes[0]
    try:
        with transport_factory(path) as transport:
            selected_index: int | None = None
            protocol: tuple[int, int] | None = None
            for candidate in ((device_index,) if device_index is not None
                              else (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0xFF)):
                try:
                    protocol = get_protocol_version(transport, candidate)
                except HidppError:
                    continue
                if protocol is not None:
                    selected_index = candidate
                    break
            if selected_index is None:
                raise HidppError("no HID++ 2.0 device index responded")
            features: dict[int, HidppFeature] = {}
            for feature_id in (DEVICE_NAME_FEATURE_ID, ADJUSTABLE_DPI_FEATURE_ID):
                feature = lookup_feature(transport, selected_index, feature_id)
                if feature is not None:
                    features[feature_id] = feature
            name_feature = features.get(DEVICE_NAME_FEATURE_ID)
            name = get_device_name(transport, selected_index, name_feature) if name_feature else None
    except (OSError, HidppError) as exc:
        LOG.info("Logitech HID++ capability discovery unavailable: %s", exc)
        return None
    return HidppDevice(vendor_id, product_id, selected_index, name, path, protocol, features, phys)


def validated_dpi_decoder_profile(device: HidppDevice) -> DpiEventDecoderProfile | None:
    feature = device.feature(ADJUSTABLE_DPI_FEATURE_ID)
    profile = VALIDATED_DPI_EVENT_PROFILES.get((device.vendor_id, device.product_id))
    if feature is None or profile is None or feature.version != profile.feature_version:
        return None
    return profile


def dpi_decoder_profile(device: HidppDevice) -> DpiEventDecoderProfile | None:
    profile = validated_dpi_decoder_profile(device)
    event = device.dpi_event
    if (profile is None or event is None or event.report_id != profile.report_id or
            event.event != profile.event):
        return None
    return profile


def dpi_event_candidate(data: bytes, device: HidppDevice,
                        profile: DpiEventDecoderProfile,
                        *, maximum_stage: int = 4) -> int | None:
    """Return an observed event index only for a validated notification shape."""
    report = parse_hidpp_report(data)
    if (report is None or report.report_id != profile.report_id or
            report.device_index != device.device_index or
            report.function_or_event != profile.event or report.software_id != 0 or
            not report.parameters or report.parameters[0] > maximum_stage):
        return None
    return report.feature_index


def dpi_stage_event(data: bytes, device: HidppDevice,
                    profile: DpiEventDecoderProfile) -> int | None:
    event, report = device.dpi_event, parse_hidpp_report(data)
    if (event is None or report is None or report.report_id != event.report_id or
            report.device_index != device.device_index or report.feature_index != event.feature_index or
            report.function_or_event != profile.event or report.software_id != 0 or
            not report.parameters):
        return None
    return report.parameters[0]


def watch_dpi_events(device: HidppDevice, profile: DpiEventDecoderProfile,
                     callback: Callable[[int], None], shutdown_event: threading.Event,
                     *, retry_interval: float = 1.0) -> None:
    """Passively read events; no HID++ command is sent during normal runtime."""
    warned: str | None = None
    while not shutdown_event.is_set():
        nodes = find_hidraw(device.vendor_id, device.product_id, device.phys)
        if len(nodes) != 1:
            message = ("no matching hidraw node" if not nodes else
                       "multiple matching hidraw nodes; refusing ambiguous capture")
            if warned != message:
                LOG.warning("HID++ DPI monitoring unavailable: %s", message)
                warned = message
            shutdown_event.wait(retry_interval)
            continue
        try:
            node = nodes[0]
            fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as exc:
            message = f"cannot open {node} read-only: {exc}"
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
                stage = dpi_stage_event(data, device, profile)
                if stage is not None:
                    callback(stage)
        except OSError as exc:
            LOG.warning("HID++ DPI monitor disconnected; retrying: %s", exc)
        except Exception:
            LOG.exception("HID++ DPI monitor failed; retrying")
        finally:
            os.close(fd)
        shutdown_event.wait(retry_interval)
