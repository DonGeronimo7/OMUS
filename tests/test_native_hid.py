from pathlib import Path
import queue
import threading
import time

import pytest

from mouse_control.hardware.capabilities import BatteryState, DpiState
from mouse_control.hid_session import HidSession
from mouse_control.hidpp import HidppError, HidppReport
from mouse_control.hidpp_driver import (ADJUSTABLE_DPI_FEATURE_ID,
    ONBOARD_PROFILES_FEATURE_ID, REPORT_RATE_FEATURE_ID, BATTERY_STATUS_FEATURE_ID, Hidpp20Driver,
    connect_hidpp20,
    decode_supported_dpi)
from mouse_control.hidpp_driver import (UNIFIED_BATTERY_FEATURE_ID,
                                        decode_unified_battery, decode_battery_status)


def packet(device, feature, function, swid, parameters=b""):
    return bytes((0x11, device, feature, (function << 4) | swid)) + parameters.ljust(16, b"\0")


class QueueIo:
    def __init__(self, _path):
        self.incoming = queue.Queue()
        self.writes = []

    def read(self, timeout):
        try:
            return self.incoming.get(timeout=timeout)
        except queue.Empty:
            return None

    def write(self, data):
        self.writes.append(data)
        # An unsolicited profile event must not steal the command response.
        self.incoming.put(packet(1, 0x12, 1, 0, b"\x04"))
        self.incoming.put(packet(data[1], data[2], data[3] >> 4,
                                 data[3] & 0x0f, b"\x02\x00"))

    def close(self):
        pass


def test_session_correlates_reply_while_dispatching_unsolicited_event():
    created = []
    def factory(path):
        io = QueueIo(path); created.append(io); return io
    session = HidSession(Path("/dev/fake"), io_factory=factory)
    events = []
    session.subscribe(events.append)
    response = session.request(1, 0, 1)
    session.close()
    assert response.parameters[:2] == b"\x02\x00"
    assert [(event.feature_index, event.software_id) for event in events] == [(0x12, 0)]


def test_session_routes_protocol_error_to_waiter():
    class ErrorIo(QueueIo):
        def write(self, data):
            self.incoming.put(packet(data[1], 0xff, data[2] >> 4,
                                     data[2] & 0x0f, bytes((data[3], 2))))
    session = HidSession(Path("/dev/fake"), io_factory=ErrorIo)
    with pytest.raises(HidppError, match="0x02"):
        session.request(1, 0x1a, 2)
    session.close()


def test_supported_dpi_decodes_explicit_and_range_step_values():
    explicit, ranges = decode_supported_dpi(
        b"\0" + b"\x01\x90\x03\x20\x06\x40\0\0")
    assert explicit == (400, 800, 1600)
    assert ranges == ()
    explicit, ranges = decode_supported_dpi(
        b"\0" + b"\x01\x90\xe0\x32\x0c\x80\0\0")
    assert explicit == (400,)
    assert ranges[0].minimum == 400
    assert ranges[0].maximum == 3200
    assert ranges[0].step == 50


def test_unified_battery_rejects_empty_and_out_of_range_payloads():
    with pytest.raises(HidppError, match="malformed"):
        decode_unified_battery(b"")
    with pytest.raises(HidppError, match="outside"):
        decode_unified_battery(bytes((101,)))
    assert decode_unified_battery(bytes((83, 0, 0))) == BatteryState(percentage=83)


def test_g305_battery_status_decodes_validated_0x1000_payload():
    assert decode_battery_status(bytes.fromhex("5a 32 00")) == BatteryState(
        percentage=90, status="discharging")
    with pytest.raises(HidppError):
        decode_battery_status(bytes((101, 50, 0)))
    with pytest.raises(HidppError):
        decode_battery_status(bytes((90,)))


class FakeSession:
    def __init__(self, *, mismatch=False, profile_mode=0x02):
        self.dpi = 800
        self.rate_ms = 2
        self.mismatch = mismatch
        self.profile_mode = profile_mode
        self.calls = []
        self.callbacks = []

    def request(self, device, feature, function, parameters=b""):
        self.calls.append((device, feature, function, parameters))
        if feature == 0 and function == 1:
            result = bytes((2, 0))
        elif feature == 0 and function == 0:
            feature_id = int.from_bytes(parameters[:2], "big")
            indexes = {ADJUSTABLE_DPI_FEATURE_ID: 0x19,
                       ONBOARD_PROFILES_FEATURE_ID: 0x12,
                       REPORT_RATE_FEATURE_ID: 0x17}
            result = bytes((indexes.get(feature_id, 0), 0, 1))
        elif feature == 0x19 and function == 0:
            result = b"\x01"
        elif feature == 0x19 and function == 1:
            result = b"\0\x01\x90\x03\x20\x05\xdc\x07\xd0\0\0"
        elif feature == 0x19 and function == 2:
            result = b"\0" + self.dpi.to_bytes(2, "big")
        elif feature == 0x19 and function == 3:
            requested = int.from_bytes(parameters[1:3], "big")
            self.dpi = requested + 1 if self.mismatch else requested
            result = b"\0"
        elif feature == 0x17 and function == 0:
            result = b"\x8b"  # 1, 2, 4 and 8 ms
        elif feature == 0x12 and function == 2:
            result = bytes((self.profile_mode,))
        elif feature == 0x17 and function == 1:
            result = bytes((self.rate_ms,))
        elif feature == 0x17 and function == 2:
            self.rate_ms = parameters[0]
            result = b"\0"
        else:
            raise AssertionError((device, feature, function, parameters))
        return HidppReport(0x11, device, feature, function, 0x0a, result)

    def subscribe(self, callback):
        self.callbacks.append(callback)
        return lambda: self.callbacks.remove(callback)


def test_driver_discovers_dynamic_indexes_reads_writes_and_verifies():
    session = FakeSession()
    driver = Hidpp20Driver(session, 1)
    assert driver.features[ADJUSTABLE_DPI_FEATURE_ID].index == 0x19
    assert driver.features[ONBOARD_PROFILES_FEATURE_ID].index == 0x12
    assert driver.get_dpi_state() == DpiState(800, 800, confirmed=True)
    assert driver.set_dpi(1500).x_dpi == 1500
    assert any(call[1:3] == (0x19, 3) for call in session.calls)
    assert driver.capabilities.report_rate.values == (1000, 500, 250, 125)
    assert driver.set_report_rate(1000) == 1000


def test_driver_discovers_unified_battery_through_root_and_reads_percentage():
    class BatterySession(FakeSession):
        def request(self, device, feature, function, parameters=b""):
            if feature == 0 and function == 0 and int.from_bytes(parameters[:2], "big") == UNIFIED_BATTERY_FEATURE_ID:
                return HidppReport(0x11, device, feature, function, 0x0a, bytes((0x2A, 0, 1)))
            if feature == 0x2A and function == 0:
                return HidppReport(0x11, device, feature, function, 0x0a, bytes((83, 0, 0)))
            return super().request(device, feature, function, parameters)
    session = BatterySession()
    driver = Hidpp20Driver(session, 1)
    assert driver.features[UNIFIED_BATTERY_FEATURE_ID].index == 0x2A
    assert driver.capabilities.battery.percentage
    assert driver.get_battery_state() == BatteryState(percentage=83)


def test_g305_dynamic_battery_status_runtime_path():
    class BatterySession(FakeSession):
        def request(self, device, feature, function, parameters=b""):
            if feature == 0 and function == 0 and int.from_bytes(parameters[:2], "big") == BATTERY_STATUS_FEATURE_ID:
                return HidppReport(0x11, device, feature, function, 0x0a, bytes((0x05, 0, 1)))
            if feature == 0x05 and function == 0:
                return HidppReport(0x11, device, feature, function, 0x0a,
                                   bytes.fromhex("5a 32 00"))
            return super().request(device, feature, function, parameters)
    session = BatterySession()
    driver = Hidpp20Driver(session, 1)
    assert UNIFIED_BATTERY_FEATURE_ID not in driver.features
    assert driver.features[BATTERY_STATUS_FEATURE_ID].index == 0x05
    assert driver.get_battery_state() == BatteryState(percentage=90, status="discharging")
    assert driver.capabilities.battery.readable


def test_report_rate_remains_readable_but_not_writable_in_onboard_mode():
    session = FakeSession(profile_mode=0x01)
    driver = Hidpp20Driver(session, 1)
    caps = driver.capabilities.report_rate
    assert caps.readable
    assert not caps.writable
    assert caps.values == (1000, 500, 250, 125)
    assert driver.get_report_rate() == 500
    calls_before_write = list(session.calls)
    with pytest.raises(HidppError, match="unsupported report rate"):
        driver.set_report_rate(1000)
    assert session.calls == calls_before_write


def test_report_rate_is_writable_in_host_mode():
    driver = Hidpp20Driver(FakeSession(profile_mode=0x02), 1)
    assert driver.capabilities.report_rate.writable
    assert driver.set_report_rate(1000) == 1000


def test_driver_rejects_invalid_dpi_and_verification_mismatch():
    driver = Hidpp20Driver(FakeSession(), 1)
    with pytest.raises(HidppError, match="unsupported DPI"):
        driver.set_dpi(1234)
    driver = Hidpp20Driver(FakeSession(mismatch=True), 1)
    with pytest.raises(HidppError, match="verification failed"):
        driver.set_dpi(1500)


def test_onboard_profiles_v0_supports_dpi_events():
    class VersionZeroProfiles(FakeSession):
        def request(self, device, feature, function, parameters=b""):
            response = super().request(device, feature, function, parameters)
            if (feature == 0 and function == 0 and
                    int.from_bytes(parameters[:2], "big") == ONBOARD_PROFILES_FEATURE_ID):
                return HidppReport(response.report_id, device, feature, function,
                                   response.software_id,
                                   bytes((response.parameters[0], 0, 0)))
            return response

    driver = Hidpp20Driver(VersionZeroProfiles(profile_mode=0x01), 1)
    assert driver.features[ONBOARD_PROFILES_FEATURE_ID].version == 0
    assert driver.capabilities.dpi.events
    assert not driver.capabilities.report_rate.writable


def test_profile_event_is_resolved_by_live_dpi_query():
    session = FakeSession()
    driver = Hidpp20Driver(session, 1)
    stop, states = threading.Event(), []
    thread = threading.Thread(target=driver.watch_dpi, args=(states.append, stop))
    thread.start()
    while not session.callbacks:
        time.sleep(0.001)
    session.dpi = 2000
    session.callbacks[0](HidppReport(0x11, 1, 0x12, 1, 0, b"\x04"))
    while not states:
        time.sleep(0.001)
    stop.set(); thread.join(timeout=1)
    assert states == [DpiState(2000, 2000, active_stage=4, confirmed=True)]


def test_optional_dpi_discovery_failure_keeps_report_rate():
    class BrokenDpi(FakeSession):
        def request(self, device, feature, function, parameters=b""):
            if feature == 0x19 and function == 1:
                raise HidppError("DPI list unavailable")
            return super().request(device, feature, function, parameters)

    driver = Hidpp20Driver(BrokenDpi(), 1)
    assert not driver.capabilities.dpi.readable
    assert driver.capabilities.report_rate.readable


def test_report_rate_does_not_claim_writes_without_mode_evidence():
    class NoProfiles(FakeSession):
        def request(self, device, feature, function, parameters=b""):
            if feature == 0 and function == 0 and int.from_bytes(parameters[:2], "big") == ONBOARD_PROFILES_FEATURE_ID:
                return HidppReport(0x11, device, feature, function, 0x0a, b"\0")
            return super().request(device, feature, function, parameters)

    session = NoProfiles()
    driver = Hidpp20Driver(session, 1)
    assert driver.capabilities.report_rate.readable
    assert not driver.capabilities.report_rate.writable
    before = list(session.calls)
    with pytest.raises(HidppError):
        driver.set_report_rate(1000)
    assert session.calls == before


def test_multiple_receiver_children_are_ambiguous():
    with pytest.raises(HidppError, match="ambiguous"):
        connect_hidpp20(FakeSession())


@pytest.mark.parametrize("responding_index", [1, 4, 0xFF])
def test_single_responder_is_selected_without_fixed_g305_index(responding_index):
    class SingleResponder(FakeSession):
        def request(self, device, feature, function, parameters=b""):
            if device != responding_index:
                raise HidppError("no response")
            return super().request(device, feature, function, parameters)

    assert connect_hidpp20(SingleResponder()).device_index == responding_index


def test_zero_responders_are_rejected():
    class NoResponders(FakeSession):
        def request(self, device, feature, function, parameters=b""):
            raise HidppError("no response")

    with pytest.raises(HidppError, match=r"no HID\+\+ 2 device index responded"):
        connect_hidpp20(NoResponders())
