"""Golden coverage for descriptor schema, bit decoding and HID semantics."""
import pytest
from mouse_control.hid_descriptor import parse_report_descriptor, HidCollectionType
from mouse_control.hid_report import decode_input_report, extract_bits
from mouse_control.hid_semantics import HidSemanticClass, interpret_field, correlate_evdev
from mouse_control.hid_behavior import profile_reports, HidBehaviorClass
from mouse_control.event_correlation import TimedEvdevEvent
from mouse_control.event_correlation import TimedReport, decode_timed_reports, detect_decoded_field_changes

# Mouse application -> Pointer physical; five buttons, padding, X/Y/wheel.
MOUSE = bytes.fromhex(
 "05 01 09 02 A1 01 09 01 A1 00 05 09 19 01 29 05 15 00 25 01 "
 "95 05 75 01 81 02 95 01 75 03 81 01 05 01 09 30 09 31 09 38 "
 "15 81 25 7F 75 08 95 03 81 06 C0 C0")

def test_collection_schema_and_standard_mouse_interpretation():
    parsed=parse_report_descriptor(MOUSE)
    assert [c.known_type for c in parsed.collections]==[HidCollectionType.APPLICATION,HidCollectionType.PHYSICAL]
    buttons,x_y_wheel=[f for f in parsed.fields if not f.is_constant]
    assert buttons.application_usage==(1,2) and buttons.physical_usage==(1,1)
    assert interpret_field(buttons,3).semantic_class is HidSemanticClass.BUTTON
    assert interpret_field(x_y_wheel,0).semantic_class is HidSemanticClass.POINTER_AXIS
    assert interpret_field(x_y_wheel,2).semantic_class is HidSemanticClass.WHEEL

def test_numberless_variable_report_decodes_members_and_signed_values():
    parsed=parse_report_descriptor(MOUSE)
    report=decode_input_report(parsed,bytes([0b10001,0xFE,0x05,0xFF]))
    assert [v.logical_value for v in report.values]==[1,0,0,0,1,-2,5,-1]
    assert [v.usage.usage for v in report.values[:5]]==[1,2,3,4,5]

# Two signed, non-byte-aligned 12-bit axes in numbered report 2.
NON_ALIGNED=bytes.fromhex("05 01 09 02 A1 01 85 02 09 30 09 31 16 00 F8 26 FF 07 75 0C 95 02 81 06 C0")

def test_non_byte_aligned_signed_12_bit_numbered_report():
    parsed=parse_report_descriptor(NON_ALIGNED)
    # -31 = 0xfe1; +7 = 0x007, packed little-endian into 24 bits.
    decoded=decode_input_report(parsed,b"\x02\xe1\x7f\x00")
    assert [v.logical_value for v in decoded.values]==[-31,7]
    assert extract_bits(decoded.raw[1:],12,12)==7

# Keyboard array with usage range 0..101 and six selectors.
ARRAY=bytes.fromhex("05 01 09 06 A1 01 05 07 19 00 29 65 15 00 25 65 75 08 95 06 81 00 C0")

def test_array_selectors_decode_as_active_usages_and_keep_empty_entries():
    decoded=decode_input_report(parse_report_descriptor(ARRAY),b"\x04\x05\x00\x00\x00\x00")
    assert [v.usage.usage if v.usage else None for v in decoded.values]==[4,5,None,None,None,None]
    assert [v.array_index for v in decoded.values]==list(range(6))

def test_descriptor_preserves_physical_unit_designator_string_and_flags():
    raw=bytes.fromhex("05 01 09 02 A1 01 09 30 15 00 25 64 35 00 45 0A 55 0F 65 11 39 02 79 03 75 08 95 01 81 FE C0")
    field=parse_report_descriptor(raw).fields[0]
    assert (field.physical_minimum,field.physical_maximum,field.unit_exponent,field.unit)==(0,10,-1,0x11)
    assert (field.designator_index,field.string_index)==(2,3)
    flags=field.main_flags
    assert flags.variable and flags.relative and flags.wrap and flags.non_linear and flags.no_preferred and flags.null_state and flags.volatile

def test_diagnostics_are_retained_without_mutating_raw_descriptor():
    raw=bytes.fromhex("05 01 A1 01 75 00 95 01 81 02")
    parsed=parse_report_descriptor(raw)
    assert parsed.raw==raw
    assert {d.code for d in parsed.diagnostics}=={"zero-report-size","unclosed-collection"}

def test_vendor_field_has_stable_identity_and_behavior_profile():
    raw=bytes.fromhex("06 00 FF 09 23 A1 01 15 00 25 07 75 03 95 01 81 02 C0")
    parsed=parse_report_descriptor(raw)
    reports=[decode_input_report(parsed,bytes([v])) for v in (0,1,0,0,1,0)]
    field=parsed.fields[0]
    assert interpret_field(field).semantic_class is HidSemanticClass.VENDOR_DEFINED
    assert field.stable_id(parsed.fingerprint)==field.stable_id(parsed.fingerprint)
    behavior=next(iter(profile_reports(reports).values()))
    assert behavior.classification is HidBehaviorClass.MOMENTARY
    assert "values=(0, 1)" in behavior.explanation()

def test_evdev_mapping_separates_spec_expectation_from_observation():
    field=parse_report_descriptor(MOUSE).fields[0]
    semantic=interpret_field(field,3)
    event=TimedEvdevEvent(1,"event",1,0x113,1)
    relation=correlate_evdev(field.stable_id("fixture"),semantic,[event])
    assert relation.expected_event==(1,0x113) and relation.confirmed

def test_decoder_rejects_unknown_ids_and_bounds_short_reports():
    parsed=parse_report_descriptor(NON_ALIGNED)
    with pytest.raises(ValueError,match="unknown input report ID"): decode_input_report(parsed,b"\x03\x00")
    short=decode_input_report(parsed,b"\x02\x00")
    assert [d.code for d in short.diagnostics]==["short-input-report"]

def test_field_level_action_correlation_uses_stable_descriptor_identity():
    parsed=parse_report_descriptor(bytes.fromhex("06 00 FF 09 23 15 00 25 07 75 03 95 01 81 02"))
    reports=[TimedReport(i,"stable-interface",bytes([v])) for i,v in enumerate((0,1,0,0,1,0))]
    decoded=decode_timed_reports(reports,{"stable-interface":parsed})
    candidates=detect_decoded_field_changes((decoded[:3],decoded[3:]),minimum_observations=2)
    assert len(candidates)==1
    assert candidates[0].field_id.startswith("HID-F")
    assert candidates[0].values==(0,1)
