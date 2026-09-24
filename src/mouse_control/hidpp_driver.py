# SPDX-License-Identifier: AGPL-3.0-or-later
"""Native Logitech HID++ 2 protocol driver.

The implementation is independent and based on observed HID++ wire behavior;
feature-table indexes are always resolved live through ROOT.
"""

from __future__ import annotations

import queue
import threading
import logging
from collections.abc import Callable

from .hardware.capabilities import (BatteryCapabilities, BatteryState,
                                    DpiCapabilities, DpiRange, DpiState,
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
UNIFIED_BATTERY_FEATURE_ID = 0x1004
BATTERY_STATUS_FEATURE_ID = 0x1000
BATTERY_VOLTAGE_FEATURE_ID = 0x1001
ONBOARD_MODE = 0x01
HOST_MODE = 0x02


def decode_unified_battery(parameters: bytes) -> BatteryState:
    """Decode HID++ Unified Battery getStatus response for the validated layout.

    Byte zero is the percentage.  The following bytes are status/routing data
    and are not exposed until their semantics are independently validated.
    """
    if not parameters:
        raise HidppError("malformed unified-battery response")
    percentage = parameters[0]
    if not 0 <= percentage <= 100:
        raise HidppError("unified-battery percentage is outside 0..100")
    return BatteryState(percentage=percentage)


def decode_battery_status(parameters: bytes) -> BatteryState:
    """Decode 0x1000 getBatteryLevelStatus: level, next level, status."""
    if len(parameters) < 3 or not 0 <= parameters[0] <= 100:
        raise HidppError("invalid battery-status response")
    statuses = {0: "discharging", 1: "recharging", 2: "almost full", 3: "full"}
    return BatteryState(percentage=parameters[0], status=statuses.get(parameters[2]))


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


def decode_extended_dpi_parameters(parameters: bytes) -> tuple[int, int, int, int, int, int]:
    """Decode HID++ 0x2202 get_sensor_dpi_parameters (function 5)."""
    if len(parameters) < 10:
        raise HidppError("malformed extended-DPI parameters response")
    sensor = parameters[0]
    dpi_x = int.from_bytes(parameters[1:3], "big")
    default_x = int.from_bytes(parameters[3:5], "big")
    dpi_y = int.from_bytes(parameters[5:7], "big")
    default_y = int.from_bytes(parameters[7:9], "big")
    lod = parameters[9]
    if dpi_x <= 0 or default_x <= 0 or lod not in (0, 1, 2, 3):
        raise HidppError("invalid extended-DPI parameters response")
    return sensor, dpi_x, default_x, dpi_y, default_y, lod


def decode_extended_dpi_ranges(words: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[DpiRange, ...]]:
    """Decode one validated 0x2202 DPI range stream."""
    values: list[int] = []
    ranges: list[DpiRange] = []
    index = 0
    while index < len(words):
        word = int(words[index])
        if word == 0:
            break
        if word & 0xE000 == 0xE000:
            if not values or index + 1 >= len(words):
                raise HidppError("malformed extended-DPI stepped range")
            step = word & 0x1FFF
            maximum = int(words[index + 1])
            if step <= 0 or maximum <= 0 or maximum < values[-1]:
                raise HidppError("invalid extended-DPI stepped range")
            ranges.append(DpiRange(values[-1], maximum, step))
            index += 2
            continue
        if word <= 0 or word > 0xDFFF:
            raise HidppError("invalid extended-DPI fixed value")
        if word not in values:
            values.append(word)
        index += 1
    if not values and not ranges:
        raise HidppError("device returned no extended-DPI values")
    return tuple(values), tuple(ranges)


class Hidpp20Driver:
    protocol_name = "Logitech HID++ 2"

    def __init__(self, session: HidSession, device_index: int, *,
                 _probed_version: tuple[int, int] | None = None) -> None:
        self.session, self.device_index = session, device_index
        protocol = (_probed_version if _probed_version is not None
                    else get_protocol_version(session, device_index))
        if protocol is None:
            raise HidppError("device is not HID++ 2")
        self.protocol_version = protocol
        self.features: dict[int, HidppFeature] = {}
        for feature_id in (DEVICE_NAME_FEATURE_ID, ADJUSTABLE_DPI_FEATURE_ID,
                           EXTENDED_ADJUSTABLE_DPI_FEATURE_ID,
                           ONBOARD_PROFILES_FEATURE_ID, REPORT_RATE_FEATURE_ID,
                           MODE_STATUS_FEATURE_ID, MOUSE_BUTTON_SPY_FEATURE_ID,
                           UNIFIED_BATTERY_FEATURE_ID, BATTERY_STATUS_FEATURE_ID,
                           BATTERY_VOLTAGE_FEATURE_ID):
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
        try:
            self._battery_capabilities = self._discover_battery()
        except HidppError:
            self._battery_capabilities = BatteryCapabilities()

    def _discover_dpi(self) -> DpiCapabilities:
        feature = self.features.get(ADJUSTABLE_DPI_FEATURE_ID)
        if feature is not None:
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

        extended = self.features.get(EXTENDED_ADJUSTABLE_DPI_FEATURE_ID)
        if extended is None:
            return DpiCapabilities()
        count = self.session.request(self.device_index, extended.index, 0x00)
        if not count.parameters or count.parameters[0] == 0:
            raise HidppError("device returned no extended-DPI sensors")
        capabilities = self.session.request(
            self.device_index, extended.index, 0x01, b"\0"
        ).parameters
        if len(capabilities) < 3 or capabilities[0] != 0:
            raise HidppError("malformed extended-DPI capability response")
        level_count, flags = capabilities[1], capabilities[2]
        independent_axes = bool(flags & 0x01)

        words: list[int] = []
        terminated = False
        for page in range(16):
            response = self.session.request(
                self.device_index, extended.index, 0x02, bytes((0, 0, page))
            ).parameters
            if len(response) < 3 or tuple(response[:3]) != (0, 0, page):
                raise HidppError("extended-DPI range page echo mismatch")
            payload = response[3:]
            for offset in range(0, len(payload) - 1, 2):
                word = int.from_bytes(payload[offset:offset + 2], "big")
                words.append(word)
                if word == 0:
                    terminated = True
                    break
            if terminated:
                break
        if not terminated:
            raise HidppError("extended-DPI range stream did not terminate")
        values, ranges = decode_extended_dpi_ranges(tuple(words))
        return DpiCapabilities(
            readable=True, writable=True, values=values, ranges=ranges,
            independent_axes=independent_axes, stage_count=level_count or None,
            events=True,
        )

    @property
    def capabilities(self) -> HardwareCapabilities:
        return HardwareCapabilities(dpi=self._dpi_capabilities,
                                    report_rate=self._report_rate_capabilities,
                                    battery=self._battery_capabilities)

    def _discover_battery(self) -> BatteryCapabilities:
        # A ROOT-discovered but unknown battery feature is not support.  This
        # protects us from treating similar-looking HID++ generations alike.
        feature = self.features.get(UNIFIED_BATTERY_FEATURE_ID)
        if feature is None:
            feature = self.features.get(BATTERY_STATUS_FEATURE_ID)
            if feature is None:
                return BatteryCapabilities()
            state = self._read_battery_status(feature)
        else:
            state = self._read_unified_battery(feature)
        return BatteryCapabilities(readable=state.percentage is not None, percentage=True)

    def _read_battery_status(self, feature: HidppFeature) -> BatteryState:
        parameters = self.session.request(self.device_index, feature.index, 0x00).parameters
        state = decode_battery_status(parameters)
        LOG.debug("HID++ 0x1000 raw battery parameters=%s decoded percentage=%s status=%s",
                  parameters.hex(" "), state.percentage, state.status)
        return state

    def _read_unified_battery(self, feature: HidppFeature | None = None) -> BatteryState:
        feature = feature or self.features.get(UNIFIED_BATTERY_FEATURE_ID)
        if feature is None:
            raise HidppError("unified battery is unsupported")
        parameters = self.session.request(self.device_index, feature.index, 0x00).parameters
        state = decode_unified_battery(parameters)
        LOG.debug("HID++ 0x1004 raw battery parameters=%s decoded percentage=%s status=%s",
                  parameters.hex(" "), state.percentage, state.status)
        return state

    def get_battery_state(self) -> BatteryState:
        if not self._battery_capabilities.readable:
            raise HidppError("battery status is unsupported")
        feature = self.features.get(UNIFIED_BATTERY_FEATURE_ID)
        if feature is not None:
            return self._read_unified_battery(feature)
        return self._read_battery_status(self.features[BATTERY_STATUS_FEATURE_ID])

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
        # The driver describes protocol mechanics. Whether OMUS may
        # enter Host mode is a device-specific policy decision in the backend.
        writable = ONBOARD_PROFILES_FEATURE_ID in self.features
        return ReportRateCapabilities(readable=bool(values), writable=writable,
                                      values=values)

    def get_control_mode(self) -> int:
        feature = self.features.get(ONBOARD_PROFILES_FEATURE_ID)
        if feature is None:
            raise HidppError("onboard-profiles control mode is unsupported")
        response = self.session.request(self.device_index, feature.index, 0x02)
        if not response.parameters or response.parameters[0] not in (ONBOARD_MODE, HOST_MODE):
            raise HidppError("malformed onboard-profiles mode response")
        return response.parameters[0]

    def set_control_mode(self, mode: int) -> None:
        if mode not in (ONBOARD_MODE, HOST_MODE):
            raise HidppError(f"invalid onboard-profiles control mode 0x{mode:02x}")
        feature = self.features.get(ONBOARD_PROFILES_FEATURE_ID)
        if feature is None:
            raise HidppError("onboard-profiles control mode is unsupported")
        self.session.request(self.device_index, feature.index, 0x01, bytes((mode,)))

    def get_dpi_state(self, *, active_stage: int | None = None) -> DpiState:
        feature = self.features.get(ADJUSTABLE_DPI_FEATURE_ID)
        if feature is not None:
            response = self.session.request(self.device_index, feature.index, 0x02, b"\0")
            if len(response.parameters) < 3 or response.parameters[0] != 0:
                raise HidppError("malformed current-DPI response")
            dpi = int.from_bytes(response.parameters[1:3], "big")
            if dpi <= 0:
                raise HidppError("device returned invalid current DPI")
            return DpiState(dpi, dpi, active_stage=active_stage, confirmed=True)

        extended = self.features.get(EXTENDED_ADJUSTABLE_DPI_FEATURE_ID)
        if extended is None:
            raise HidppError("adjustable DPI is unsupported")
        parameters = self.session.request(
            self.device_index, extended.index, 0x05, b"\0"
        ).parameters
        sensor, dpi_x, _default_x, dpi_y, _default_y, _lod = decode_extended_dpi_parameters(parameters)
        if sensor != 0:
            raise HidppError("extended-DPI sensor echo mismatch")
        return DpiState(dpi_x, dpi_y or None, active_stage=active_stage, confirmed=True)

    def set_dpi(self, dpi: int) -> DpiState:
        if not self._dpi_capabilities.writable or not self._dpi_capabilities.accepts(dpi):
            raise HidppError(f"unsupported DPI {dpi}")
        feature = self.features.get(ADJUSTABLE_DPI_FEATURE_ID)
        if feature is not None:
            self.session.request(self.device_index, feature.index, 0x03,
                                 bytes((0,)) + dpi.to_bytes(2, "big"))
        else:
            extended = self.features.get(EXTENDED_ADJUSTABLE_DPI_FEATURE_ID)
            if extended is None:
                raise HidppError("adjustable DPI is unsupported")
            current = self.session.request(
                self.device_index, extended.index, 0x05, b"\0"
            ).parameters
            sensor, _x, _default_x, _y, _default_y, lod = decode_extended_dpi_parameters(current)
            if sensor != 0:
                raise HidppError("extended-DPI sensor echo mismatch")
            y_dpi = dpi if self._dpi_capabilities.independent_axes else 0
            payload = (bytes((0,)) + dpi.to_bytes(2, "big")
                       + y_dpi.to_bytes(2, "big") + bytes((lod,)))
            self.session.request(self.device_index, extended.index, 0x06, payload)
        state = self.get_dpi_state()
        expected_y = dpi if self._dpi_capabilities.independent_axes else None
        if state.x_dpi != dpi or (expected_y is not None and state.y_dpi != expected_y):
            raise HidppError(
                f"DPI verification failed: requested {dpi}, read {state.display_value}")
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
        extended = self.features.get(EXTENDED_ADJUSTABLE_DPI_FEATURE_ID)
        legacy_events = (
            ADJUSTABLE_DPI_FEATURE_ID in self.features
            and profile is not None and profile.version in (0, 1)
        )
        extended_events = (
            ADJUSTABLE_DPI_FEATURE_ID not in self.features and extended is not None
        )
        if not self._dpi_capabilities.events or not (legacy_events or extended_events):
            raise HidppError("DPI events are unsupported")
        pending: queue.Queue[int | DpiState] = queue.Queue()

        def receive(report: HidppReport) -> None:
            if legacy_events and profile is not None and (
                    report.device_index == self.device_index and
                    report.report_id == 0x11 and report.feature_index == profile.index and
                    report.function_or_event == 0x01 and report.software_id == 0 and
                    report.parameters and report.parameters[0] < 16):
                pending.put(report.parameters[0])
                return
            if extended_events and extended is not None and (
                    report.device_index == self.device_index and
                    report.report_id == 0x11 and report.feature_index == extended.index and
                    report.function_or_event == 0x00 and report.software_id == 0 and
                    len(report.parameters) >= 6):
                sensor = report.parameters[0]
                x_dpi = int.from_bytes(report.parameters[1:3], "big")
                y_dpi = int.from_bytes(report.parameters[3:5], "big")
                lod = report.parameters[5]
                if sensor == 0 and x_dpi > 0 and lod in (0, 1, 2, 3):
                    pending.put(DpiState(x_dpi, y_dpi or None, confirmed=True))

        unsubscribe = self.session.subscribe(receive)
        try:
            if ready_callback is not None:
                ready_callback()
            while not shutdown_event.is_set():
                if getattr(self.session, "closed", False):
                    raise HidppError("HID session disconnected")
                try:
                    item = pending.get(timeout=0.25)
                except queue.Empty:
                    continue
                if isinstance(item, DpiState):
                    callback(item)
                else:
                    # Legacy profile events carry routing/stage data only;
                    # query hardware for the authoritative current DPI.
                    callback(self.get_dpi_state(active_stage=item))
        finally:
            unsubscribe()



def connect_hidpp20(session: HidSession) -> Hidpp20Driver:
    last_error: Exception | None = None
    found: list[Hidpp20Driver] = []
    candidates = (*range(1, 7), 0xFF)
    probe = getattr(type(session), "probe_protocol_versions", None)
    versions = probe(session, candidates) if callable(probe) else None
    # A single-reader native session can overlap independent read-only probes.
    # Compatibility transports retain their existing serial API.
    for candidate in candidates:
        if versions is not None and candidate not in versions:
            continue
        try:
            found.append(Hidpp20Driver(
                session, candidate,
                _probed_version=versions[candidate] if versions is not None else None))
        except HidppError as exc:
            last_error = exc
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        raise HidppError("multiple HID++ devices responded on one interface; identity is ambiguous")
    raise HidppError(f"no HID++ 2 device index responded: {last_error}")
