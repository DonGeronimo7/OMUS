# SPDX-License-Identifier: AGPL-3.0-or-later
from dataclasses import asdict
from mouse_control.hid_descriptor import parse_report_descriptor
from mouse_control.hid_report import decode_input_report
from mouse_control.trace import HidTraceEnrichment

def test_trace_enrichment_links_derived_decode_without_modifying_raw_evidence():
    descriptor=parse_report_descriptor(bytes.fromhex("05 09 09 01 15 00 25 01 75 01 95 01 81 02"))
    decoded=decode_input_report(descriptor,b"\x01")
    enriched=HidTraceEnrichment("capture:1",descriptor.fingerprint,2,"input",0,decoded.values,decoded.diagnostics)
    assert enriched.observation_id=="capture:1"
    assert asdict(enriched)["decoded_fields"][0]["raw_value"]==1
