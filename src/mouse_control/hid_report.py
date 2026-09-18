"""Canonical bounded descriptor-backed HID report decoder."""
from __future__ import annotations

from dataclasses import dataclass

from .hid_descriptor import (
    HidDescriptorDiagnostic, HidDiagnosticSeverity, HidFieldDefinition,
    ParsedHidDescriptor, fields_for_report,
)
from .hid_usage import HidUsage, HidUsageInfo, USAGES


@dataclass(frozen=True)
class HidPhysicalValue:
    value: float
    unit_system: str
    dimensions: tuple[tuple[str, int], ...]
    exponent: int


@dataclass(frozen=True)
class DecodedHidValue:
    field_id: str
    parent_field_id: str
    usage: HidUsage | None
    raw_value: int
    logical_value: int | None
    array_index: int | None
    member_index: int | None
    relative: bool
    changed: bool | None = None
    wire_bit_offset: int = 0
    wire_byte_offset: int = 0
    bit_width: int = 0
    usage_info: HidUsageInfo | None = None
    collection_path: tuple[int, ...] = ()
    application_usage: HidUsage | None = None
    physical_usage: HidUsage | None = None
    logical_usage: HidUsage | None = None
    vendor_defined: bool = False
    null_selection: bool = False
    raw_bytes: bytes | None = None
    physical_value: HidPhysicalValue | None = None


@dataclass(frozen=True)
class DecodedHidReport:
    report_id: int
    report_type: str
    raw: bytes
    values: tuple[DecodedHidValue, ...]
    diagnostics: tuple[HidDescriptorDiagnostic, ...] = ()


def extract_bits(data: bytes, bit_offset: int, width: int) -> int:
    if bit_offset < 0 or width < 0 or width > 65536:
        raise ValueError("unsafe bit extraction")
    if bit_offset + width > len(data) * 8:
        raise ValueError("report is shorter than declared field")
    value = 0
    for index in range(width):
        value |= ((data[(bit_offset + index) // 8] >> ((bit_offset + index) % 8)) & 1) << index
    return value


def _signed(value: int, width: int) -> int:
    return value - (1 << width) if width and value & (1 << (width - 1)) else value


def _signed_nibble(value: int) -> int:
    value &= 0xF
    return value - 16 if value & 0x8 else value


def _unit(field: HidFieldDefinition, logical: int | None) -> HidPhysicalValue | None:
    if logical is None or field.unit in (None, 0):
        return None
    if None in (field.logical_minimum, field.logical_maximum,
                field.physical_minimum, field.physical_maximum):
        return None
    logical_span = field.logical_maximum - field.logical_minimum
    if logical_span <= 0:
        return None
    physical = field.physical_minimum + (
        (logical - field.logical_minimum)
        * (field.physical_maximum - field.physical_minimum) / logical_span
    )
    exponent = field.unit_exponent or 0
    physical *= 10 ** exponent
    systems = {1: "si-linear", 2: "si-rotation", 3: "english-linear", 4: "english-rotation"}
    system = systems.get(field.unit & 0xF)
    if system is None:
        return None
    names = ("length", "mass", "time", "temperature", "current", "luminous_intensity")
    dimensions = tuple(
        (name, power)
        for name, shift in zip(names, (4, 8, 12, 16, 20, 24))
        if (power := _signed_nibble(field.unit >> shift))
    )
    return HidPhysicalValue(float(physical), system, dimensions, exponent)


def _usage(value: tuple[int, int] | None) -> HidUsage | None:
    return HidUsage(*value) if value else None


def _array_usage(field: HidFieldDefinition, logical: int) -> tuple[HidUsage | None, bool]:
    minimum, maximum = field.usage_minimum, field.usage_maximum
    logical_minimum, logical_maximum = field.logical_minimum, field.logical_maximum
    outside = (
        logical_minimum is not None and logical < logical_minimum
        or logical_maximum is not None and logical > logical_maximum
    )
    if field.main_flags.null_state and outside:
        return None, True
    if minimum and maximum and minimum[0] == maximum[0]:
        # Selector zero is the HID "no event/none selected" value when the
        # declared range begins at Undefined (usage 0).
        if logical == 0 and minimum[1] == 0:
            return None, False
        base = logical_minimum if logical_minimum is not None else minimum[1]
        candidate = minimum[1] + logical - base
        if minimum[1] <= candidate <= maximum[1]:
            return HidUsage(minimum[0], candidate), False
    return None, outside


def decode_report(
    descriptor: ParsedHidDescriptor,
    raw_report: bytes,
    *,
    report_type: str,
    previous: DecodedHidReport | None = None,
) -> DecodedHidReport:
    """Decode an Input, Output, or Feature report through one schema path."""
    if report_type not in {"input", "output", "feature"}:
        raise ValueError(f"unsupported HID report type {report_type!r}")
    raw = bytes(raw_report)
    reports = tuple(report for report in descriptor.reports if report.report_type == report_type)
    numbered = any(report.report_id for report in reports)
    if not raw and numbered:
        raise ValueError("numbered report has no report ID")
    report_id = raw[0] if numbered else 0
    payload = raw[1:] if numbered else raw
    definitions = fields_for_report(descriptor, report_type=report_type, report_id=report_id)
    if not definitions:
        raise ValueError(f"unknown {report_type} report ID {report_id}")
    expected = max((field.bit_offset + field.bit_length for field in definitions), default=0)
    diagnostics: list[HidDescriptorDiagnostic] = []
    if len(payload) * 8 < expected:
        diagnostics.append(HidDescriptorDiagnostic(
            HidDiagnosticSeverity.ERROR, f"short-{report_type}-report",
            f"declared {expected} bits, observed {len(payload) * 8}", None))
    elif len(payload) * 8 >= expected + 8:
        diagnostics.append(HidDescriptorDiagnostic(
            HidDiagnosticSeverity.WARNING, f"long-{report_type}-report",
            f"declared {expected} bits, observed {len(payload) * 8}", None))
    prior = {(value.field_id, value.array_index): value.logical_value for value in previous.values} if previous else {}
    values: list[DecodedHidValue] = []
    for field in definitions:
        if field.is_constant:
            continue
        parent_identity = field.stable_id(descriptor.fingerprint)
        if field.main_flags.buffered_bytes:
            if field.bit_offset % 8 or field.bit_length % 8:
                diagnostics.append(HidDescriptorDiagnostic(
                    HidDiagnosticSeverity.ERROR, "unaligned-buffered-bytes",
                    "Buffered Bytes field is not byte aligned", None))
                continue
            start, end = field.bit_offset // 8, (field.bit_offset + field.bit_length) // 8
            if end > len(payload):
                continue
            blob = payload[start:end]
            values.append(DecodedHidValue(
                parent_identity, parent_identity, _usage(field.usages[0] if field.usages else None),
                int.from_bytes(blob, "little"), None, None, None, field.is_relative,
                None if previous is None else prior.get((parent_identity, None)) is not None,
                field.wire_bit_offset, field.wire_bit_offset // 8, field.bit_length,
                USAGES.lookup(*field.usages[0]) if field.usages else None,
                field.collection_path, _usage(field.application_usage), _usage(field.physical_usage),
                _usage(field.logical_usage), field.vendor_defined, False, blob, None,
            ))
            continue
        for member in range(field.report_count):
            start = field.bit_offset + member * field.report_size
            if start + field.report_size > len(payload) * 8:
                continue
            raw_value = extract_bits(payload, start, field.report_size)
            logical = _signed(raw_value, field.report_size) if (field.logical_minimum or 0) < 0 else raw_value
            if field.is_variable:
                positional = field.has_positional_members
                identity = field.member_stable_id(descriptor.fingerprint, member) if positional else parent_identity
                selected = field.usages[min(member, len(field.usages) - 1)] if field.usages else None
                usage, null_selection, array_index = _usage(selected), False, None
                member_index = member if positional else None
            else:
                positional = field.has_positional_members
                identity = field.member_stable_id(descriptor.fingerprint, member) if positional else parent_identity
                usage, null_selection = _array_usage(field, logical)
                array_index, member_index = member, member if positional else None
            changed = None if previous is None else prior.get((identity, array_index)) != logical
            wire_bit = start + (8 if report_id else 0)
            values.append(DecodedHidValue(
                identity, parent_identity, usage, raw_value, logical, array_index, member_index,
                field.is_relative, changed, wire_bit, wire_bit // 8, field.report_size,
                USAGES.lookup(usage.page, usage.usage) if usage else None,
                field.collection_path, _usage(field.application_usage), _usage(field.physical_usage),
                _usage(field.logical_usage), field.vendor_defined, null_selection, None,
                _unit(field, logical),
            ))
    return DecodedHidReport(report_id, report_type, raw, tuple(values), tuple(diagnostics))


def decode_input_report(descriptor, raw_report, *, previous=None) -> DecodedHidReport:
    return decode_report(descriptor, raw_report, report_type="input", previous=previous)


def decode_output_report(descriptor, raw_report, *, previous=None) -> DecodedHidReport:
    return decode_report(descriptor, raw_report, report_type="output", previous=previous)


def decode_feature_report(descriptor, raw_report, *, previous=None) -> DecodedHidReport:
    return decode_report(descriptor, raw_report, report_type="feature", previous=previous)
