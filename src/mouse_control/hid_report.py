"""Bounded bit-level HID report decoding."""
from __future__ import annotations
from dataclasses import dataclass
from .hid_descriptor import ParsedHidDescriptor, HidDescriptorDiagnostic, HidDiagnosticSeverity, fields_for_report
from .hid_usage import HidUsage

@dataclass(frozen=True)
class DecodedHidValue:
    field_id: str
    usage: HidUsage|None
    raw_value: int
    logical_value: int|None
    array_index: int|None
    relative: bool
    changed: bool|None = None

@dataclass(frozen=True)
class DecodedHidReport:
    report_id: int
    report_type: str
    raw: bytes
    values: tuple[DecodedHidValue,...]
    diagnostics: tuple[HidDescriptorDiagnostic,...]=()

def extract_bits(data:bytes, bit_offset:int, width:int) -> int:
    if bit_offset<0 or width<0 or width>65536: raise ValueError("unsafe bit extraction")
    if bit_offset+width>len(data)*8: raise ValueError("report is shorter than declared field")
    value=0
    for index in range(width): value |= ((data[(bit_offset+index)//8] >> ((bit_offset+index)%8))&1)<<index
    return value

def _signed(value:int,width:int) -> int:
    return value-(1<<width) if width and value&(1<<(width-1)) else value

def decode_input_report(descriptor:ParsedHidDescriptor, raw_report:bytes, *, previous:DecodedHidReport|None=None) -> DecodedHidReport:
    raw=bytes(raw_report); numbered=any(r.report_id for r in descriptor.input_reports)
    if not raw and numbered: raise ValueError("numbered report has no report ID")
    report_id=raw[0] if numbered else 0; payload=raw[1:] if numbered else raw
    definitions=fields_for_report(descriptor,report_type="input",report_id=report_id)
    if not definitions: raise ValueError(f"unknown input report ID {report_id}")
    expected=max((f.bit_offset+f.bit_length for f in definitions),default=0)
    diagnostics=[]
    if len(payload)*8<expected:
        diagnostics.append(HidDescriptorDiagnostic(HidDiagnosticSeverity.ERROR,"short-input-report",f"declared {expected} bits, observed {len(payload)*8}",None))
    elif len(payload)*8>=expected+8:
        diagnostics.append(HidDescriptorDiagnostic(HidDiagnosticSeverity.WARNING,"long-input-report",f"declared {expected} bits, observed {len(payload)*8}",None))
    prior={(v.field_id,v.array_index):v.logical_value for v in previous.values} if previous else {}
    values=[]
    for field in definitions:
        if field.is_constant: continue
        for member in range(field.report_count):
            start=field.bit_offset+member*field.report_size
            if start+field.report_size>len(payload)*8: continue
            raw_value=extract_bits(payload,start,field.report_size)
            logical=_signed(raw_value,field.report_size) if (field.logical_minimum or 0)<0 else raw_value
            identity=field.stable_id(descriptor.fingerprint)
            if field.is_variable:
                use=field.usages[min(member,len(field.usages)-1)] if field.usages else None
                usage=HidUsage(*use) if use else None; array_index=None
            else:
                usage=None; array_index=member
                if raw_value and field.usage_minimum and field.usage_maximum and field.usage_minimum[0]==field.usage_maximum[0]:
                    candidate=field.usage_minimum[1]+raw_value-(field.logical_minimum or 0)
                    if field.usage_minimum[1]<=candidate<=field.usage_maximum[1]: usage=HidUsage(field.usage_minimum[0],candidate)
                if field.main_flags.null_state and (logical < (field.logical_minimum or logical) or logical > (field.logical_maximum or logical)): usage=None
            changed=None if previous is None else prior.get((identity,array_index))!=logical
            values.append(DecodedHidValue(identity,usage,raw_value,logical,array_index,field.is_relative,changed))
    return DecodedHidReport(report_id,"input",raw,tuple(values),tuple(diagnostics))
