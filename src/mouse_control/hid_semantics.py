"""Specification-derived HID meaning and explicit Linux evdev expectations."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .hid_descriptor import HidFieldDefinition
from .hid_usage import HidUsage, USAGES

class HidSemanticClass(str,Enum):
    POINTER_AXIS="pointer_axis"; WHEEL="wheel"; BUTTON="button"; KEYBOARD="keyboard"
    CONSUMER_CONTROL="consumer_control"; BATTERY="battery"; POWER="power"
    DEVICE_CONTROL="device_control"; VENDOR_DEFINED="vendor_defined"; STANDARD_OTHER="standard_other"; PADDING="padding"

@dataclass(frozen=True)
class HidSemantic:
    semantic_class:HidSemanticClass
    name:str
    usage:HidUsage|None
    evdev_expectation:tuple[int,int]|None=None

@dataclass(frozen=True)
class InterpretedHidField:
    field_id:str
    report_type:str
    report_id:int
    bit_offset:int
    bit_width:int
    semantics:tuple[HidSemantic,...]

# Linux input-event constants kept local to avoid making evdev a parser dependency.
EV_REL=2; EV_KEY=1
_BUTTON_CODES={1:0x110,2:0x111,3:0x112,4:0x113,5:0x114}
_REL_CODES={(1,0x30):0,(1,0x31):1,(1,0x38):8,(0x0C,0x238):6}

def interpret_field(field:HidFieldDefinition, member:int=0) -> HidSemantic:
    if field.is_constant: return HidSemantic(HidSemanticClass.PADDING,"Padding",None)
    use=field.usages[min(member,len(field.usages)-1)] if field.usages else None
    usage=HidUsage(*use) if use else None
    if field.vendor_defined: return HidSemantic(HidSemanticClass.VENDOR_DEFINED,USAGES.lookup(*use).usage_name if use else "Vendor-defined field",usage)
    if use and use[0]==9:
        return HidSemantic(HidSemanticClass.BUTTON,f"Mouse Button {use[1]}",usage,(EV_KEY,_BUTTON_CODES[use[1]]) if use[1] in _BUTTON_CODES else None)
    if use in {(1,0x30),(1,0x31)}: return HidSemantic(HidSemanticClass.POINTER_AXIS,USAGES.lookup(*use).usage_name,usage,(EV_REL,_REL_CODES[use]))
    if use in {(1,0x38),(0x0C,0x238)}: return HidSemantic(HidSemanticClass.WHEEL,USAGES.lookup(*use).usage_name,usage,(EV_REL,_REL_CODES[use]))
    if use and use[0]==7: return HidSemantic(HidSemanticClass.KEYBOARD,USAGES.lookup(*use).usage_name,usage)
    if use and use[0]==0x0C: return HidSemantic(HidSemanticClass.CONSUMER_CONTROL,USAGES.lookup(*use).usage_name,usage)
    if use and use[0]==0x85: return HidSemantic(HidSemanticClass.BATTERY,USAGES.lookup(*use).usage_name,usage)
    if use and use[0]==0x84: return HidSemantic(HidSemanticClass.POWER,USAGES.lookup(*use).usage_name,usage)
    if use and use[0]==6: return HidSemantic(HidSemanticClass.DEVICE_CONTROL,USAGES.lookup(*use).usage_name,usage)
    return HidSemantic(HidSemanticClass.STANDARD_OTHER,USAGES.lookup(*use).usage_name if use else "Undeclared field",usage)

def interpret_descriptor(descriptor):
    """Return a deterministic semantic inventory without behavioral inference."""
    return tuple(
        InterpretedHidField(
            field.stable_id(descriptor.fingerprint), field.report_type,
            field.report_id, field.bit_offset, field.bit_length,
            tuple(interpret_field(field,index) for index in range(max(1,field.report_count))),
        )
        for field in descriptor.fields
    )

@dataclass(frozen=True)
class EvdevCorrelation:
    field_id:str; expected_event:tuple[int,int]|None; observed_event:tuple[int,int]|None; confirmed:bool

def correlate_evdev(field_id:str, semantic:HidSemantic, observed_events) -> EvdevCorrelation:
    observed={(e.event_type,e.code) for e in observed_events}
    match=semantic.evdev_expectation if semantic.evdev_expectation in observed else None
    return EvdevCorrelation(field_id,semantic.evdev_expectation,match,match is not None)
