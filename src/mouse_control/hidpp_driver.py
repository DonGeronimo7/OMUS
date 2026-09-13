"""Native Logitech HID++ 2 protocol driver.

The implementation is independent and based on observed HID++ wire behavior;
feature-table indexes are always resolved live through ROOT.
"""

from __future__ import annotations

import queue
import threading
import logging
from collections.abc import Callable

from .hardware.capabilities import (DpiCapabilities, DpiRange, DpiState,
                                    HardwareCapabilities, ReportRateCapabilities)
from .hid_session import HidSession
from .hidpp import (ADJUSTABLE_DPI_FEATURE_ID, DEVICE_NAME_FEATURE_ID,
                    HidppError, HidppFeature, HidppReport, get_device_name,
                    get_protocol_version, lookup_feature)

LOG = logging.getLogger(__name__)

EXTENDED_ADJUSTABLE_DPI_FEATURE_ID = 0x2202
ONBOARD_PROFILES_FEATURE_ID = 0x8100
REPORT_RATE_FEATURE_ID = 0x8060
MOUSE_BUTTON_SPY_FEATURE_ID = 0x8110
MODE_STATUS_FEATURE_ID = 0x8090


def decode_supported_dpi(parameters: bytes) -> tuple[tuple[int, ...], tuple[DpiRange, ...]]:
    """Decode getSensorDpiList's explicit values and E000 range markers."""
    if not parameters:
        raise HidppError("malformed supported-DPI response")
    payload = parameters[1:]
    words = [int.from_bytes(payload[offset:offset + 2], "big")
             for offset in range(0, len(payload) - 1, 2)]
    words = words[:words.index(0)] if 0 in words else words
    values: list[int] = []
    ranges: list[DpiRange] = []
    index = 0
    while index < len(words):
        word = words[index]
        if word & 0xE000 == 0xE000:
            if not values or index + 1 >= len(words):
                raise HidppError("malformed supported-DPI range")
            step, maximum = word & 0x1FFF, words[index + 1]
            if step <= 0 or maximum < values[-1]:
                raise HidppError("invalid supported-DPI range")
            ranges.append(DpiRange(values[-1], maximum, step))
            index += 2
            continue
        if word <= 0:
            raise HidppError("invalid supported-DPI value")
        if word not in values:
            values.append(word)
        index += 1
    if not values and not ranges:
        raise HidppError("device returned no supported DPI values")
    return tuple(values), tuple(ranges)


class Hidpp20Driver:
    protocol_name = "Logitech HID++ 2"

    def __init__(self, session: HidSession, device_index: int) -> None:
        self.session, self.device_index = session, device_index
        protocol = get_protocol_version(session, device_index)
        if protocol is None:
            raise HidppError("device is not HID++ 2")
        self.protocol_version = protocol
        self.features: dict[int, HidppFeature] = {}
        for feature_id in (DEVICE_NAME_FEATURE_ID, ADJUSTABLE_DPI_FEATURE_ID,
                           EXTENDED_ADJUSTABLE_DPI_FEATURE_ID,
                           ONBOARD_PROFILES_FEATURE_ID, REPORT_RATE_FEATURE_ID,
                           MODE_STATUS_FEATURE_ID, MOUSE_BUTTON_SPY_FEATURE_ID):
            try:
                feature = lookup_feature(session, device_index, feature_id)
            except HidppError:
                continue
            if feature is not None:
                self.features[feature_id] = feature
        name_feature = self.features.get(DEVICE_NAME_FEATURE_ID)
        try:
            self.name = get_device_name(session, device_index, name_feature) if name_feature else None
        except HidppError:
            self.name = None
        try:
            self._dpi_capabilities = self._discover_dpi()
        except HidppError:
            self._dpi_capabilities = DpiCapabilities()
        try:
            self._report_rate_capabilities = self._discover_report_rate()
        except HidppError:
            self._report_rate_capabilities = ReportRateCapabilities()

    def _discover_dpi(self) -> DpiCapabilities:
        feature = self.features.get(ADJUSTABLE_DPI_FEATURE_ID)
        if feature is None:
            # 0x2202 is represented but not claimed until its independent-axis
            # packet format is implemented and validated.
            return DpiCapabilities()
        count = self.session.request(self.device_index, feature.index, 0x00)
        if not count.parameters or count.parameters[0] == 0:
            raise HidppError("device returned no adjustable-DPI sensors")
        response = self.session.request(self.device_index, feature.index, 0x01, b"\0")
        values, ranges = decode_supported_dpi(response.parameters)
        profiles = self.features.get(ONBOARD_PROFILES_FEATURE_ID)
        return DpiCapabilities(
            readable=True, writable=True, values=values, ranges=ranges,
            events=profiles is not None and profiles.version in (0, 1),
        )

    @property
    def capabilities(self) -> HardwareCapabilities:
        return HardwareCapabilities(dpi=self._dpi_capabilities,
                                    report_rate=self._report_rate_capabilities)

    def _discover_report_rate(self) -> ReportRateCapabilities:
        feature = self.features.get(REPORT_RATE_FEATURE_ID)
        if feature is None:
            return ReportRateCapabilities()
        response = self.session.request(self.device_index, feature.index, 0x00)
        if not response.parameters:
            raise HidppError("malformed report-rate response")
        flags = response.parameters[0]
        values = tuple(1000 // milliseconds for milliseconds in range(1, 9)
                       if flags & (1 << (milliseconds - 1)))
        profiles = self.features.get(ONBOARD_PROFILES_FEATURE_ID)
        writable = False
        if profiles is not None:
            mode = self.session.request(self.device_index, profiles.index, 0x02)
            if not mode.parameters or mode.parameters[0] not in (0x01, 0x02):
                raise HidppError("malformed onboard-profiles mode response")
            writable = mode.parameters[0] == 0x02
        return ReportRateCapabilities(readable=bool(values), writable=writable,
                                      values=values)

    def get_dpi_state(self, *, active_stage: int | None = None) -> DpiState:
        feature = self.features.get(ADJUSTABLE_DPI_FEATURE_ID)
        if feature is None:
            raise HidppError("adjustable DPI is unsupported")
        response = self.session.request(self.device_index, feature.index, 0x02, b"\0")
        if len(response.parameters) < 3 or response.parameters[0] != 0:
            raise HidppError("malformed current-DPI response")
        dpi = int.from_bytes(response.parameters[1:3], "big")
        if dpi <= 0:
            raise HidppError("device returned invalid current DPI")
        return DpiState(dpi, dpi, active_stage=active_stage, confirmed=True)

    def set_dpi(self, dpi: int) -> DpiState:
        if not self._dpi_capabilities.writable or not self._dpi_capabilities.accepts(dpi):
            raise HidppError(f"unsupported DPI {dpi}")
        feature = self.features[ADJUSTABLE_DPI_FEATURE_ID]
        self.session.request(self.device_index, feature.index, 0x03,
                             bytes((0,)) + dpi.to_bytes(2, "big"))
        state = self.get_dpi_state()
        if state.x_dpi != dpi:
            raise HidppError(f"DPI verification failed: requested {dpi}, read {state.x_dpi}")
        return state

    def get_report_rate(self) -> int:
        feature = self.features.get(REPORT_RATE_FEATURE_ID)
        if feature is None:
            raise HidppError("report rate is unsupported")
        response = self.session.request(self.device_index, feature.index, 0x01)
        if not response.parameters or response.parameters[0] == 0 or 1000 % response.parameters[0]:
            raise HidppError("malformed report-rate response")
        return 1000 // response.parameters[0]

    def set_report_rate(self, hz: int) -> int:
        caps = self._report_rate_capabilities
        if not caps.writable or caps.values is None or hz not in caps.values:
            raise HidppError(f"unsupported report rate {hz} Hz")
        milliseconds = 1000 // hz
        feature = self.features[REPORT_RATE_FEATURE_ID]
        self.session.request(self.device_index, feature.index, 0x02,
                             bytes((milliseconds,)))
        actual = self.get_report_rate()
        if actual != hz:
            raise HidppError(f"report-rate verification failed: requested {hz}, read {actual}")
        return actual

    def watch_dpi(self, callback: Callable[[DpiState], None],
                  shutdown_event: threading.Event,
                  ready_callback: Callable[[], None] | None = None) -> None:
        profile = self.features.get(ONBOARD_PROFILES_FEATURE_ID)
        if profile is None or not self._dpi_capabilities.events:
            raise HidppError("DPI events are unsupported")
        pending: queue.Queue[int] = queue.Queue()

        def receive(report: HidppReport) -> None:
            if (report.device_index == self.device_index and
                    report.report_id == 0x11 and report.feature_index == profile.index and
                    report.function_or_event == 0x01 and report.software_id == 0 and
                    report.parameters and report.parameters[0] < 16):
                stage = report.parameters[0]
                pending.put(stage)

        unsubscribe = self.session.subscribe(receive)
        try:
            # Subscription registration, rather than thread creation, is the
            # point at which the monitor may advertise that it can receive a
            # physical button transition.
            if ready_callback is not None:
                ready_callback()
            while not shutdown_event.is_set():
                if getattr(self.session, "closed", False):
                    raise HidppError("HID session disconnected")
                try:
                    stage = pending.get(timeout=0.25)
                except queue.Empty:
                    continue
                # The event's slot is routing data. Query hardware for truth.
                state = self.get_dpi_state(active_stage=stage)
                callback(state)
        finally:
            unsubscribe()


def connect_hidpp20(session: HidSession) -> Hidpp20Driver:
    last_error: Exception | None = None
    found: list[Hidpp20Driver] = []
    for candidate in (*range(1, 7), 0xFF):
        try:
            found.append(Hidpp20Driver(session, candidate))
        except HidppError as exc:
            last_error = exc
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        raise HidppError("multiple HID++ devices responded on one interface; identity is ambiguous")
    raise HidppError(f"no HID++ 2 device index responded: {last_error}")
