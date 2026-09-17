"""Property-oriented bounded parser/decoder safety cases."""
from mouse_control.hid_descriptor import parse_report_descriptor

def test_every_truncation_of_descriptor_is_bounded_and_deterministic():
    raw=bytes.fromhex("05 01 09 02 A1 01 85 01 05 09 19 01 29 05 75 01 95 05 81 02 C0")
    for length in range(len(raw)+1):
        left=parse_report_descriptor(raw[:length]); right=parse_report_descriptor(raw[:length])
        assert left==right

def test_bad_pop_huge_count_and_reserved_item_become_diagnostics():
    bad_pop=parse_report_descriptor(bytes.fromhex("B4"))
    assert bad_pop.diagnostics[0].code=="global-pop-underflow"
    huge=parse_report_descriptor(bytes.fromhex("75 20 97 FF FF FF FF 81 02"))
    assert any(d.code=="unreasonable-report-size" for d in huge.diagnostics)
    reserved=parse_report_descriptor(bytes.fromhex("0C"))
    assert reserved.diagnostics[0].code=="reserved-item"
