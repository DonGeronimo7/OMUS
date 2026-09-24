# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure protocol vocabulary recovered from public, hardware-tested projects.

This module deliberately contains *codecs and parsers only*.  It never opens a
HID device and never grants write authority.  Discovery may use these routines
to recognize and reason about candidate protocols, while physical writes still
flow through the existing exact-binding proof/transaction machinery.

The functions are intentionally strict: ambiguous, truncated, non-round-trip or
out-of-domain values are rejected rather than normalized into a plausible
packet.
"""

from __future__ import annotations

from dataclasses import dataclass


class PublicProtocolError(ValueError):
    """A public protocol sample is malformed or outside the proven grammar."""


# ---------------------------------------------------------------------------
# Darmoshark M3 / Attack Shark M3 — dms
# ---------------------------------------------------------------------------

DMS_RATE_INDEX_HZ = {0: 125, 1: 500, 2: 1000}


@dataclass(frozen=True)
class DmsReceiverAck:
    status: int
    state: str


@dataclass(frozen=True)
class DmsConnectionSelection:
    rate_index: int
    dpi_index: int
    rate_hz: int | None


@dataclass(frozen=True)
class DmsConfigSnapshot:
    active_profile: int
    usb: DmsConnectionSelection
    wireless_24g: DmsConnectionSelection
    bluetooth: DmsConnectionSelection
    dpi_values: tuple[int, ...]
    sensor_flags: int
    enabled_levels: int
    debounce_ms: int
    sleep_minutes: int


_DMS_ACK_STATES = {
    0: "queued",
    1: "reply_ready",
    2: "no_rf_link",
    4: "busy_or_queued",
}


def decode_dms_receiver_ack(report: bytes) -> DmsReceiverAck:
    """Decode the exact ``54 E4 <status> 00`` receiver acknowledgement."""

    if len(report) < 4 or report[0] != 0x54 or report[1] != 0xE4 or report[3] != 0:
        raise PublicProtocolError("not a Darmoshark dms receiver acknowledgement")
    status = report[2]
    if status not in _DMS_ACK_STATES:
        raise PublicProtocolError(f"unknown Darmoshark receiver status 0x{status:02x}")
    return DmsReceiverAck(status, _DMS_ACK_STATES[status])


def _decode_dms_connection(value: int) -> DmsConnectionSelection:
    rate_index = (value >> 4) & 0x0F
    dpi_index = value & 0x0F
    return DmsConnectionSelection(rate_index, dpi_index, DMS_RATE_INDEX_HZ.get(rate_index))


def decode_dms_config_snapshot(payload: bytes) -> DmsConfigSnapshot:
    """Decode the receiver opcode ``0x07`` configuration snapshot.

    Index 3 is intentionally *not* assigned a report rate: the tested M3 accepts
    that index even though its vendor profile does not declare the meaning.
    """

    if len(payload) < 19 or payload[0] != 0x07:
        raise PublicProtocolError("malformed Darmoshark dms configuration snapshot")
    dpi_values = tuple(
        int.from_bytes(payload[offset:offset + 2], "little")
        for offset in range(5, 15, 2)
    )
    if any(value <= 0 for value in dpi_values):
        raise PublicProtocolError("Darmoshark snapshot contains invalid DPI value")
    enabled = payload[16]
    if not 1 <= enabled <= len(dpi_values):
        raise PublicProtocolError("Darmoshark enabled DPI-level count is invalid")
    selections = tuple(_decode_dms_connection(payload[index]) for index in (2, 3, 4))
    if any(item.dpi_index >= enabled for item in selections):
        raise PublicProtocolError("Darmoshark active DPI index exceeds enabled level count")
    return DmsConfigSnapshot(
        active_profile=payload[1],
        usb=selections[0],
        wireless_24g=selections[1],
        bluetooth=selections[2],
        dpi_values=dpi_values,
        sensor_flags=payload[15],
        enabled_levels=enabled,
        debounce_ms=payload[17],
        sleep_minutes=payload[18],
    )


def build_dms_short_dpi_payload(
    dpi_values: tuple[int, int, int, int, int],
    *,
    active_index: int,
    enabled_levels: int,
) -> bytes:
    """Build the proven 20-byte ``0x40`` short DPI payload, without sending it."""

    if len(dpi_values) != 5 or any(type(value) is not int or not 1 <= value <= 0xFFFF for value in dpi_values):
        raise PublicProtocolError("Darmoshark short DPI form requires five u16 values")
    if not 1 <= enabled_levels <= 5 or not 0 <= active_index < enabled_levels:
        raise PublicProtocolError("Darmoshark active/enabled DPI selection is invalid")
    packet = bytearray(20)
    packet[0] = 0x40
    packet[1:4] = bytes((active_index,)) * 3
    for slot, value in enumerate(dpi_values):
        start = 4 + slot * 2
        packet[start:start + 2] = value.to_bytes(2, "little")
    packet[14] = enabled_levels
    return bytes(packet)


# ---------------------------------------------------------------------------
# MiracleTek-hosted RAWM — variable logical events over fixed 64-byte HID
# ---------------------------------------------------------------------------

RAWM_CMD_QUERY = 0x01
RAWM_CMD_QUERY_RESULT = 0x02
RAWM_CMD_CONFIG = 0x03
RAWM_CMD_ACTION = 0x06
RAWM_CMD_NOTIFY = 0x0B


@dataclass(frozen=True)
class RawmTransportChunk:
    virtual: bool
    payload: bytes


@dataclass(frozen=True)
class RawmEvent:
    command: int
    declared_length: int
    data: bytes


@dataclass(frozen=True)
class RawmNotification:
    kind: str
    value: int | tuple[int, int] | bytes


def encode_rawm_event(command: int, data: bytes = b"") -> bytes:
    """Encode the 12-bit RAWM event length in the command/header pair."""

    if not 0 <= command <= 0x0F:
        raise PublicProtocolError("RAWM command must fit the low nibble")
    total = 2 + len(data)
    if not 2 <= total <= 0x0FFF:
        raise PublicProtocolError("RAWM event exceeds the 12-bit length domain")
    return bytes((((total >> 8) & 0x0F) << 4 | command, total & 0xFF)) + bytes(data)


def decode_rawm_event(event: bytes) -> RawmEvent:
    if len(event) < 2:
        raise PublicProtocolError("truncated RAWM event")
    declared = ((event[0] & 0xF0) << 4) | event[1]
    if declared < 2 or declared != len(event):
        raise PublicProtocolError("RAWM declared event length does not match capture")
    return RawmEvent(event[0] & 0x0F, declared, event[2:])


def encode_rawm_query(epoch_seconds: int) -> bytes:
    if type(epoch_seconds) is not int or not 0 <= epoch_seconds <= 0xFFFFFFFFFFFFFFFF:
        raise PublicProtocolError("RAWM query epoch must be u64")
    # OS_PC=0x03 followed by two reserved zeros and little-endian epoch.
    return encode_rawm_event(RAWM_CMD_QUERY, bytes((0x03, 0, 0)) + epoch_seconds.to_bytes(8, "little"))


def encode_rawm_transport_chunk(payload: bytes, *, virtual: bool = False) -> bytes:
    """Wrap one event fragment in a fixed 64-byte RAWM transport report."""

    limit = 62 if virtual else 63
    if not 0 < len(payload) <= limit:
        raise PublicProtocolError(f"RAWM {'virtual' if virtual else 'physical'} chunk must be 1..{limit} bytes")
    report = bytearray(64)
    if virtual:
        report[0] = 0xC0
        report[1] = 0x80 | len(payload)
        report[2:2 + len(payload)] = payload
    else:
        report[0] = 0x80 | len(payload)
        report[1:1 + len(payload)] = payload
    return bytes(report)


def decode_rawm_transport_chunk(report: bytes) -> RawmTransportChunk:
    if len(report) != 64:
        raise PublicProtocolError("RAWM transport report must be exactly 64 bytes")
    virtual = report[0] == 0xC0
    if virtual:
        marker = report[1]
        limit = 62
        start = 2
    else:
        marker = report[0]
        limit = 63
        start = 1
    if not marker & 0x80:
        raise PublicProtocolError("RAWM transport chunk marker is missing")
    size = marker & 0x7F
    if not 1 <= size <= limit:
        raise PublicProtocolError("RAWM transport chunk length is invalid")
    end = start + size
    if any(report[end:]):
        raise PublicProtocolError("RAWM transport padding contains non-zero bytes")
    return RawmTransportChunk(virtual, report[start:end])


def decode_rawm_notification(event: bytes) -> RawmNotification:
    parsed = decode_rawm_event(event)
    if parsed.command != RAWM_CMD_NOTIFY or not parsed.data:
        raise PublicProtocolError("not a RAWM notification")
    kind, body = parsed.data[0], parsed.data[1:]
    if kind in (0x00, 0x01):
        if len(body) < 2:
            raise PublicProtocolError("truncated RAWM scalar notification")
        value = int.from_bytes(body[:2], "little")
        return RawmNotification("dpi" if kind == 0 else "polling", value)
    if kind == 0x06:
        if len(body) < 4:
            raise PublicProtocolError("truncated RAWM independent-axis DPI notification")
        packed = int.from_bytes(body[:4], "little")
        return RawmNotification("xy_dpi", (packed & 0xFFFF, packed >> 16))
    if kind == 0x14:
        return RawmNotification("onboard_stream", bytes(body))
    if kind == 0x22:
        if not body:
            raise PublicProtocolError("truncated RAWM onboard-index notification")
        return RawmNotification("active_onboard_index", body[0])
    raise PublicProtocolError(f"unknown RAWM notification type 0x{kind:02x}")


# ---------------------------------------------------------------------------
# EWEADN H2 — exact 33-byte family
# ---------------------------------------------------------------------------

H2_POLLING_HZ_TO_CODE = {125: 8, 250: 4, 500: 2, 1000: 1}
H2_POLLING_CODE_TO_HZ = {value: key for key, value in H2_POLLING_HZ_TO_CODE.items()}
H2_UNSOLICITED_PREFIXES = frozenset((0xD1, 0xD2))


@dataclass(frozen=True)
class H2DpiTable:
    active_index: int
    enabled_count: int
    dpi_values: tuple[int, ...]


def h2_checksum(packet: bytes) -> int:
    if len(packet) != 33:
        raise PublicProtocolError("EWEADN H2 packet must be exactly 33 bytes")
    return sum(packet[5:32]) & 0xFF


def finalize_h2_packet(packet: bytes | bytearray) -> bytes:
    if len(packet) != 33:
        raise PublicProtocolError("EWEADN H2 packet must be exactly 33 bytes")
    result = bytearray(packet)
    result[32] = sum(result[5:32]) & 0xFF
    return bytes(result)


def validate_h2_packet(packet: bytes) -> None:
    if len(packet) != 33 or packet[32] != sum(packet[5:32]) & 0xFF:
        raise PublicProtocolError("invalid EWEADN H2 packet checksum")


def h2_is_unsolicited_status(packet: bytes) -> bool:
    return bool(packet) and packet[0] in H2_UNSOLICITED_PREFIXES


def encode_h2_dpi_ic17(dpi: int) -> int:
    """Encode only values that round-trip through the documented ic_type 17 codec."""

    if type(dpi) is not int or dpi <= 0:
        raise PublicProtocolError("DPI must be a positive integer")
    if dpi <= 10000:
        if dpi % 50:
            raise PublicProtocolError("ic_type 17 DPI <=10000 must align to 50")
        raw = dpi // 50
    elif dpi < 13000:
        if (dpi - 10000) % 100:
            raise PublicProtocolError("ic_type 17 mid-range DPI must align to 100")
        raw = ((dpi - 10000) // 100) + 200
    else:
        if (dpi - 13000) % 1000:
            raise PublicProtocolError("ic_type 17 high DPI must align to 1000")
        raw = ((dpi - 13000) // 1000) + 221
    if not 0 < raw <= 0xFFFF or decode_h2_dpi_ic17(raw) != dpi:
        raise PublicProtocolError("DPI is not representable by the proven ic_type 17 codec")
    return raw


def decode_h2_dpi_ic17(raw: int) -> int:
    if type(raw) is not int or not 0 < raw <= 0xFFFF:
        raise PublicProtocolError("raw H2 DPI value must be a positive u16")
    if raw < 200:
        return 50 * raw
    if raw <= 220:
        return (raw - 200) * 100 + 10000
    return (raw - 220) * 1000 + 12000


def decode_h2_polling_response(packet: bytes) -> int:
    validate_h2_packet(packet)
    if packet[1] != 0x12:
        raise PublicProtocolError("not an EWEADN H2 report-rate response")
    try:
        return H2_POLLING_CODE_TO_HZ[packet[4]]
    except KeyError as exc:
        raise PublicProtocolError("unknown EWEADN H2 polling code") from exc


def build_h2_polling_set(hz: int) -> bytes:
    try:
        code = H2_POLLING_HZ_TO_CODE[hz]
    except KeyError as exc:
        raise PublicProtocolError("unsupported EWEADN H2 polling rate") from exc
    packet = bytearray(33)
    packet[1] = 0x02
    packet[3] = 1
    packet[4] = 1
    packet[5] = code
    return finalize_h2_packet(packet)


def decode_h2_dpi_table(packet: bytes, *, ic_type: int) -> H2DpiTable:
    validate_h2_packet(packet)
    if packet[1] != 0x13:
        raise PublicProtocolError("not an EWEADN H2 DPI-table response")
    if ic_type != 17:
        raise PublicProtocolError("only the proven EWEADN H2 ic_type 17 codec is implemented")
    active = (packet[4] >> 4) & 0x0F
    count = packet[4] & 0x0F
    if not 1 <= count <= 6 or active >= count:
        raise PublicProtocolError("invalid EWEADN H2 DPI active/count nibble")
    values = tuple(
        decode_h2_dpi_ic17(int.from_bytes(packet[offset:offset + 2], "little"))
        for offset in (5, 9, 13, 17, 21, 25)
    )
    return H2DpiTable(active, count, values)


def build_h2_dpi_set(
    dpi_values: tuple[int, int, int, int, int, int],
    *,
    active_index: int,
    enabled_count: int,
    ic_type: int,
) -> bytes:
    if ic_type != 17:
        raise PublicProtocolError("only the proven EWEADN H2 ic_type 17 codec is implemented")
    if len(dpi_values) != 6 or not 1 <= enabled_count <= 6 or not 0 <= active_index < enabled_count:
        raise PublicProtocolError("invalid EWEADN H2 DPI table selection")
    raws = tuple(encode_h2_dpi_ic17(value) for value in dpi_values)
    packet = bytearray(33)
    packet[1] = 0x03
    packet[3] = 1
    packet[4] = 26
    packet[6] = (active_index << 4) | enabled_count
    for index, raw in enumerate(raws):
        start = 7 + index * 4
        packet[start:start + 2] = raw.to_bytes(2, "little")
        packet[start + 2:start + 4] = raw.to_bytes(2, "little")
    return finalize_h2_packet(packet)


# ---------------------------------------------------------------------------
# WLMOUSE Beast X — tested 36A7:A887 page protocol
# ---------------------------------------------------------------------------


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def finalize_beastx_report(report: bytes | bytearray) -> bytes:
    if len(report) != 64 or report[0] != 0x04:
        raise PublicProtocolError("WLMOUSE Beast X report must be 64 bytes with report ID 4")
    result = bytearray(report)
    result[1:3] = crc16_modbus(result[3:32]).to_bytes(2, "little")
    return bytes(result)


def validate_beastx_report(report: bytes) -> None:
    if len(report) != 64 or report[0] != 0x04:
        raise PublicProtocolError("not an exact Beast X report")
    expected = crc16_modbus(report[3:32])
    if int.from_bytes(report[1:3], "little") != expected:
        raise PublicProtocolError("Beast X CRC16/MODBUS mismatch")


def build_beastx_page_read(page_offset: int) -> bytes:
    if type(page_offset) is not int or not 0 <= page_offset <= 0xFF:
        raise PublicProtocolError("Beast X page offset must be u8")
    report = bytearray(64)
    report[0] = 0x04
    report[3:8] = bytes((0x05, 0x18, page_offset, 0, 0))
    return finalize_beastx_report(report)


def decode_beastx_page_reply(report: bytes) -> tuple[int, bytes]:
    validate_beastx_report(report)
    if report[3:5] != bytes((0x05, 0x18)):
        raise PublicProtocolError("not a Beast X page-read reply")
    return report[5], bytes(report[6:30])


def encode_beastx_dpi_raw(dpi: int) -> int:
    if type(dpi) is not int or dpi <= 0:
        raise PublicProtocolError("Beast X DPI must be a positive integer")
    raw = round(0.96 * dpi + 49)
    if not 0 <= raw <= 0xFFFF:
        raise PublicProtocolError("Beast X DPI does not fit u16")
    return raw


def decode_beastx_dpi_raw(raw: int) -> int:
    if type(raw) is not int or not 0 <= raw <= 0xFFFF or raw < 49:
        raise PublicProtocolError("Beast X raw DPI is invalid")
    return round((raw - 49) / 0.96)
