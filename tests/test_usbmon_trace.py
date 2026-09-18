from pathlib import Path
import struct

import pytest

from mouse_control.discovery_models import PhysicalDevice
from mouse_control.trace.models import CompletenessStatus, UrbEventType, UsbDirection, UsbTransferType
from mouse_control.trace.usbmon import (
    MAX_CAPTURE_BYTES,
    USBMON_HEADER_SIZE,
    UsbmonCaptureProvider,
    UsbmonDeviceSelection,
    UsbmonError,
    normalize_usbmon_record,
    parse_usbmon_record,
    selection_from_physical_device,
)


HEADER = struct.Struct("=QBBBBHccqiiII8siiII")


def record_bytes(
    *,
    urb_id: int = 0x1234,
    event: bytes = b"S",
    transfer: int = 2,
    endpoint: int = 0,
    device: int = 7,
    bus: int = 3,
    setup_flag: bytes = b"\x00",
    setup: bytes = b"\x21\x09\x05\x03\x01\x00\x04\x00",
    payload: bytes = b"data",
    declared_length: int | None = None,
    data_flag: bytes = b"\x00",
    interval: int = 0,
    start_frame: int = 0,
    transfer_flags: int = 0,
    descriptor_count: int = 0,
) -> tuple[bytes, bytes]:
    header = HEADER.pack(
        urb_id, event[0], transfer, endpoint, device, bus,
        setup_flag, data_flag, 10, 250, 0,
        len(payload) if declared_length is None else declared_length,
        len(payload), setup, interval, start_frame, transfer_flags, descriptor_count,
    )
    assert len(header) == USBMON_HEADER_SIZE
    return header, payload


def test_binary_usbmon_control_record_preserves_setup_transport_and_payload() -> None:
    header, payload = record_bytes()
    raw = parse_usbmon_record(header, payload)
    observation = normalize_usbmon_record(
        raw,
        capture_id="capture",
        sequence=4,
        selection=UsbmonDeviceSelection(3, 7, "fingerprint", (1,)),
    )

    assert observation is not None
    assert observation.event_type is UrbEventType.SUBMIT
    assert observation.transfer_type is UsbTransferType.CONTROL
    assert observation.direction is UsbDirection.OUT
    assert observation.interface_number == 1
    assert observation.setup is not None
    assert observation.setup.request == 9
    assert observation.setup.value == 0x0305
    assert observation.payload == b"data"
    assert observation.timestamp_ns == 10_000_250_000


def test_binary_usbmon_nonzero_extended_metadata_and_truncation_survive_normalization() -> None:
    header, payload = record_bytes(
        setup_flag=b"\x01", data_flag=b"\x02", payload=b"ab",
        declared_length=9, interval=7, start_frame=123,
        transfer_flags=0xA0000011, descriptor_count=4,
    )
    observation = normalize_usbmon_record(
        parse_usbmon_record(header, payload), capture_id="capture", sequence=0,
        selection=UsbmonDeviceSelection(3, 7, "fingerprint"),
    )

    assert observation is not None
    assert (observation.setup_flag, observation.data_flag) == (1, 2)
    assert (observation.interval, observation.start_frame) == (7, 123)
    assert observation.transfer_flags == 0xA0000011
    assert observation.descriptor_count == 4
    assert observation.capture_quality is not None
    assert observation.capture_quality.full_binary_header_available is True
    assert observation.capture_quality.completeness is CompletenessStatus.TRUNCATED


def test_binary_usbmon_filter_rejects_unselected_device() -> None:
    header, payload = record_bytes(device=8)
    assert normalize_usbmon_record(
        parse_usbmon_record(header, payload),
        capture_id="capture",
        sequence=0,
        selection=UsbmonDeviceSelection(3, 7, "fingerprint"),
    ) is None


def test_parser_rejects_truncated_and_oversized_records() -> None:
    with pytest.raises(UsbmonError, match="64 bytes"):
        parse_usbmon_record(b"short", b"")
    header, payload = record_bytes(payload=b"abc")
    with pytest.raises(UsbmonError, match="does not match"):
        parse_usbmon_record(header, payload[:-1])
    values = list(HEADER.unpack(header))
    values[12] = MAX_CAPTURE_BYTES + 1
    with pytest.raises(UsbmonError, match="safety limit"):
        parse_usbmon_record(HEADER.pack(*values), b"")


class Reader:
    def __init__(self, records: list[tuple[bytes, bytes]]) -> None:
        self.records = iter(records)
        self.closed = False

    def read_record(self, maximum_payload: int) -> tuple[bytes, bytes]:
        return next(self.records)

    def close(self) -> None:
        self.closed = True


def test_provider_counts_only_selected_device_events() -> None:
    reader = Reader([record_bytes(device=8), record_bytes(device=7)])
    observations = tuple(UsbmonCaptureProvider().capture(
        UsbmonDeviceSelection(3, 7, "fingerprint"),
        capture_id="capture",
        limit=1,
        reader=reader,
    ))
    assert len(observations) == 1
    assert observations[0].sequence == 1
    assert not reader.closed  # injected readers are caller-owned


def test_physical_selection_reresolves_live_bus_address_and_refuses_ambiguity(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "3-2"
    parent.mkdir()
    (parent / "busnum").write_text("3\n")
    (parent / "devnum").write_text("11\n")
    device = PhysicalDevice(
        name="mouse", vendor_id=1, product_id=2, bus=3, parent_path=parent,
        model_fingerprint="model", instance_fingerprint="instance",
    )
    selection = selection_from_physical_device(device)
    assert (selection.bus_id, selection.device_address) == (3, 11)
    assert selection.physical_device_fingerprint == "instance"

    device.ambiguous = True
    with pytest.raises(UsbmonError, match="ambiguous"):
        selection_from_physical_device(device)
