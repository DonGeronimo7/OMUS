# SPDX-License-Identifier: AGPL-3.0-or-later
"""Specification-derived HID meaning and explicit Linux evdev expectations."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .hid_descriptor import HidFieldDefinition
from .hid_usage import HidUsage, USAGES

class HidSemanticClass(str,Enum):
    POINTER_AXIS="pointer_axis"; WHEEL="wheel"; BUTTON="button"; KEYBOARD="keyboard"
    CONSUMER_CONTROL="consumer_control"; BATTERY="battery"; POWER="power"
    DEVICE_CONTROL="device_control"; DIGITIZER="digitizer"; SENSOR="sensor"
    HAPTIC="haptic"; VENDOR_DEFINED="vendor_defined"; STANDARD_OTHER="standard_other"; PADDING="padding"

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
    collection_roles:tuple[str,...]=()

# Linux input-event constants kept local to avoid making evdev a parser dependency.
EV_KEY=1; EV_REL=2; EV_ABS=3
_BUTTON_CODES={1:0x110,2:0x111,3:0x112,4:0x113,5:0x114,6:0x115,7:0x116,8:0x117}
_REL_CODES={(1,0x30):0,(1,0x31):1,(1,0x32):2,(1,0x33):3,(1,0x34):4,
            (1,0x35):5,(1,0x36):6,(1,0x37):7,(1,0x38):8,(0x0C,0x238):6}
_CONSUMER_CODES={(0x0C,0xE2):113,(0x0C,0xE9):115,(0x0C,0xEA):114,
                 (0x0C,0xB5):163,(0x0C,0xB6):165,(0x0C,0xCD):164,
                 (0x0C,0x223):172,(0x0C,0x224):158,(0x0C,0x225):159}
_APPLICATION_NAMES={(1,1):"pointer",(1,2):"mouse",(1,6):"keyboard",
                    (1,7):"keypad",(0x0C,1):"consumer-control"}

def interpret_field(field:HidFieldDefinition, member:int=0) -> HidSemantic:
    if field.is_constant: return HidSemantic(HidSemanticClass.PADDING,"Padding",None)
    use=field.usages[min(member,len(field.usages)-1)] if field.usages else None
    usage=HidUsage(*use) if use else None
    if field.vendor_defined: return HidSemantic(HidSemanticClass.VENDOR_DEFINED,USAGES.lookup(*use).usage_name if use else "Vendor-defined field",usage)
    if use and use[0]==9:
        return HidSemantic(HidSemanticClass.BUTTON,f"Mouse Button {use[1]}",usage,(EV_KEY,_BUTTON_CODES[use[1]]) if use[1] in _BUTTON_CODES else None)
    if use in _REL_CODES and use not in {(1,0x38),(0x0C,0x238)}:
        event_type=EV_REL if field.is_relative else EV_ABS
        return HidSemantic(HidSemanticClass.POINTER_AXIS,USAGES.lookup(*use).usage_name,usage,(event_type,_REL_CODES[use]))
    if use in {(1,0x38),(0x0C,0x238)}: return HidSemantic(HidSemanticClass.WHEEL,USAGES.lookup(*use).usage_name,usage,(EV_REL,_REL_CODES[use]))
    if use and use[0]==7: return HidSemantic(HidSemanticClass.KEYBOARD,USAGES.lookup(*use).usage_name,usage)
    if use and use[0]==0x0C: return HidSemantic(HidSemanticClass.CONSUMER_CONTROL,USAGES.lookup(*use).usage_name,usage,(EV_KEY,_CONSUMER_CODES[use]) if use in _CONSUMER_CODES else None)
    if use and use[0]==0x85: return HidSemantic(HidSemanticClass.BATTERY,USAGES.lookup(*use).usage_name,usage)
    if use and use[0]==0x84: return HidSemantic(HidSemanticClass.POWER,USAGES.lookup(*use).usage_name,usage)
    if use and use[0]==6: return HidSemantic(HidSemanticClass.DEVICE_CONTROL,USAGES.lookup(*use).usage_name,usage)
    if use and use[0]==0x0D: return HidSemantic(HidSemanticClass.DIGITIZER,USAGES.lookup(*use).usage_name,usage)
    if use and use[0]==0x20: return HidSemantic(HidSemanticClass.SENSOR,USAGES.lookup(*use).usage_name,usage)
    if use and use[0]==0x0E: return HidSemantic(HidSemanticClass.HAPTIC,USAGES.lookup(*use).usage_name,usage)
    return HidSemantic(HidSemanticClass.STANDARD_OTHER,USAGES.lookup(*use).usage_name if use else "Undeclared field",usage)

def interpret_descriptor(descriptor):
    """Return a deterministic semantic inventory without behavioral inference."""
    return tuple(
        InterpretedHidField(
            field.stable_id(descriptor.fingerprint), field.report_type,
            field.report_id, field.bit_offset, field.bit_length,
            tuple(interpret_field(field,index) for index in range(max(1,field.report_count))),
            tuple(filter(None, (
                _APPLICATION_NAMES.get(field.application_usage, "vendor-application" if field.application_usage and field.application_usage[0] >= 0xFF00 else "standard-application" if field.application_usage else None),
                "physical" if field.physical_usage else None,
                "logical" if field.logical_usage else None,
            ))),
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
