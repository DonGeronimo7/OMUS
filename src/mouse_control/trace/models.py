# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stable, protocol-neutral models for raw USB trace evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


TRACE_SCHEMA_VERSION = 1


class CaptureSource(str, Enum):
    USBMON_BINARY = "usbmon_binary"
    PCAPNG_USBMON = "pcapng_usbmon"
    PCAP_USBMON = "pcap_usbmon"
    USBPCAP = "usbpcap"
    WIRESHARK_EXPORT = "wireshark_export"
    HARDWARE_SNIFFER = "hardware_sniffer"
    SYNTHETIC_TEST = "synthetic_test"


class UsbDirection(str, Enum):
    IN = "in"
    OUT = "out"
    UNKNOWN = "unknown"


class UsbTransferType(str, Enum):
    CONTROL = "control"
    INTERRUPT = "interrupt"
    BULK = "bulk"
    ISOCHRONOUS = "isochronous"
    UNKNOWN = "unknown"


class UrbEventType(str, Enum):
    SUBMIT = "submit"
    COMPLETE = "complete"
    ERROR = "error"
    UNKNOWN = "unknown"


class TransactionAnomaly(str, Enum):
    MISSING_SUBMIT = "missing_submit"
    MISSING_COMPLETION = "missing_completion"
    REUSED_URB = "reused_urb"
    EVENT_MISMATCH = "event_mismatch"
    CAPTURE_BOUNDARY = "capture_boundary"


class CompletenessStatus(str, Enum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CaptureQuality:
    """Session/source quality facts; absence is deliberately not encoded as zero."""

    source_representation: str | None = None
    full_binary_header_available: bool | None = None
    dropped_record_count: int | None = None
    clock_timebase: str | None = None
    completeness: CompletenessStatus = CompletenessStatus.UNKNOWN

    def __post_init__(self) -> None:
        if self.dropped_record_count is not None and self.dropped_record_count < 0:
            raise ValueError("dropped_record_count cannot be negative")


@dataclass(frozen=True)
class UsbSetupPacket:
    bm_request_type: int
    request: int
    value: int
    index: int
    length: int

    def __post_init__(self) -> None:
        for name in ("bm_request_type", "request"):
            if not 0 <= getattr(self, name) <= 0xFF:
                raise ValueError(f"{name} must fit in one byte")
        for name in ("value", "index", "length"):
            if not 0 <= getattr(self, name) <= 0xFFFF:
                raise ValueError(f"{name} must fit in two bytes")

    @property
    def direction(self) -> UsbDirection:
        return UsbDirection.IN if self.bm_request_type & 0x80 else UsbDirection.OUT


@dataclass(frozen=True)
class UsbObservation:
    capture_id: str
    sequence: int
    timestamp_ns: int
    source: CaptureSource
    bus_id: int | None
    device_address: int | None
    interface_number: int | None
    endpoint: int | None
    direction: UsbDirection
    transfer_type: UsbTransferType
    event_type: UrbEventType
    urb_id: int | None
    status: int | None
    setup: UsbSetupPacket | None
    declared_length: int | None
    captured_length: int
    payload: bytes
    physical_device_fingerprint: str
    setup_flag: int | None = None
    data_flag: int | None = None
    interval: int | None = None
    start_frame: int | None = None
    transfer_flags: int | None = None
    descriptor_count: int | None = None
    capture_quality: CaptureQuality | None = None

    def __post_init__(self) -> None:
        if not self.capture_id:
            raise ValueError("capture_id is required")
        if self.sequence < 0 or self.timestamp_ns < 0:
            raise ValueError("sequence and timestamp must be non-negative")
        if self.captured_length < 0 or self.captured_length != len(self.payload):
            raise ValueError("captured_length must equal the payload length")
        if self.declared_length is not None and self.declared_length < 0:
            raise ValueError("declared_length cannot be negative")
        if not self.physical_device_fingerprint:
            raise ValueError("physical_device_fingerprint is required")
        for name in ("setup_flag", "data_flag"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 0xFF:
                raise ValueError(f"{name} must fit in one byte")
        for name in ("interval", "start_frame", "descriptor_count"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.transfer_flags is not None and not 0 <= self.transfer_flags <= 0xFFFFFFFF:
            raise ValueError("transfer_flags must fit in four bytes")


@dataclass(frozen=True)
class UsbTransaction:
    transaction_id: str
    submit: UsbObservation | None
    completion: UsbObservation | None
    request_payload: bytes
    response_payload: bytes
    setup: UsbSetupPacket | None
    transfer_type: UsbTransferType
    endpoint: int | None
    direction: UsbDirection
    status: int | None
    latency_ns: int | None
    complete: bool
    anomaly: TransactionAnomaly | None = None

    def __post_init__(self) -> None:
        if not self.transaction_id:
            raise ValueError("transaction_id is required")
        if self.submit is None and self.completion is None:
            raise ValueError("transaction requires at least one observation")
        if self.latency_ns is not None and self.latency_ns < 0:
            raise ValueError("latency cannot be negative")
        if self.complete != (self.submit is not None and self.completion is not None):
            raise ValueError("complete must reflect submit/completion presence")
