import pytest

from mouse_control.trace.models import (
    CaptureSource,
    UrbEventType,
    UsbDirection,
    UsbObservation,
    UsbSetupPacket,
    UsbTransferType,
)


def test_setup_packet_derives_control_direction() -> None:
    assert UsbSetupPacket(0xA1, 1, 2, 3, 4).direction is UsbDirection.IN
    assert UsbSetupPacket(0x21, 1, 2, 3, 4).direction is UsbDirection.OUT


def test_observation_refuses_inconsistent_capture_length() -> None:
    with pytest.raises(ValueError, match="captured_length"):
        UsbObservation(
            capture_id="capture",
            sequence=0,
            timestamp_ns=1,
            source=CaptureSource.SYNTHETIC_TEST,
            bus_id=1,
            device_address=2,
            interface_number=None,
            endpoint=1,
            direction=UsbDirection.IN,
            transfer_type=UsbTransferType.INTERRUPT,
            event_type=UrbEventType.COMPLETE,
            urb_id=3,
            status=0,
            setup=None,
            declared_length=2,
            captured_length=1,
            payload=b"two",
            physical_device_fingerprint="device",
        )
