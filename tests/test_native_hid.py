from pathlib import Path
import queue
import threading
import time

import pytest

from mouse_control.hardware.capabilities import DpiState
from mouse_control.hid_session import HidSession
from mouse_control.hidpp import HidppError, HidppReport
from mouse_control.hidpp_driver import (ADJUSTABLE_DPI_FEATURE_ID,
    ONBOARD_PROFILES_FEATURE_ID, REPORT_RATE_FEATURE_ID, Hidpp20Driver,
    decode_supported_dpi)


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


class FakeSession:
    def __init__(self, *, mismatch=False):
        self.dpi = 800
        self.rate_ms = 2
        self.mismatch = mismatch
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


def test_driver_rejects_invalid_dpi_and_verification_mismatch():
    driver = Hidpp20Driver(FakeSession(), 1)
    with pytest.raises(HidppError, match="unsupported DPI"):
        driver.set_dpi(1234)
    driver = Hidpp20Driver(FakeSession(mismatch=True), 1)
    with pytest.raises(HidppError, match="verification failed"):
        driver.set_dpi(1500)


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
