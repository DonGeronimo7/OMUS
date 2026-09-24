# SPDX-License-Identifier: AGPL-3.0-or-later
"""Derived HID interpretation linked to immutable trace observations."""
from dataclasses import dataclass
from ..hid_report import DecodedHidValue
from ..hid_descriptor import HidDescriptorDiagnostic

@dataclass(frozen=True)
class HidTraceEnrichment:
    observation_id:str
    descriptor_fingerprint:str
    interface_number:int|None
    report_type:str|None
    report_id:int|None
    decoded_fields:tuple[DecodedHidValue,...]
    diagnostics:tuple[HidDescriptorDiagnostic,...]=()
