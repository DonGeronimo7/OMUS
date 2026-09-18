"""Lossless, dependency-free HID report-descriptor schema parser.

This module records descriptor-declared facts. It never infers vendor meaning
and never grants hardware write authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from functools import cached_property, lru_cache
import hashlib
from math import ceil

from .discovery_models import HidReportDefinition


class HidDescriptorError(ValueError):
    pass


class HidDiagnosticSeverity(str, Enum):
    INFO = "info"; WARNING = "warning"; ERROR = "error"; FATAL = "fatal"


@dataclass(frozen=True)
class HidDescriptorDiagnostic:
    severity: HidDiagnosticSeverity
    code: str
    message: str
    offset: int | None = None


class HidCollectionType(IntEnum):
    PHYSICAL = 0; APPLICATION = 1; LOGICAL = 2; REPORT = 3
    NAMED_ARRAY = 4; USAGE_SWITCH = 5; USAGE_MODIFIER = 6


@dataclass(frozen=True)
class HidCollection:
    index: int
    collection_type: int
    usage_page: int | None
    usage: int | None
    parent_index: int | None

    @property
    def known_type(self) -> HidCollectionType | None:
        try: return HidCollectionType(self.collection_type)
        except ValueError: return None


@dataclass(frozen=True)
class HidMainFlags:
    raw: int
    constant: bool
    variable: bool
    relative: bool
    wrap: bool
    non_linear: bool
    no_preferred: bool
    null_state: bool
    volatile: bool
    buffered_bytes: bool

    @classmethod
    def from_raw(cls, raw: int) -> "HidMainFlags":
        return cls(raw, bool(raw&1), bool(raw&2), bool(raw&4), bool(raw&8),
                   bool(raw&0x10), bool(raw&0x20), bool(raw&0x40),
                   bool(raw&0x80), bool(raw&0x100))


@dataclass(frozen=True)
class HidFieldDefinition:
    report_id: int
    report_type: str
    bit_offset: int
    report_size: int
    report_count: int
    flags: int
    usage_pages: tuple[int, ...] = ()
    usages: tuple[tuple[int, int], ...] = ()
    usage_sets: tuple[tuple[tuple[int, int], ...], ...] = ()
    logical_minimum: int | None = None
    logical_maximum: int | None = None
    physical_minimum: int | None = None
    physical_maximum: int | None = None
    unit: int | None = None
    unit_exponent: int | None = None
    usage_minimum: tuple[int, int] | None = None
    usage_maximum: tuple[int, int] | None = None
    designator_index: int | None = None
    designator_minimum: int | None = None
    designator_maximum: int | None = None
    string_index: int | None = None
    string_minimum: int | None = None
    string_maximum: int | None = None
    collection_path: tuple[int, ...] = ()
    application_usage: tuple[int, int] | None = None
    physical_usage: tuple[int, int] | None = None
    logical_usage: tuple[int, int] | None = None
    field_index: int = 0

    @cached_property
    def main_flags(self) -> HidMainFlags: return HidMainFlags.from_raw(self.flags)
    @property
    def bit_length(self) -> int: return self.report_size * self.report_count
    @property
    def wire_bit_offset(self) -> int: return self.bit_offset + (8 if self.report_id else 0)
    @property
    def is_constant(self) -> bool: return self.main_flags.constant
    @property
    def is_variable(self) -> bool: return self.main_flags.variable
    @property
    def is_relative(self) -> bool: return self.main_flags.relative
    @property
    def vendor_defined(self) -> bool: return any(0xFF00 <= p <= 0xFFFF for p in self.usage_pages)
    @property
    def role(self) -> str:
        if self.is_constant: return "padding"
        if self.vendor_defined: return "vendor"
        pages = set(self.usage_pages)
        if 0x09 in pages: return "button"
        if any(p == 1 and u in {0x30,0x31,0x38} for p,u in self.usages): return "pointer"
        if 0x0C in pages: return "consumer"
        return "standard" if pages else "undeclared"
    def stable_id(self, fingerprint: str) -> str:
        return _stable_field_id(self, fingerprint)

    def _calculate_stable_id(self, fingerprint: str) -> str:
        material = repr((fingerprint, self.report_type, self.report_id,
                         self.field_index, self.bit_offset, self.report_size,
                         self.report_count, self.usages, self.collection_path))
        return "HID-F" + hashlib.sha256(material.encode()).hexdigest()[:20].upper()
    def member_stable_id(self, fingerprint: str, member_index: int) -> str:
        """Stable observation identity for one positional field member.

        Variable fields always have positional members.  An opaque
        vendor-defined Array with no selector range is also exposed
        positionally for observation, while retaining its descriptor-declared
        Array flags and parent field identity.
        """
        if not self.has_positional_members or not 0 <= member_index < self.report_count:
            raise ValueError("member index is outside a positional HID field")
        return f"{self.stable_id(fingerprint)}/member-{member_index}"
    @property
    def has_positional_members(self) -> bool:
        return ((self.is_variable and self.report_count > 1) or
                (self.vendor_defined and self.report_count > 1 and
                 self.usage_minimum is None and self.usage_maximum is None))
    def overlaps_wire_byte(self, byte_offset: int) -> bool:
        return (byte_offset >= 0 and self.bit_length > 0 and
                self.wire_bit_offset < (byte_offset+1)*8 and
                byte_offset*8 < self.wire_bit_offset+self.bit_length)


@dataclass(frozen=True)
class ParsedHidDescriptor:
    raw: bytes
    reports: tuple[HidReportDefinition, ...]
    fields: tuple[HidFieldDefinition, ...] = ()
    collections: tuple[HidCollection, ...] = ()
    diagnostics: tuple[HidDescriptorDiagnostic, ...] = ()
    @cached_property
    def fingerprint(self) -> str: return hashlib.sha256(self.raw).hexdigest()
    @cached_property
    def input_reports(self): return get_input_reports(self)
    @cached_property
    def output_reports(self): return get_output_reports(self)
    @cached_property
    def feature_reports(self): return get_feature_reports(self)


@dataclass
class _Global:
    usage_page: int=0; logical_minimum: int|None=None; logical_maximum: int|None=None
    physical_minimum: int|None=None; physical_maximum: int|None=None
    unit_exponent: int|None=None; unit: int|None=None
    report_size: int=0; report_count: int=0; report_id: int=0
    def copy(self): return _Global(**vars(self))


@dataclass
class _Local:
    usages: list[tuple[int,int]]
    alternate_usage_sets: list[list[tuple[int,int]]]
    delimiter_open: bool = False
    alternate_usage_minimum: tuple[int,int]|None = None
    alternate_usage_maximum: tuple[int,int]|None = None
    usage_minimum: tuple[int,int]|None=None; usage_maximum: tuple[int,int]|None=None
    designator_index: int|None=None; designator_minimum: int|None=None; designator_maximum: int|None=None
    string_index: int|None=None; string_minimum: int|None=None; string_maximum: int|None=None
    @classmethod
    def empty(cls): return cls([], [])


def _u(data: bytes) -> int: return int.from_bytes(data,"little") if data else 0
def _s(data: bytes) -> int: return int.from_bytes(data,"little",signed=True) if data else 0
def _usage(value:int,page:int,size:int): return ((value>>16)&0xffff,value&0xffff) if size==4 else (page,value)


@lru_cache(maxsize=4096)
def _stable_field_id(field: HidFieldDefinition, fingerprint: str) -> str:
    return field._calculate_stable_id(fingerprint)


def _expand_range(result, low, high, diagnostics, offset):
    if (low is None)!=(high is None):
        diagnostics.append(HidDescriptorDiagnostic(HidDiagnosticSeverity.WARNING,"incomplete-usage-range","usage range has one bound",offset))
    elif low and high:
        if low[0]!=high[0] or low[1]>high[1]:
            diagnostics.append(HidDescriptorDiagnostic(HidDiagnosticSeverity.ERROR,"invalid-usage-range","usage range is invalid",offset))
        elif high[1]-low[1] <= 4096: result.extend((low[0],i) for i in range(low[1],high[1]+1))
        else:
            diagnostics.append(HidDescriptorDiagnostic(HidDiagnosticSeverity.ERROR,"unbounded-usage-range","usage range is too large",offset)); result.extend((low,high))
    return tuple(dict.fromkeys(result))


def _usage_sets(local:_Local, diagnostics:list[HidDescriptorDiagnostic], offset:int):
    primary = _expand_range(list(local.usages), local.usage_minimum, local.usage_maximum,
                            diagnostics, offset)
    result = [primary]
    for index, alternate in enumerate(local.alternate_usage_sets):
        low = local.alternate_usage_minimum if index == len(local.alternate_usage_sets)-1 else None
        high = local.alternate_usage_maximum if index == len(local.alternate_usage_sets)-1 else None
        result.append(_expand_range(list(alternate), low, high, diagnostics, offset))
    return tuple(result)


def _containing(collections, path, kind):
    for index in reversed(path):
        item=collections[index]
        if item.collection_type==kind and item.usage_page is not None and item.usage is not None:
            return item.usage_page,item.usage
    return None


def parse_report_descriptor(raw: bytes) -> ParsedHidDescriptor:
    if not isinstance(raw,(bytes,bytearray,memoryview)): raise TypeError("raw HID descriptor must be bytes-like")
    return _parse_report_descriptor(bytes(raw))


@lru_cache(maxsize=128)
def _parse_report_descriptor(data: bytes) -> ParsedHidDescriptor:
    state=_Global(); stack=[]; local=_Local.empty(); path=[]
    collections=[]; diagnostics=[]; lengths={}; pages={}; fields=[]; indexes={}; offset=0
    def diag(severity,code,message,where): diagnostics.append(HidDescriptorDiagnostic(severity,code,message,where))
    while offset < len(data):
        where=offset; prefix=data[offset]; offset+=1
        if prefix==0xfe:
            if offset+2>len(data): diag(HidDiagnosticSeverity.FATAL,"truncated-long-header","truncated long-item header",where); break
            size=data[offset]; offset+=2
            if offset+size>len(data): diag(HidDiagnosticSeverity.FATAL,"truncated-long-item","truncated long item",where); break
            diag(HidDiagnosticSeverity.INFO,"unknown-long-item","long item retained in raw descriptor",where); offset+=size; continue
        size=(0,1,2,4)[prefix&3]; item_type=(prefix>>2)&3; tag=(prefix>>4)&15
        if offset+size>len(data): diag(HidDiagnosticSeverity.FATAL,"truncated-short-item","truncated short item",where); break
        payload=data[offset:offset+size]; offset+=size; value=_u(payload)
        if item_type==1:
            if tag==0: state.usage_page=value
            elif tag==1: state.logical_minimum=_s(payload)
            elif tag==2: state.logical_maximum=_s(payload) if (state.logical_minimum or 0)<0 else value
            elif tag==3: state.physical_minimum=_s(payload)
            elif tag==4: state.physical_maximum=_s(payload) if (state.physical_minimum or 0)<0 else value
            elif tag==5:
                nibble=value&15; state.unit_exponent=nibble-16 if nibble&8 else nibble
            elif tag==6: state.unit=value
            elif tag==7: state.report_size=value
            elif tag==8:
                if not 1<=value<=255: diag(HidDiagnosticSeverity.ERROR,"invalid-report-id",f"invalid report ID {value}",where)
                else: state.report_id=value
            elif tag==9: state.report_count=value
            elif tag==10: stack.append(state.copy())
            elif tag==11:
                if stack: state=stack.pop()
                else: diag(HidDiagnosticSeverity.ERROR,"global-pop-underflow","global pop without push",where)
            continue
        if item_type==2:
            split=_usage(value,state.usage_page,size)
            if tag==0:
                (local.alternate_usage_sets[-1] if local.delimiter_open else local.usages).append(split)
            elif tag==1:
                if local.delimiter_open: local.alternate_usage_minimum=split
                else: local.usage_minimum=split
            elif tag==2:
                if local.delimiter_open: local.alternate_usage_maximum=split
                else: local.usage_maximum=split
            elif tag==3: local.designator_index=value
            elif tag==4: local.designator_minimum=value
            elif tag==5: local.designator_maximum=value
            elif tag==7: local.string_index=value
            elif tag==8: local.string_minimum=value
            elif tag==9: local.string_maximum=value
            elif tag==10:
                if value==1:
                    if local.delimiter_open:
                        diag(HidDiagnosticSeverity.ERROR,"nested-delimiter","nested Local Delimiter is invalid",where)
                    else:
                        local.delimiter_open=True; local.alternate_usage_sets.append([])
                elif value==0:
                    if not local.delimiter_open:
                        diag(HidDiagnosticSeverity.ERROR,"delimiter-close-without-open","Local Delimiter close has no open set",where)
                    local.delimiter_open=False
                else:
                    diag(HidDiagnosticSeverity.ERROR,"invalid-delimiter-value",f"invalid Local Delimiter value {value}",where)
            continue
        if item_type==3: diag(HidDiagnosticSeverity.INFO,"reserved-item","reserved item ignored",where); continue
        if tag==10:
            use=local.usages[0] if local.usages else local.usage_minimum; index=len(collections)
            collections.append(HidCollection(index,value,use[0] if use else None,use[1] if use else None,path[-1] if path else None)); path.append(index); local=_Local.empty(); continue
        if tag==12:
            if path: path.pop()
            else: diag(HidDiagnosticSeverity.ERROR,"collection-underflow","end collection without collection",where)
            local=_Local.empty(); continue
        report_type={8:"input",9:"output",11:"feature"}.get(tag)
        if report_type:
            key=(report_type,state.report_id)
            if state.report_size==0: diag(HidDiagnosticSeverity.ERROR,"zero-report-size","Main item has zero report size",where)
            bits=state.report_size*state.report_count
            if state.report_size>65536 or state.report_count>1000000 or bits>8388608:
                diag(HidDiagnosticSeverity.FATAL,"unreasonable-report-size","report field exceeds safe limits",where); local=_Local.empty(); continue
            if state.logical_minimum is not None and state.logical_maximum is not None and state.logical_minimum>state.logical_maximum:
                diag(HidDiagnosticSeverity.ERROR,"invalid-logical-range","logical minimum exceeds maximum",where)
            if local.delimiter_open:
                diag(HidDiagnosticSeverity.ERROR,"unclosed-delimiter","Local Delimiter set was not closed before Main item",where)
            usage_sets=_usage_sets(local,diagnostics,where); uses=usage_sets[0]
            field_pages={state.usage_page,*(p for usage_set in usage_sets for p,_ in usage_set)}; pages.setdefault(key,set()).update(field_pages); field_index=indexes.get(key,0)
            fields.append(HidFieldDefinition(state.report_id,report_type,lengths.get(key,0),state.report_size,state.report_count,value,
                tuple(sorted(field_pages)),uses,usage_sets,state.logical_minimum,state.logical_maximum,state.physical_minimum,state.physical_maximum,
                state.unit,state.unit_exponent,local.usage_minimum,local.usage_maximum,local.designator_index,local.designator_minimum,
                local.designator_maximum,local.string_index,local.string_minimum,local.string_maximum,tuple(path),
                _containing(collections,path,HidCollectionType.APPLICATION),_containing(collections,path,HidCollectionType.PHYSICAL),
                _containing(collections,path,HidCollectionType.LOGICAL),field_index))
            indexes[key]=field_index+1; lengths[key]=lengths.get(key,0)+bits
        local=_Local.empty()
    if path: diag(HidDiagnosticSeverity.ERROR,"unclosed-collection",f"{len(path)} collection(s) not closed",len(data))
    if stack: diag(HidDiagnosticSeverity.WARNING,"unclosed-global-push",f"{len(stack)} push state(s) not popped",len(data))
    order={"input":0,"output":1,"feature":2}; reports=[]
    for (kind,rid),bits in sorted(lengths.items(),key=lambda x:(order[x[0][0]],x[0][1])):
        application_usages = tuple(sorted({
            field.application_usage for field in fields
            if field.report_type == kind and field.report_id == rid
            and field.application_usage is not None
        }))
        reports.append(HidReportDefinition(
            rid, kind, ceil(bits/8)+(1 if rid else 0),
            tuple(sorted(pages[(kind,rid)])), application_usages,
        ))
    return ParsedHidDescriptor(data,tuple(reports),tuple(fields),tuple(collections),tuple(diagnostics))


def enumerate_report_ids(d): return tuple(sorted({r.report_id for r in d.reports}))
def _reports(d,t): return tuple(r for r in d.reports if r.report_type==t)
def get_input_reports(d): return _reports(d,"input")
def get_output_reports(d): return _reports(d,"output")
def get_feature_reports(d): return _reports(d,"feature")
@lru_cache(maxsize=1024)
def _fields_for_report(d, report_type, report_id):
    return tuple(f for f in d.fields if f.report_type==report_type and f.report_id==report_id)
def fields_for_report(d,*,report_type,report_id): return _fields_for_report(d,report_type,report_id)
def fields_overlapping_wire_byte(d,*,report_type,report_id,byte_offset): return tuple(f for f in fields_for_report(d,report_type=report_type,report_id=report_id) if f.overlaps_wire_byte(byte_offset))
def calculate_report_lengths(d,*,report_type=None):
    result={}
    for r in d.reports:
        if report_type is None or r.report_type==report_type: result[r.report_id]=max(result.get(r.report_id,0),r.byte_length)
    return result
def vendor_defined_reports(d): return tuple(r for r in d.reports if any(0xff00<=p<=0xffff for p in r.usage_pages))
