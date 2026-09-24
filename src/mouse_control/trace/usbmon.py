# SPDX-License-Identifier: AGPL-3.0-or-later
"""Linux binary-usbmon capture and normalization.

Only the stable binary ABI is used.  The deprecated text format is not parsed.
Opening usbmon is observational, but it can expose unrelated private USB
traffic, so callers must select a physical device before capture.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import re
import struct
from typing import Iterator, Protocol

from ..discovery_models import PhysicalDevice
from .models import (
    CaptureQuality,
    CaptureSource,
    CompletenessStatus,
    UrbEventType,
    UsbDirection,
    UsbObservation,
    UsbSetupPacket,
    UsbTransferType,
)


USBMON_HEADER_SIZE = 64
MAX_CAPTURE_BYTES = 1 << 20
_HEADER = struct.Struct("=QBBBBHccqiiII8siiII")


class UsbmonError(RuntimeError):
    pass


@dataclass(frozen=True)
class UsbmonDeviceSelection:
    bus_id: int
    device_address: int
    physical_device_fingerprint: str
    interface_numbers: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.bus_id <= 0 or self.device_address <= 0:
            raise ValueError("usbmon selection requires current positive bus/address")
        if not self.physical_device_fingerprint:
            raise ValueError("a stable physical fingerprint is required")


@dataclass(frozen=True)
class UsbmonBinaryRecord:
    urb_id: int
    event_code: int
    transfer_code: int
    endpoint_number: int
    device_address: int
    bus_id: int
    setup_flag: int
    data_flag: int
    timestamp_seconds: int
    timestamp_microseconds: int
    status: int
    declared_length: int
    captured_length: int
    setup_bytes: bytes
    interval: int
    start_frame: int
    transfer_flags: int
    descriptor_count: int
    payload: bytes


def parse_usbmon_record(header: bytes, payload: bytes) -> UsbmonBinaryRecord:
    if len(header) != USBMON_HEADER_SIZE:
        raise UsbmonError(f"usbmon extended header must be {USBMON_HEADER_SIZE} bytes")
    fields = _HEADER.unpack(header)
    captured_length = fields[12]
    if captured_length > MAX_CAPTURE_BYTES:
        raise UsbmonError("usbmon captured length exceeds safety limit")
    if len(payload) != captured_length:
        raise UsbmonError("usbmon payload length does not match header")
    return UsbmonBinaryRecord(
        urb_id=fields[0], event_code=fields[1], transfer_code=fields[2],
        endpoint_number=fields[3], device_address=fields[4], bus_id=fields[5],
        setup_flag=fields[6][0], data_flag=fields[7][0],
        timestamp_seconds=fields[8], timestamp_microseconds=fields[9],
        status=fields[10], declared_length=fields[11], captured_length=fields[12],
        setup_bytes=fields[13], interval=fields[14], start_frame=fields[15],
        transfer_flags=fields[16], descriptor_count=fields[17], payload=payload,
    )


def _event_type(code: int) -> UrbEventType:
    return {
        ord("S"): UrbEventType.SUBMIT,
        ord("C"): UrbEventType.COMPLETE,
        ord("E"): UrbEventType.ERROR,
    }.get(code, UrbEventType.UNKNOWN)


def _transfer_type(code: int) -> UsbTransferType:
    return {
        0: UsbTransferType.ISOCHRONOUS,
        1: UsbTransferType.INTERRUPT,
        2: UsbTransferType.CONTROL,
        3: UsbTransferType.BULK,
    }.get(code, UsbTransferType.UNKNOWN)


def _setup(record: UsbmonBinaryRecord) -> UsbSetupPacket | None:
    # usbmon uses zero to mean that the setup bytes are present.
    if record.transfer_code != 2 or record.setup_flag != 0:
        return None
    request_type, request, value, index, length = struct.unpack("<BBHHH", record.setup_bytes)
    return UsbSetupPacket(request_type, request, value, index, length)


def normalize_usbmon_record(
    record: UsbmonBinaryRecord,
    *,
    capture_id: str,
    sequence: int,
    selection: UsbmonDeviceSelection,
) -> UsbObservation | None:
    if record.bus_id != selection.bus_id or record.device_address != selection.device_address:
        return None
    setup = _setup(record)
    endpoint = record.endpoint_number & 0x7F
    direction = UsbDirection.IN if record.endpoint_number & 0x80 else UsbDirection.OUT
    if setup is not None:
        direction = setup.direction
    interface_number = None
    if setup is not None and (setup.bm_request_type & 0x1F) == 1:
        candidate = setup.index & 0xFF
        if not selection.interface_numbers or candidate in selection.interface_numbers:
            interface_number = candidate
    return UsbObservation(
        capture_id=capture_id,
        sequence=sequence,
        timestamp_ns=(record.timestamp_seconds * 1_000_000_000
                      + record.timestamp_microseconds * 1_000),
        source=CaptureSource.USBMON_BINARY,
        bus_id=record.bus_id,
        device_address=record.device_address,
        interface_number=interface_number,
        endpoint=endpoint,
        direction=direction,
        transfer_type=_transfer_type(record.transfer_code),
        event_type=_event_type(record.event_code),
        urb_id=record.urb_id,
        status=record.status,
        setup=setup,
        declared_length=record.declared_length,
        captured_length=record.captured_length,
        payload=record.payload,
        physical_device_fingerprint=selection.physical_device_fingerprint,
        setup_flag=record.setup_flag,
        data_flag=record.data_flag,
        interval=record.interval,
        start_frame=record.start_frame,
        transfer_flags=record.transfer_flags,
        descriptor_count=record.descriptor_count,
        capture_quality=CaptureQuality(
            source_representation="linux_usbmon_binary_extended",
            full_binary_header_available=True,
            completeness=(
                CompletenessStatus.TRUNCATED
                if record.captured_length < record.declared_length
                else CompletenessStatus.COMPLETE
            ),
        ),
    )


def selection_from_physical_device(device: PhysicalDevice) -> UsbmonDeviceSelection:
    if device.ambiguous:
        raise UsbmonError("refusing usbmon capture for an ambiguous physical device")
    if device.parent_path is None:
        raise UsbmonError("physical device has no USB parent")
    try:
        bus_id = int((device.parent_path / "busnum").read_text().strip())
        address = int((device.parent_path / "devnum").read_text().strip())
    except (OSError, ValueError) as exc:
        raise UsbmonError("could not resolve the device's current USB bus/address") from exc
    fingerprint = device.instance_fingerprint or device.model_fingerprint
    if not fingerprint:
        raise UsbmonError("physical device has no stable fingerprint")
    interfaces = tuple(sorted({
        node.interface_number for node in device.all_nodes
        if node.interface_number is not None
    }))
    return UsbmonDeviceSelection(bus_id, address, fingerprint, interfaces)


class _RecordReader(Protocol):
    def read_record(self, maximum_payload: int) -> tuple[bytes, bytes]: ...
    def close(self) -> None: ...


class _UsbmonPacket(ctypes.Structure):
    _fields_ = [
        ("urb_id", ctypes.c_uint64), ("event_type", ctypes.c_ubyte),
        ("transfer_type", ctypes.c_ubyte), ("endpoint", ctypes.c_ubyte),
        ("device", ctypes.c_ubyte), ("bus", ctypes.c_uint16),
        ("setup_flag", ctypes.c_byte), ("data_flag", ctypes.c_byte),
        ("seconds", ctypes.c_int64), ("microseconds", ctypes.c_int32),
        ("status", ctypes.c_int32), ("length", ctypes.c_uint32),
        ("captured_length", ctypes.c_uint32), ("setup", ctypes.c_ubyte * 8),
        ("interval", ctypes.c_int32), ("start_frame", ctypes.c_int32),
        ("transfer_flags", ctypes.c_uint32), ("descriptor_count", ctypes.c_uint32),
    ]


class _MonGetArg(ctypes.Structure):
    _fields_ = [
        ("header", ctypes.POINTER(_UsbmonPacket)),
        ("data", ctypes.c_void_p),
        ("allocation", ctypes.c_size_t),
    ]


def _iow(type_: int, number: int, size: int) -> int:
    return (1 << 30) | (size << 16) | (type_ << 8) | number


MON_IOCX_GETX = _iow(0x92, 10, ctypes.sizeof(_MonGetArg))


class _IoctlRecordReader:
    def __init__(self, path: Path) -> None:
        self._fd = os.open(path, os.O_RDONLY)
        self._libc = ctypes.CDLL(None, use_errno=True)

    def read_record(self, maximum_payload: int) -> tuple[bytes, bytes]:
        packet = _UsbmonPacket()
        data = (ctypes.c_ubyte * maximum_payload)()
        argument = _MonGetArg(ctypes.pointer(packet), ctypes.addressof(data), maximum_payload)
        result = self._libc.ioctl(self._fd, MON_IOCX_GETX, ctypes.byref(argument))
        if result < 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        header = ctypes.string_at(ctypes.addressof(packet), USBMON_HEADER_SIZE)
        length = min(packet.captured_length, maximum_payload)
        return header, bytes(data[:length])

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1


class UsbmonCaptureProvider:
    def __init__(self, *, dev_root: Path = Path("/dev")) -> None:
        self._dev_root = dev_root

    def available_buses(self) -> tuple[int, ...]:
        buses = []
        for path in self._dev_root.glob("usbmon*"):
            match = re.fullmatch(r"usbmon([0-9]+)", path.name)
            if match and path.is_char_device():
                buses.append(int(match.group(1)))
        return tuple(sorted(set(buses)))

    def capture(
        self,
        selection: UsbmonDeviceSelection,
        *,
        capture_id: str,
        limit: int | None = None,
        maximum_payload: int = 4096,
        reader: _RecordReader | None = None,
    ) -> Iterator[UsbObservation]:
        if not capture_id:
            raise ValueError("capture_id is required")
        if not 0 <= maximum_payload <= MAX_CAPTURE_BYTES:
            raise ValueError("maximum_payload is outside the safe range")
        owned = reader is None
        stream = reader or _IoctlRecordReader(self._dev_root / f"usbmon{selection.bus_id}")
        sequence = 0
        emitted = 0
        try:
            while limit is None or emitted < limit:
                header, payload = stream.read_record(maximum_payload)
                record = parse_usbmon_record(header, payload)
                observation = normalize_usbmon_record(
                    record, capture_id=capture_id, sequence=sequence, selection=selection
                )
                sequence += 1
                if observation is not None:
                    emitted += 1
                    yield observation
        finally:
            if owned:
                stream.close()
