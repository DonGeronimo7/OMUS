# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auditable USB HID Usage Tables 1.7 ontology used by interpretation.

The database intentionally describes standardized usages only. Vendor-defined
pages remain opaque and no usage name grants protocol or write authority.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class HidUsage:
    page: int
    usage: int

@dataclass(frozen=True)
class HidUsageInfo:
    usage: HidUsage
    page_name: str
    usage_name: str
    category: str

_PAGES = {
    0x01: "Generic Desktop", 0x02: "Simulation Controls", 0x03: "VR Controls",
    0x04: "Sport Controls", 0x05: "Game Controls", 0x06: "Generic Device Controls",
    0x07: "Keyboard/Keypad", 0x08: "LED", 0x09: "Button", 0x0A: "Ordinal",
    0x0B: "Telephony", 0x0C: "Consumer", 0x0D: "Digitizers", 0x0E: "Haptics",
    0x0F: "Physical Input Device", 0x10: "Unicode", 0x12: "Eye and Head Trackers",
    0x14: "Auxiliary Display", 0x20: "Sensors", 0x40: "Medical Instruments",
    0x41: "Braille Display", 0x59: "Lighting and Illumination",
    0x80: "Monitor", 0x81: "Monitor Enumerated", 0x82: "VESA Virtual Controls",
    0x84: "Power", 0x85: "Battery System", 0x8C: "Barcode Scanner",
    0x8D: "Scale", 0x8E: "Magnetic Stripe Reader", 0x90: "Camera Control",
    0x91: "Arcade", 0x92: "Gaming Device",
}
_USAGES = {
    (1, 0x01): ("Pointer", "pointer"), (1, 0x02): ("Mouse", "mouse"),
    (1, 0x04): ("Joystick", "pointer"), (1, 0x05): ("Game Pad", "pointer"),
    (1, 0x06): ("Keyboard", "keyboard"), (1, 0x07): ("Keypad", "keyboard"),
    (1, 0x08): ("Multi-axis Controller", "pointer"),
    (1, 0x30): ("X", "axis"), (1, 0x31): ("Y", "axis"),
    (1, 0x32): ("Z", "axis"), (1, 0x33): ("Rx", "axis"),
    (1, 0x34): ("Ry", "axis"), (1, 0x35): ("Rz", "axis"),
    (1, 0x36): ("Slider", "axis"), (1, 0x37): ("Dial", "axis"),
    (1, 0x38): ("Wheel", "wheel"), (1, 0x39): ("Hat Switch", "control"),
    (1, 0x3A): ("Counted Buffer", "buffer"),
    (1, 0x3B): ("Byte Count", "control"), (1, 0x3C): ("Motion Wakeup", "control"),
    (1, 0x3D): ("Start", "control"), (1, 0x3E): ("Select", "control"),
    (1, 0x40): ("Vx", "axis"), (1, 0x41): ("Vy", "axis"),
    (1, 0x42): ("Vz", "axis"), (1, 0x43): ("Vbrx", "axis"),
    (1, 0x44): ("Vbry", "axis"), (1, 0x45): ("Vbrz", "axis"),
    (1, 0x46): ("Vno", "axis"), (1, 0x47): ("Feature Notification", "event"),
    (1, 0x48): ("Resolution Multiplier", "control"),
    (1, 0x49): ("Qx", "axis"), (1, 0x4A): ("Qy", "axis"),
    (1, 0x4B): ("Qz", "axis"), (1, 0x4C): ("Qw", "axis"),
    (6, 0x20): ("Battery Strength", "battery"),
    (6, 0x21): ("Wireless Channel", "device_control"),
    (6, 0x22): ("Wireless ID", "device_control"),
    (6, 0x23): ("Discover Wireless Control", "device_control"),
    (6, 0x24): ("Security Code Character Entered", "device_control"),
    (6, 0x25): ("Security Code Character Erased", "device_control"),
    (6, 0x26): ("Security Code Cleared", "device_control"),
    (6, 0x27): ("Sequence ID", "device_control"),
    (6, 0x28): ("Sequence ID Reset", "device_control"),
    (6, 0x2A): ("Software Version", "device_control"),
    (6, 0x2B): ("Protocol Version", "device_control"),
    (6, 0x2C): ("Hardware Version", "device_control"),
    (6, 0x2D): ("Major", "device_control"), (6, 0x2E): ("Minor", "device_control"),
    (6, 0x2F): ("Revision", "device_control"),
    (0x0C, 0x30): ("Power", "consumer_control"),
    (0x0C, 0xE2): ("Mute", "consumer_control"),
    (0x0C, 0xE9): ("Volume Increment", "consumer_control"),
    (0x0C, 0xEA): ("Volume Decrement", "consumer_control"),
    (0x0C, 0xB0): ("Play", "consumer_control"),
    (0x0C, 0xB1): ("Pause", "consumer_control"),
    (0x0C, 0xB5): ("Scan Next Track", "consumer_control"),
    (0x0C, 0xB6): ("Scan Previous Track", "consumer_control"),
    (0x0C, 0xCD): ("Play/Pause", "consumer_control"),
    (0x0C, 0x223): ("AC Home", "application_control"),
    (0x0C, 0x224): ("AC Back", "application_control"),
    (0x0C, 0x225): ("AC Forward", "application_control"),
    (0x0C, 0x238): ("AC Pan", "horizontal_pan"),
    (0x0D, 0x01): ("Digitizer", "digitizer"), (0x0D, 0x02): ("Pen", "digitizer"),
    (0x0D, 0x04): ("Touch Screen", "digitizer"),
    (0x0D, 0x22): ("Finger", "digitizer"), (0x0D, 0x30): ("Tip Pressure", "axis"),
    (0x0D, 0x42): ("Tip Switch", "button"), (0x0D, 0x51): ("Contact Identifier", "control"),
    (0x84, 0x30): ("Voltage", "power"), (0x84, 0x31): ("Current", "power"),
    (0x84, 0x32): ("Frequency", "power"), (0x84, 0x40): ("Config Voltage", "power"),
    (0x85, 0x44): ("Charging", "battery"), (0x85, 0x45): ("Discharging", "battery"),
    (0x85, 0x65): ("Absolute State of Charge", "battery"),
    (0x85, 0x66): ("Remaining Capacity", "battery"),
    (0x85, 0x68): ("Run Time To Empty", "battery"),
}

class HidUsageDatabase:
    def lookup(self, page:int, usage:int) -> HidUsageInfo:
        if 0xFF00 <= page <= 0xFFFF:
            return HidUsageInfo(HidUsage(page,usage),f"Vendor {page:04X}",f"Usage {usage:04X}","vendor")
        page_name=_PAGES.get(page,f"Usage Page {page:04X}")
        if page==0x09: return HidUsageInfo(HidUsage(page,usage),page_name,f"Button {usage}","button")
        if page==0x07: return HidUsageInfo(HidUsage(page,usage),page_name,f"Key {usage:02X}","keyboard")
        name,category=_USAGES.get((page,usage),(f"Usage {usage:04X}","standard_other"))
        return HidUsageInfo(HidUsage(page,usage),page_name,name,category)

USAGES = HidUsageDatabase()
