import asyncio
import threading
import time

from dbus_next import Message, Variant

from mouse_control.battery import (BatteryMonitorSupervisor, StatusNotifierTray,
                                   SNI_MENU_PATH, battery_icon, battery_menu_layout,
                                   battery_menu_properties, battery_pixmap, battery_tooltip)
from mouse_control.discovery import MouseDevice
from mouse_control.hardware import BatteryState, HardwareBackend


DEVICE = MouseDevice("test", "/dev/input/test")


class Backend(HardwareBackend):
    def __init__(self, value=83, available=True): self.value, self.available = value, available
    def supports_device(self, device): return True
    def supports_battery(self, device): return self.available
    def get_battery_state(self, device):
        if not self.available: raise RuntimeError("gone")
        return BatteryState(percentage=self.value)


class Tray:
    def __init__(self): self.values = []; self.closed = 0
    def update(self, state, device_name): self.values.append((state, device_name))
    def close(self): self.closed += 1


def wait_for(predicate, timeout=1.):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.001)
    assert predicate()


class ScriptedBackend(HardwareBackend):
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = 0
        self.finished = threading.Event()
        self.release = threading.Event()

    def supports_device(self, device): return True
    def supports_battery(self, device): return True

    def get_battery_state(self, device):
        self.calls += 1
        try:
            outcome = next(self.outcomes)
        except StopIteration:
            self.finished.set()
            self.release.wait()
            raise RuntimeError("test backend stopped")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_icons_are_simple_symbolic_battery_states():
    assert battery_icon(100) == "battery-full-symbolic"
    assert battery_icon(50) == "battery-medium-symbolic"
    assert battery_icon(10) == "battery-caution-symbolic"


def test_no_capability_never_creates_a_tray_item():
    stop, tray = threading.Event(), Tray()
    monitor = BatteryMonitorSupervisor(Backend(available=False), DEVICE, lambda _: Backend(available=False), stop,
                                       tray=tray, retry_interval=.001)
    monitor.start(); time.sleep(.01); monitor.stop()
    assert tray.values == []


def test_valid_battery_updates_tray_and_cleanup_removes_it():
    stop, tray = threading.Event(), Tray()
    monitor = BatteryMonitorSupervisor(Backend(83), DEVICE, lambda _: Backend(83), stop,
                                       tray=tray, interval=10, retry_interval=.001)
    monitor.start()
    while not tray.values: time.sleep(.001)
    monitor.stop()
    assert tray.values[-1] == (BatteryState(percentage=83), "test")
    assert tray.closed >= 1


def test_tray_validates_visible_percentage():
    tray = StatusNotifierTray()
    try:
        try: tray.update(BatteryState(percentage=101), "Example Mouse")
        except ValueError: pass
        else: assert False
    finally: tray.close()


def test_tray_close_prevents_late_updates_from_resurrecting_worker():
    tray = StatusNotifierTray()
    tray.close()
    tray.update(BatteryState(percentage=50), "test")
    assert tray._thread is None
    tray.close()


def test_tooltip_uses_device_name_live_percentage_and_status():
    tooltip = battery_tooltip("Example Mouse", BatteryState(percentage=90, status="discharging"))
    assert tooltip[2] == "Example Mouse"
    assert "90%" in tooltip[3]
    assert "Status: Discharging" in tooltip[3]


def test_tooltip_updates_with_the_battery_state_used_by_the_icon():
    device_name = "Example Mouse"
    before = BatteryState(percentage=25, status="discharging")
    after = BatteryState(percentage=90, status="charging")
    assert "25%" in battery_tooltip(device_name, before)[3]
    assert "90%" in battery_tooltip(device_name, after)[3]
    assert battery_pixmap(before.percentage, 16) != battery_pixmap(after.percentage, 16)


def test_pixmap_fill_grows_with_charge_at_common_tray_sizes():
    for height in (16, 20, 22, 24, 32):
        filled_counts = []
        for percentage in (0, 10, 25, 50, 75, 100):
            pixmap = battery_pixmap(percentage, height)
            assert isinstance(pixmap, list)
            width, actual_height, pixels = pixmap
            assert width == actual_height == height
            assert isinstance(pixels, bytes)
            assert len(pixels) == width * height * 4
            assert any(pixels[index] == 255 for index in range(0, len(pixels), 4))
            assert b"\0\0\0\0" in pixels
            filled_counts.append(sum(pixels[index] for index in range(0, len(pixels), 4)))
        assert filled_counts == sorted(filled_counts)
        assert filled_counts[0] < filled_counts[-1]


def test_pixmap_is_deterministic_transparent_and_uses_omus_gradient():
    for height in (16, 20, 22, 24, 32):
        for percentage in (0, 10, 50, 100):
            first = battery_pixmap(percentage, height)
            assert first == battery_pixmap(percentage, height)
            pixels = first[2]
            assert pixels[:4] == b"\0\0\0\0"
            opaque_colors = {tuple(pixels[index + 1:index + 4])
                             for index in range(0, len(pixels), 4)
                             if pixels[index] == 255}
            assert opaque_colors
            assert all(blue > green and red > green for red, green, blue in opaque_colors)
            if percentage:
                assert len(opaque_colors) > 1


def test_pixmap_rejects_invalid_percentage_and_dimensions():
    for percentage, height in ((-1, 16), (101, 16), (50, 15), (50, 0)):
        try:
            battery_pixmap(percentage, height)
        except ValueError:
            pass
        else:
            assert False, (percentage, height)


def test_sni_icon_pixmap_uses_dbus_next_struct_and_byte_array_shapes():
    for percentage in (0, 10, 25, 50, 75, 100):
        pixmaps = [battery_pixmap(percentage, size) for size in (16, 20, 22, 24, 32)]
        variant = Variant("a(iiay)", pixmaps)
        assert variant.value == pixmaps


def test_sni_tooltip_uses_the_dbus_next_status_notifier_signature():
    tooltip = battery_tooltip("Example Mouse", BatteryState(percentage=90, status="discharging"))
    variant = Variant("(sa(iiay)ss)", tooltip)
    assert variant.value == tooltip


def test_battery_menu_contains_live_identity_percentage_and_status():
    properties = battery_menu_properties("Example Mouse", BatteryState(percentage=83, status="discharging"))
    assert properties[1]["label"].value == "Battery: 83%"
    assert properties[2]["label"].value == "Status: Discharging"
    assert all("G305" not in value.value and "90%" not in value.value
               for row in properties.values() for value in row.values() if value.signature == "s")


def test_device_name_does_not_appear_in_tray_menu():
    """Device name must not appear in tray menu labels."""
    properties = battery_menu_properties("G305 Gaming Mouse", BatteryState(percentage=83, status="discharging"))
    for row_values in properties.values():
        for value in row_values.values():
            if value.signature == "s":
                assert "G305" not in value.value
                assert "Gaming" not in value.value
                assert "Mouse" not in value.value


def test_status_notifier_exposes_a_standard_menu_object_path():
    assert SNI_MENU_PATH.startswith("/")
    assert SNI_MENU_PATH == "/StatusNotifierMenu"


def test_battery_menu_omits_status_when_unavailable_and_updates_with_state():
    before = battery_menu_properties("Example Mouse", BatteryState(percentage=25, status="discharging"))
    after = battery_menu_properties("Example Mouse", BatteryState(percentage=78))
    assert before[1]["label"].value == "Battery: 25%"
    assert after[1]["label"].value == "Battery: 78%"
    assert 2 in before
    assert 2 not in after


def test_transient_failures_keep_last_known_battery_visible():
    stop, tray = threading.Event(), Tray()
    backend = ScriptedBackend([BatteryState(percentage=75), RuntimeError("timeout"),
                               RuntimeError("timeout")])
    monitor = BatteryMonitorSupervisor(backend, DEVICE, lambda _: backend, stop, tray=tray,
                                       interval=.001, retry_interval=.001)
    monitor.start()
    try:
        wait_for(backend.finished.is_set)
        assert tray.values[-1] == (BatteryState(percentage=75), "test")
        assert tray.closed == 0
        assert monitor._consecutive_failures == 2
    finally:
        backend.release.set()
        monitor.stop()


def test_third_consecutive_failure_keeps_unknown_tray():
    stop, tray = threading.Event(), Tray()
    backend = ScriptedBackend([BatteryState(percentage=75), RuntimeError("timeout"),
                               RuntimeError("timeout"), RuntimeError("timeout")])
    monitor = BatteryMonitorSupervisor(backend, DEVICE, lambda _: backend, stop, tray=tray,
                                       interval=.001, retry_interval=.001)
    monitor.start()
    try:
        wait_for(backend.finished.is_set)
        assert tray.closed == 0
        assert tray.values[-1][0].percentage is None
        assert monitor._consecutive_failures == 3
    finally:
        backend.release.set()
        monitor.stop()


def test_successful_read_resets_failure_counter():
    stop, tray = threading.Event(), Tray()
    backend = ScriptedBackend([BatteryState(percentage=60), RuntimeError("timeout"),
                               RuntimeError("timeout"), BatteryState(percentage=61),
                               RuntimeError("timeout"), RuntimeError("timeout")])
    monitor = BatteryMonitorSupervisor(backend, DEVICE, lambda _: backend, stop, tray=tray,
                                       interval=.001, retry_interval=.001)
    monitor.start()
    try:
        wait_for(backend.finished.is_set)
        assert [state.percentage for state, _ in tray.values] == [None, 60, 61]
        assert tray.closed == 0
        assert monitor._consecutive_failures == 2
    finally:
        backend.release.set()
        monitor.stop()


def test_battery_menu_layout_has_valid_dbusmenu_struct_and_variant_shapes():
    layout = battery_menu_layout("Example Mouse", BatteryState(percentage=83, status="charging"))
    layout_variant = Variant("(ia{sv}av)", layout)
    assert layout_variant.value == layout
    reply = Message(path="/StatusNotifierMenu", interface="com.canonical.dbusmenu",
                    member="GetLayout", signature="u(ia{sv}av)", body=[1, layout])
    assert reply._marshall()
    properties = battery_menu_properties("Example Mouse", BatteryState(percentage=83))
    group_variant = Variant("a(ia{sv})", [[item_id, values] for item_id, values in properties.items()])
    assert group_variant.value[0][0] == 1


def test_battery_absent_at_boot_recovers_without_restarting_monitor():
    stop, tray = threading.Event(), Tray()
    backend = Backend(available=False)
    backend.discovery_pending = True
    monitor = BatteryMonitorSupervisor(backend, DEVICE, lambda _: backend, stop, tray=tray,
                                       interval=.01, retry_interval=.001)
    monitor.start()
    try:
        wait_for(lambda: bool(tray.values))
        assert tray.values[-1][0].percentage is None
        original_thread = monitor._thread
        monitor.start()
        assert monitor._thread is original_thread
        backend.available = True
        wait_for(lambda: tray.values[-1][0].percentage == 83)
        assert tray.closed == 0
    finally:
        monitor.stop()
    assert not original_thread.is_alive()


def test_unknown_battery_exports_valid_tooltip_and_menu():
    state = BatteryState(percentage=None, status="unavailable")
    assert 'Unknown' in battery_tooltip('test', state)[3]
    assert battery_menu_properties('test', state)[1]['label'].value == 'Battery: Unknown'
    Variant('(ia{sv}av)', battery_menu_layout('test', state))
