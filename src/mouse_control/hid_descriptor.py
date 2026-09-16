"""Dependency-free HID report-descriptor parser used by discovery.

Discovery needs more than report lengths: Linux exposes a descriptor that maps
wire bits to HID usages, logical ranges and Main-item flags.  We keep that
structure protocol-neutral so guided learning can tell ordinary pointer/button
traffic from vendor-defined or undeclared bytes without assigning vendor
semantics such as DPI or polling rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from .discovery_models import HidReportDefinition


class HidDescriptorError(ValueError):
    """The HID report descriptor is malformed or truncated."""


@dataclass(frozen=True)
class HidFieldDefinition:
    """One descriptor Main item mapped onto its report bit range.

    ``bit_offset`` is relative to the report payload and therefore excludes the
    report-ID prefix. ``wire_bit_offset`` includes that prefix when a numbered
    report is used, matching byte offsets observed directly through hidraw.
    """

    report_id: int
    report_type: str
    bit_offset: int
    report_size: int
    report_count: int
    flags: int
    usage_pages: tuple[int, ...] = ()
    usages: tuple[tuple[int, int], ...] = ()
    logical_minimum: int | None = None
    logical_maximum: int | None = None

    @property
    def bit_length(self) -> int:
        return self.report_size * self.report_count

    @property
    def wire_bit_offset(self) -> int:
        return self.bit_offset + (8 if self.report_id else 0)

    @property
    def is_constant(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def is_variable(self) -> bool:
        return bool(self.flags & 0x02)

    @property
    def is_relative(self) -> bool:
        return bool(self.flags & 0x04)

    @property
    def vendor_defined(self) -> bool:
        return any(0xFF00 <= page <= 0xFFFF for page in self.usage_pages)

    @property
    def role(self) -> str:
        """Return a conservative structural role, never a vendor semantic."""

        if self.is_constant:
            return "padding"
        if self.vendor_defined:
            return "vendor"
        pages = set(self.usage_pages)
        usages = set(self.usages)
        if 0x09 in pages:
            return "button"
        if any(page == 0x01 and usage in {0x30, 0x31, 0x38} for page, usage in usages):
            return "pointer"
        if 0x0C in pages:
            return "consumer"
        if pages:
            return "standard"
        return "undeclared"

    def overlaps_wire_byte(self, byte_offset: int) -> bool:
        if byte_offset < 0 or self.bit_length <= 0:
            return False
        byte_start = byte_offset * 8
        byte_end = byte_start + 8
        field_start = self.wire_bit_offset
        field_end = field_start + self.bit_length
        return field_start < byte_end and byte_start < field_end


@dataclass(frozen=True)
class ParsedHidDescriptor:
    raw: bytes
    reports: tuple[HidReportDefinition, ...]
    fields: tuple[HidFieldDefinition, ...] = ()

    @property
    def input_reports(self) -> tuple[HidReportDefinition, ...]:
        return get_input_reports(self)

    @property
    def output_reports(self) -> tuple[HidReportDefinition, ...]:
        return get_output_reports(self)

    @property
    def feature_reports(self) -> tuple[HidReportDefinition, ...]:
        return get_feature_reports(self)


@dataclass
class _GlobalState:
    usage_page: int = 0
    logical_minimum: int | None = None
    logical_maximum: int | None = None
    report_size: int = 0
    report_count: int = 0
    report_id: int = 0

    def copy(self) -> "_GlobalState":
        return _GlobalState(
            usage_page=self.usage_page,
            logical_minimum=self.logical_minimum,
            logical_maximum=self.logical_maximum,
            report_size=self.report_size,
            report_count=self.report_count,
            report_id=self.report_id,
        )


def _unsigned(payload: bytes) -> int:
    return int.from_bytes(payload, "little", signed=False) if payload else 0


def _signed(payload: bytes) -> int:
    return int.from_bytes(payload, "little", signed=True) if payload else 0


def _split_usage(value: int, fallback_page: int, payload_size: int) -> tuple[int, int]:
    if payload_size == 4 and value > 0xFFFF:
        return (value >> 16) & 0xFFFF, value & 0xFFFF
    return fallback_page, value


def _expanded_usages(
    explicit: list[tuple[int, int]],
    minimum: tuple[int, int] | None,
    maximum: tuple[int, int] | None,
) -> tuple[tuple[int, int], ...]:
    result = list(explicit)
    if minimum is not None and maximum is not None and minimum[0] == maximum[0]:
        start = minimum[1]
        stop = maximum[1]
        # HID button ranges can be large. Structural classification only needs
        # the exact usages when the range is reasonably bounded.
        if start <= stop and stop - start <= 255:
            result.extend((minimum[0], usage) for usage in range(start, stop + 1))
        else:
            result.extend((minimum, maximum))
    return tuple(dict.fromkeys(result))


def parse_report_descriptor(raw: bytes) -> ParsedHidDescriptor:
    """Parse report structure and field-level HID metadata without semantics."""

    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise TypeError("raw HID descriptor must be bytes-like")
    data = bytes(raw)
    state = _GlobalState()
    stack: list[_GlobalState] = []
    local_usages: list[tuple[int, int]] = []
    local_usage_minimum: tuple[int, int] | None = None
    local_usage_maximum: tuple[int, int] | None = None
    bit_lengths: dict[tuple[str, int], int] = {}
    usage_pages: dict[tuple[str, int], set[int]] = {}
    fields: list[HidFieldDefinition] = []

    def clear_local() -> None:
        nonlocal local_usage_minimum, local_usage_maximum
        local_usages.clear()
        local_usage_minimum = None
        local_usage_maximum = None

    offset = 0
    while offset < len(data):
        prefix = data[offset]
        offset += 1

        if prefix == 0xFE:  # Long item: size, long tag, payload.
            if offset + 2 > len(data):
                raise HidDescriptorError("truncated HID long-item header")
            size = data[offset]
            offset += 2  # Skip size and long tag.
            if offset + size > len(data):
                raise HidDescriptorError("truncated HID long item")
            offset += size
            continue

        size_code = prefix & 0x03
        size = (0, 1, 2, 4)[size_code]
        item_type = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        if offset + size > len(data):
            raise HidDescriptorError("truncated HID short item")
        payload = data[offset:offset + size]
        offset += size
        value = _unsigned(payload)

        if item_type == 1:  # Global
            if tag == 0x0:  # Usage Page
                state.usage_page = value
            elif tag == 0x1:  # Logical Minimum
                state.logical_minimum = _signed(payload)
            elif tag == 0x2:  # Logical Maximum
                state.logical_maximum = (
                    _signed(payload)
                    if state.logical_minimum is not None and state.logical_minimum < 0
                    else _unsigned(payload)
                )
            elif tag == 0x7:  # Report Size
                state.report_size = value
            elif tag == 0x8:  # Report ID
                if value == 0 or value > 0xFF:
                    raise HidDescriptorError(f"invalid report ID {value}")
                state.report_id = value
            elif tag == 0x9:  # Report Count
                state.report_count = value
            elif tag == 0xA:  # Push
                stack.append(state.copy())
            elif tag == 0xB:  # Pop
                if not stack:
                    raise HidDescriptorError("HID global-state pop without push")
                state = stack.pop()
            continue

        if item_type == 2:  # Local
            if tag == 0x0:  # Usage
                local_usages.append(_split_usage(value, state.usage_page, size))
            elif tag == 0x1:  # Usage Minimum
                local_usage_minimum = _split_usage(value, state.usage_page, size)
            elif tag == 0x2:  # Usage Maximum
                local_usage_maximum = _split_usage(value, state.usage_page, size)
            continue

        if item_type != 0:  # Reserved
            continue

        report_type = {0x8: "input", 0x9: "output", 0xB: "feature"}.get(tag)
        if report_type is not None:
            key = (report_type, state.report_id)
            field_offset = bit_lengths.get(key, 0)
            field_usages = _expanded_usages(
                local_usages,
                local_usage_minimum,
                local_usage_maximum,
            )
            pages = {state.usage_page}
            pages.update(page for page, _usage in field_usages)
            usage_pages.setdefault(key, set()).update(pages)
            fields.append(
                HidFieldDefinition(
                    report_id=state.report_id,
                    report_type=report_type,
                    bit_offset=field_offset,
                    report_size=state.report_size,
                    report_count=state.report_count,
                    flags=value,
                    usage_pages=tuple(sorted(pages)),
                    usages=field_usages,
                    logical_minimum=state.logical_minimum,
                    logical_maximum=state.logical_maximum,
                )
            )
            bit_lengths[key] = field_offset + state.report_size * state.report_count

        # Local items are reset after every Main item, including Collection.
        clear_local()

    reports: list[HidReportDefinition] = []
    order = {"input": 0, "output": 1, "feature": 2}
    for (report_type, report_id), bits in sorted(
        bit_lengths.items(), key=lambda item: (order[item[0][0]], item[0][1])
    ):
        payload_bytes = ceil(bits / 8) if bits else 0
        byte_length = payload_bytes + (1 if report_id else 0)
        reports.append(
            HidReportDefinition(
                report_id=report_id,
                report_type=report_type,
                byte_length=byte_length,
                usage_pages=tuple(sorted(usage_pages[(report_type, report_id)])),
            )
        )

    return ParsedHidDescriptor(
        raw=data,
        reports=tuple(reports),
        fields=tuple(fields),
    )


def enumerate_report_ids(descriptor: ParsedHidDescriptor) -> tuple[int, ...]:
    return tuple(sorted({report.report_id for report in descriptor.reports}))


def _reports_of_type(
    descriptor: ParsedHidDescriptor, report_type: str
) -> tuple[HidReportDefinition, ...]:
    return tuple(report for report in descriptor.reports if report.report_type == report_type)


def get_input_reports(descriptor: ParsedHidDescriptor) -> tuple[HidReportDefinition, ...]:
    return _reports_of_type(descriptor, "input")


def get_output_reports(descriptor: ParsedHidDescriptor) -> tuple[HidReportDefinition, ...]:
    return _reports_of_type(descriptor, "output")


def get_feature_reports(descriptor: ParsedHidDescriptor) -> tuple[HidReportDefinition, ...]:
    return _reports_of_type(descriptor, "feature")


def fields_for_report(
    descriptor: ParsedHidDescriptor,
    *,
    report_type: str,
    report_id: int,
) -> tuple[HidFieldDefinition, ...]:
    return tuple(
        field
        for field in descriptor.fields
        if field.report_type == report_type and field.report_id == report_id
    )


def fields_overlapping_wire_byte(
    descriptor: ParsedHidDescriptor,
    *,
    report_type: str,
    report_id: int,
    byte_offset: int,
) -> tuple[HidFieldDefinition, ...]:
    """Return descriptor fields touching one raw hidraw byte offset."""

    return tuple(
        field
        for field in fields_for_report(
            descriptor,
            report_type=report_type,
            report_id=report_id,
        )
        if field.overlaps_wire_byte(byte_offset)
    )


def calculate_report_lengths(
    descriptor: ParsedHidDescriptor,
    *,
    report_type: str | None = None,
) -> dict[int, int]:
    """Return report ID -> byte length, optionally restricted by report type.

    If the same report ID occurs in multiple report types, the maximum length
    is returned. Callers issuing a GET_FEATURE should normally pass
    ``report_type="feature"``.
    """

    result: dict[int, int] = {}
    for report in descriptor.reports:
        if report_type is not None and report.report_type != report_type:
            continue
        result[report.report_id] = max(result.get(report.report_id, 0), report.byte_length)
    return result


def vendor_defined_reports(
    descriptor: ParsedHidDescriptor,
) -> tuple[HidReportDefinition, ...]:
    """Return reports touching HID vendor-defined usage pages (0xFF00-0xFFFF)."""

    return tuple(
        report
        for report in descriptor.reports
        if any(0xFF00 <= page <= 0xFFFF for page in report.usage_pages)
    )
