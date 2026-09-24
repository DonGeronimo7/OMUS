# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import json
import sys
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mouse_control.hidpp import (ADJUSTABLE_DPI_FEATURE_ID,
    DEVICE_NAME_FEATURE_ID, DpiEventDecoderProfile, HidppDevice, HidppFeature,
    DpiEventMetadata, HidppReport, discover_hidpp_device, dpi_decoder_profile,
    dpi_event_candidate, dpi_stage_event,
    find_hidraw, get_device_name, HidrawTransport, lookup_feature, parse_hidpp_report,
    load_cached_hidpp_device, save_hidpp_device, watch_dpi_events)


class FakeTransport:
    def __init__(self, path=Path("/dev/hidraw6"), *, dpi_index=7,
                 name_index=5, name=b"G305", dpi_version=0):
        self.path, self.dpi_index, self.name_index = path, dpi_index, name_index
        self.name, self.dpi_version = name, dpi_version

    def __enter__(self): return self
    def __exit__(self, *_args): pass

    def request(self, device, feature, function, parameters=b""):
        if feature == 0 and function == 1:
            params = bytes((2, 0))
        elif feature == 0 and function == 0:
            feature_id = int.from_bytes(parameters[:2], "big")
            if feature_id == DEVICE_NAME_FEATURE_ID and self.name_index:
                params = bytes((self.name_index, 0, 0))
            elif feature_id == ADJUSTABLE_DPI_FEATURE_ID and self.dpi_index:
                params = bytes((self.dpi_index, 0, self.dpi_version))
            else:
                params = bytes((0, 0, 0))
        elif feature == self.name_index and function == 0:
            params = bytes((len(self.name),))
        elif feature == self.name_index and function == 1:
            params = self.name[parameters[0]:]
        else:
            raise AssertionError((device, feature, function, parameters))
        return HidppReport(0x11, device, feature, function, 0x0A, params)


def make_device(*, vendor=0x046D, product=0x4074, index=7, version=0,
                name="G305", event_index=7):
    features = {ADJUSTABLE_DPI_FEATURE_ID:
                HidppFeature(ADJUSTABLE_DPI_FEATURE_ID, index, 0, version)}
    event = DpiEventMetadata(event_index, 0x11, 1) if event_index is not None else None
    return HidppDevice(vendor, product, 1, name, Path("/dev/hidraw6"),
                       (2, 0), features, "", event)


def test_parse_hidpp_report_header_and_preserve_parameters():
    report = parse_hidpp_report(bytes.fromhex("11 ff 0c 20 00 05 dc"))
    assert report == HidppReport(0x11, 0xFF, 0x0C, 2, 0, bytes.fromhex("00 05 dc"))
    assert parse_hidpp_report(bytes.fromhex("01 02 03 04")) is None
    assert parse_hidpp_report(b"\x11\xff") is None


def test_hidraw_resolution_uses_exact_identity_and_phys(tmp_path):
    sysfs = tmp_path / "hidraw"
    for name, identity, phys in [
        ("hidraw3", "0003:0000046D:0000C53F", "receiver"),
        ("hidraw6", "0003:0000046D:00004074", "mouse"),
        ("hidraw7", "0003:0000046D:00004074", "other")]:
        directory = sysfs / name / "device"
        directory.mkdir(parents=True)
        (directory / "uevent").write_text(f"HID_ID={identity}\nHID_PHYS={phys}\n")
    assert find_hidraw(0x046D, 0x4074, "mouse", sysfs, Path("/dev")) == [Path("/dev/hidraw6")]


def test_root_lookup_resolves_device_assigned_indexes():
    for assigned in (0x07, 0x0A):
        feature = lookup_feature(FakeTransport(dpi_index=assigned), 1,
                                 ADJUSTABLE_DPI_FEATURE_ID)
        assert feature is not None and feature.index == assigned


def test_hidraw_request_ignores_unrelated_traffic_and_matches_software_id():
    unrelated = bytes.fromhex("11 01 00 10 02 00") + bytes(14)
    matching = bytes.fromhex("11 01 00 1a 02 00") + bytes(14)
    transport = HidrawTransport(Path("/dev/hidraw6"))
    transport.fd = 9
    with patch("mouse_control.hidpp.os.write") as write, \
         patch("mouse_control.hidpp.select.select", return_value=([9], [], [])), \
         patch("mouse_control.hidpp.os.read", side_effect=[unrelated, matching]):
        response = transport.request(1, 0, 1)
    assert response.software_id == 0x0A
    assert write.call_args.args[1][:6] == bytes.fromhex("11 01 00 1a 00 00")


def test_device_name_parsing_and_missing_name_feature():
    transport = FakeTransport(name="G502 X LIGHTSPEED".encode())
    feature = lookup_feature(transport, 1, DEVICE_NAME_FEATURE_ID)
    assert feature is not None
    assert get_device_name(transport, 1, feature) == "G502 X LIGHTSPEED"
    assert lookup_feature(FakeTransport(name_index=0), 1, DEVICE_NAME_FEATURE_ID) is None


def test_discovery_collects_protocol_name_and_features(tmp_path):
    sysfs = tmp_path / "hidraw"
    directory = sysfs / "hidraw6" / "device"
    directory.mkdir(parents=True)
    (directory / "uevent").write_text("HID_ID=0003:0000046D:00004074\nHID_PHYS=mouse\n")
    device = discover_hidpp_device(0x046D, 0x4074, "mouse", sysfs=sysfs,
        dev_root=Path("/dev"), transport_factory=lambda path: FakeTransport(path))
    assert device is not None
    assert device.name == "G305" and device.protocol_version == (2, 0)
    assert device.feature(DEVICE_NAME_FEATURE_ID).index == 5
    assert device.feature(ADJUSTABLE_DPI_FEATURE_ID).index == 7


def test_missing_adjustable_dpi_disables_decoder_without_breaking_discovery(tmp_path):
    sysfs = tmp_path / "hidraw"
    directory = sysfs / "hidraw8" / "device"
    directory.mkdir(parents=True)
    (directory / "uevent").write_text("HID_ID=0003:0000046D:0000ABCD\n")
    device = discover_hidpp_device(0x046D, 0xABCD, sysfs=sysfs,
        transport_factory=lambda path: FakeTransport(path, dpi_index=0))
    assert device is not None and device.name == "G305"
    assert device.feature(ADJUSTABLE_DPI_FEATURE_ID) is None
    assert dpi_decoder_profile(device) is None


def packet(stage, *, device=1, feature=7, event=1, swid=0):
    return bytes([0x11, device, feature, (event << 4) | swid, stage]) + bytes(15)


def test_real_g305_fixture_uses_discovered_index_and_returns_stages():
    device = make_device(index=0x1A, version=1, event_index=0x07)
    profile = DpiEventDecoderProfile(0x046D, 0x4074, 1)
    assert [dpi_stage_event(packet(stage), device, profile)
            for stage in (0, 1, 2, 3, 4, 0)] == [0, 1, 2, 3, 4, 0]
    assert dpi_stage_event(packet(2, feature=0x07), device, profile) == 2
    assert dpi_stage_event(packet(2, feature=0x1A), device, profile) is None


def test_passive_event_learning_uses_observed_index_not_adjustable_dpi_index():
    device = make_device(index=0x1A, version=1, event_index=None)
    profile = DpiEventDecoderProfile(0x046D, 0x4074, 1)
    assert dpi_event_candidate(packet(4, feature=0x07), device, profile) == 0x07
    assert dpi_event_candidate(packet(5, feature=0x08), device, profile) is None


def test_unvalidated_device_or_feature_version_never_decodes():
    assert dpi_decoder_profile(make_device(product=0xC332, version=1)) is None
    assert dpi_decoder_profile(make_device(version=2)) is None


def test_cache_round_trip_loads_dynamic_g305_index(tmp_path):
    cache = tmp_path / "hidpp.json"
    original = make_device(index=0x1A, version=1,
                           name="G305 Lightspeed Wireless Gaming Mouse")
    save_hidpp_device(original, cache, now=1000)
    sysfs = tmp_path / "hidraw"
    directory = sysfs / "hidraw9" / "device"
    directory.mkdir(parents=True)
    (directory / "uevent").write_text("HID_ID=0003:0000046D:00004074\n")
    loaded = load_cached_hidpp_device(0x046D, 0x4074, path=cache, now=1001,
                                      sysfs=sysfs, dev_root=Path("/dev"))
    assert loaded is not None
    assert loaded.name == "G305 Lightspeed Wireless Gaming Mouse"
    assert loaded.feature(ADJUSTABLE_DPI_FEATURE_ID).index == 0x1A
    assert loaded.dpi_event.feature_index == 0x07
    assert dpi_stage_event(packet(3, feature=0x07), loaded,
                           dpi_decoder_profile(loaded)) == 3


def test_cache_identity_isolation_and_invalid_or_stale_data_fail_safely(tmp_path):
    cache = tmp_path / "hidpp.json"
    save_hidpp_device(make_device(version=1), cache, now=1000)
    assert load_cached_hidpp_device(0x046D, 0xC332, path=cache, now=1001,
                                    sysfs=tmp_path) is None
    assert load_cached_hidpp_device(0x046D, 0x4074, path=cache,
                                    now=1000 + 31 * 24 * 60 * 60,
                                    sysfs=tmp_path) is None
    old = json.loads(cache.read_text())
    old["schema"] = 1
    cache.write_text(json.dumps(old))
    assert load_cached_hidpp_device(0x046D, 0x4074, path=cache,
                                    now=1001, sysfs=tmp_path) is None
    cache.write_text("not json")
    assert load_cached_hidpp_device(0x046D, 0x4074, path=cache,
                                    sysfs=tmp_path) is None


def test_disappearing_hidraw_is_closed_and_nonfatal():
    stop, device = threading.Event(), make_device(version=1)
    profile = dpi_decoder_profile(device)
    def disappeared(*_args):
        stop.set()
        raise OSError("unplugged")
    with patch("mouse_control.hidpp.find_hidraw", return_value=[device.hidraw_path]), \
         patch("mouse_control.hidpp.os.open", return_value=9), \
         patch("mouse_control.hidpp.select.select", return_value=([9], [], [])), \
         patch("mouse_control.hidpp.os.read", side_effect=disappeared), \
         patch("mouse_control.hidpp.os.close") as close:
        watch_dpi_events(device, profile, lambda stage: None, stop, retry_interval=0)
    close.assert_called_once_with(9)
