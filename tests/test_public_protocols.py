# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from mouse_control.public_protocols import (
    PublicProtocolError,
    build_beastx_page_read,
    build_dms_short_dpi_payload,
    build_h2_dpi_set,
    build_h2_polling_set,
    crc16_modbus,
    decode_beastx_dpi_raw,
    decode_beastx_page_reply,
    decode_dms_config_snapshot,
    decode_dms_receiver_ack,
    decode_h2_dpi_ic17,
    decode_h2_dpi_table,
    decode_h2_polling_response,
    decode_rawm_event,
    decode_rawm_notification,
    decode_rawm_transport_chunk,
    encode_beastx_dpi_raw,
    encode_h2_dpi_ic17,
    encode_rawm_event,
    encode_rawm_query,
    encode_rawm_transport_chunk,
    finalize_beastx_report,
    finalize_h2_packet,
    h2_is_unsolicited_status,
    validate_beastx_report,
    validate_h2_packet,
)


def test_dms_receiver_ack_and_snapshot_preserve_unknown_rate_index() -> None:
    assert decode_dms_receiver_ack(bytes.fromhex("54 e4 01 00")).state == "reply_ready"
    with pytest.raises(PublicProtocolError):
        decode_dms_receiver_ack(bytes.fromhex("54 e4 03 00"))

    payload = bytearray(19)
    payload[0] = 0x07
    payload[1] = 2
    payload[2] = 0x20  # 1000 Hz, DPI slot 0
    payload[3] = 0x31  # deliberately unknown rate index 3, DPI slot 1
    payload[4] = 0x12  # 500 Hz, DPI slot 2
    for offset, dpi in zip(range(5, 15, 2), (800, 1500, 2000, 2500, 3000)):
        payload[offset:offset + 2] = dpi.to_bytes(2, "little")
    payload[15] = 0xA5
    payload[16] = 5
    payload[17] = 4
    payload[18] = 10
    snapshot = decode_dms_config_snapshot(bytes(payload))
    assert snapshot.usb.rate_hz == 1000
    assert snapshot.wireless_24g.rate_hz is None
    assert snapshot.bluetooth.rate_hz == 500
    assert snapshot.dpi_values == (800, 1500, 2000, 2500, 3000)


def test_dms_short_dpi_builder_has_exact_repeated_index_and_le_values() -> None:
    packet = build_dms_short_dpi_payload(
        (800, 1500, 2000, 2500, 3000), active_index=1, enabled_levels=5
    )
    assert len(packet) == 20
    assert packet[:4] == bytes((0x40, 1, 1, 1))
    assert int.from_bytes(packet[4:6], "little") == 800
    assert int.from_bytes(packet[12:14], "little") == 3000
    assert packet[14] == 5
    assert packet[15:] == bytes(5)


def test_rawm_event_transport_and_notification_roundtrip() -> None:
    event = encode_rawm_event(0x0B, bytes((0x06,)) + (800 | (1600 << 16)).to_bytes(4, "little"))
    parsed = decode_rawm_event(event)
    assert parsed.command == 0x0B
    assert parsed.declared_length == len(event)
    notification = decode_rawm_notification(event)
    assert notification.kind == "xy_dpi"
    assert notification.value == (800, 1600)

    report = encode_rawm_transport_chunk(event)
    assert len(report) == 64
    assert decode_rawm_transport_chunk(report).payload == event
    virtual = encode_rawm_transport_chunk(event, virtual=True)
    decoded = decode_rawm_transport_chunk(virtual)
    assert decoded.virtual
    assert decoded.payload == event


def test_rawm_query_is_length_framed_with_u64le_epoch() -> None:
    event = encode_rawm_query(0x0102030405060708)
    parsed = decode_rawm_event(event)
    assert parsed.command == 1
    assert parsed.data[:3] == bytes((3, 0, 0))
    assert parsed.data[3:] == bytes.fromhex("08 07 06 05 04 03 02 01")


def test_rawm_rejects_padding_smuggling_and_declared_length_mismatch() -> None:
    report = bytearray(encode_rawm_transport_chunk(b"abc"))
    report[-1] = 1
    with pytest.raises(PublicProtocolError):
        decode_rawm_transport_chunk(bytes(report))
    with pytest.raises(PublicProtocolError):
        decode_rawm_event(bytes((0x01, 0x09, 1, 2)))


@pytest.mark.parametrize(
    ("dpi", "raw"),
    ((50, 1), (800, 16), (10000, 200), (11000, 210), (12000, 220),
     (13000, 221), (14000, 222), (26000, 234)),
)
def test_h2_ic17_dpi_codec_roundtrips_only_representable_values(dpi: int, raw: int) -> None:
    assert encode_h2_dpi_ic17(dpi) == raw
    assert decode_h2_dpi_ic17(raw) == dpi


def test_h2_ic17_refuses_documented_formula_values_that_do_not_roundtrip() -> None:
    # The recovered source's middle/high formulas overlap at raw 221.  Do not
    # silently encode 12100..12900 into values that decode as 13K+.
    with pytest.raises(PublicProtocolError):
        encode_h2_dpi_ic17(12100)
    with pytest.raises(PublicProtocolError):
        encode_h2_dpi_ic17(13500)


def test_h2_polling_builder_and_decoder_use_exact_codes_and_checksum() -> None:
    packet = build_h2_polling_set(1000)
    assert len(packet) == 33
    assert packet[1:6] == bytes((0x02, 0, 1, 1, 1))
    validate_h2_packet(packet)

    response = bytearray(33)
    response[1] = 0x12
    response[4] = 4
    response = bytearray(finalize_h2_packet(response))
    assert decode_h2_polling_response(bytes(response)) == 250
    response[32] ^= 1
    with pytest.raises(PublicProtocolError):
        decode_h2_polling_response(bytes(response))


def test_h2_dpi_setter_duplicates_x_y_and_table_decoder_roundtrips() -> None:
    values = (800, 1500, 2000, 2500, 3000, 4000)
    setter = build_h2_dpi_set(values, active_index=2, enabled_count=6, ic_type=17)
    validate_h2_packet(setter)
    assert setter[1] == 0x03 and setter[4] == 26 and setter[6] == 0x26
    for index, dpi in enumerate(values):
        start = 7 + index * 4
        expected = encode_h2_dpi_ic17(dpi).to_bytes(2, "little")
        assert setter[start:start + 2] == expected
        assert setter[start + 2:start + 4] == expected

    response = bytearray(33)
    response[1] = 0x13
    response[4] = 0x26
    for index, dpi in enumerate(values):
        start = (5, 9, 13, 17, 21, 25)[index]
        response[start:start + 2] = encode_h2_dpi_ic17(dpi).to_bytes(2, "little")
    response = finalize_h2_packet(response)
    table = decode_h2_dpi_table(response, ic_type=17)
    assert table.active_index == 2
    assert table.enabled_count == 6
    assert table.dpi_values == values


def test_h2_unsolicited_prefix_is_classified_without_treating_it_as_reply() -> None:
    assert h2_is_unsolicited_status(bytes((0xD1, 0)))
    assert h2_is_unsolicited_status(bytes((0xD2, 0)))
    assert not h2_is_unsolicited_status(bytes((0x00, 0)))


def test_beastx_read_report_crc_and_page_reply() -> None:
    request = build_beastx_page_read(0x48)
    validate_beastx_report(request)
    assert request[3:8] == bytes((0x05, 0x18, 0x48, 0, 0))
    assert int.from_bytes(request[1:3], "little") == crc16_modbus(request[3:32])

    reply = bytearray(64)
    reply[0] = 0x04
    reply[3:6] = bytes((0x05, 0x18, 0x48))
    reply[6:30] = bytes(range(24))
    reply = finalize_beastx_report(reply)
    page, data = decode_beastx_page_reply(reply)
    assert page == 0x48
    assert data == bytes(range(24))


def test_beastx_dpi_transform_is_deterministic_and_crc_tampering_is_rejected() -> None:
    for dpi in (400, 800, 1600, 3200, 8000):
        raw = encode_beastx_dpi_raw(dpi)
        assert abs(decode_beastx_dpi_raw(raw) - dpi) <= 1
    packet = bytearray(build_beastx_page_read(0))
    packet[10] ^= 1
    with pytest.raises(PublicProtocolError):
        validate_beastx_report(bytes(packet))
