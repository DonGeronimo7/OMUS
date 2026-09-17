"""Small, auditable HID Usage ontology used by semantic interpretation."""
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

_PAGES = {0x01:"Generic Desktop",0x07:"Keyboard/Keypad",0x09:"Button",0x0C:"Consumer",
          0x0D:"Digitizers",0x59:"Lighting and Illumination",0x84:"Power",0x85:"Battery System",
          0x06:"Generic Device Controls",0x0E:"Haptics"}
_USAGES = {
 (1,1):("Pointer","pointer"),(1,2):("Mouse","mouse"),(1,4):("Joystick","pointer"),(1,5):("Game Pad","pointer"),
 (1,0x30):("X","axis"),(1,0x31):("Y","axis"),(1,0x32):("Z","axis"),(1,0x33):("Rx","axis"),
 (1,0x34):("Ry","axis"),(1,0x35):("Rz","axis"),(1,0x36):("Slider","axis"),(1,0x37):("Dial","axis"),
 (1,0x38):("Wheel","wheel"),(1,0x39):("Hat Switch","control"),
 (0x0C,0x238):("AC Pan","horizontal_pan"),
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
