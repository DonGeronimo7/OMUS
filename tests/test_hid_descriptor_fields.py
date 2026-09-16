"""Field-level HID descriptor parsing tests for generic discovery."""

from mouse_control.hid_descriptor import (
    fields_overlapping_wire_byte,
    parse_report_descriptor,
)


DESCRIPTOR = bytes.fromhex(
    "05 01 09 02 A1 01 "
    "85 01 "
    "05 09 19 01 29 03 15 00 25 01 95 03 75 01 81 02 "
    "95 01 75 05 81 01 "
    "05 01 09 30 09 31 15 81 25 7F 75 08 95 02 81 06 "
    "C0 "
    "06 00 FF 85 05 75 08 95 04 B1 02"
)


def test_descriptor_exposes_button_padding_pointer_and_vendor_fields():
    parsed = parse_report_descriptor(DESCRIPTOR)

    input_fields = [field for field in parsed.fields if field.report_type == "input"]
    assert [field.role for field in input_fields] == ["button", "padding", "pointer"]

    buttons, padding, pointer = input_fields
    assert buttons.bit_offset == 0
    assert buttons.bit_length == 3
    assert buttons.usages == ((0x09, 1), (0x09, 2), (0x09, 3))
    assert buttons.logical_minimum == 0
    assert buttons.logical_maximum == 1
    assert not buttons.is_relative

    assert padding.bit_offset == 3
    assert padding.bit_length == 5
    assert padding.is_constant

    assert pointer.bit_offset == 8
    assert pointer.bit_length == 16
    assert pointer.usages == ((0x01, 0x30), (0x01, 0x31))
    assert pointer.logical_minimum == -127
    assert pointer.logical_maximum == 127
    assert pointer.is_relative

    feature = next(field for field in parsed.fields if field.report_type == "feature")
    assert feature.role == "vendor"
    assert feature.vendor_defined
    assert feature.logical_minimum == -127
    assert feature.logical_maximum == 127


def test_wire_byte_overlap_accounts_for_numbered_report_prefix():
    parsed = parse_report_descriptor(DESCRIPTOR)

    # Byte zero is the report ID. The button+padding payload occupies byte one,
    # and X/Y occupy bytes two and three.
    assert fields_overlapping_wire_byte(
        parsed,
        report_type="input",
        report_id=1,
        byte_offset=0,
    ) == ()

    byte_one = fields_overlapping_wire_byte(
        parsed,
        report_type="input",
        report_id=1,
        byte_offset=1,
    )
    assert {field.role for field in byte_one} == {"button", "padding"}

    byte_two = fields_overlapping_wire_byte(
        parsed,
        report_type="input",
        report_id=1,
        byte_offset=2,
    )
    assert tuple(field.role for field in byte_two) == ("pointer",)
