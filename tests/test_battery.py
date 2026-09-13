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
    assert tray.values == [(BatteryState(percentage=83), "test")]
    assert tray.closed >= 1


def test_tray_validates_visible_percentage():
    tray = StatusNotifierTray()
    try:
        try: tray.update(BatteryState(percentage=101), "Example Mouse")
        except ValueError: pass
        else: assert False
    finally: tray.close()


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
            assert b"\xff\xff\xff\xff" in pixels
            assert b"\0\0\0\0" in pixels
            filled_counts.append(pixels.count(b"\xff\xff\xff\xff"))
        assert filled_counts == sorted(filled_counts)
        assert filled_counts[0] < filled_counts[-1]


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
    assert properties[1]["label"].value == "Example Mouse"
    assert properties[3]["label"].value == "Battery: 83%"
    assert properties[4]["label"].value == "Status: Discharging"
    assert all("G305" not in value.value and "90%" not in value.value
               for row in properties.values() for value in row.values() if value.signature == "s")


def test_status_notifier_exposes_a_standard_menu_object_path():
    assert SNI_MENU_PATH.startswith("/")
    assert SNI_MENU_PATH == "/StatusNotifierMenu"


def test_battery_menu_omits_status_when_unavailable_and_updates_with_state():
    before = battery_menu_properties("Example Mouse", BatteryState(percentage=25, status="discharging"))
    after = battery_menu_properties("Example Mouse", BatteryState(percentage=78))
    assert before[3]["label"].value == "Battery: 25%"
    assert after[3]["label"].value == "Battery: 78%"
    assert 4 in before
    assert 4 not in after


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
