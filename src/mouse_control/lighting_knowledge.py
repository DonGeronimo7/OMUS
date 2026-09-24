# SPDX-License-Identifier: AGPL-3.0-or-later
"""Source-backed lighting knowledge with no runtime write authority."""

from __future__ import annotations

from dataclasses import dataclass

from .hardware.capabilities import LightingMode, LightingPersistence, LightingWriteScope


@dataclass(frozen=True)
class LightingDetectorKnowledge:
    family: str
    source: str
    interface_number: int | None = None
    usage_page: int | None = None
    usage: int | None = None
    report_type: str | None = None
    report_id: int | None = None
    report_length: int | None = None
    modes: tuple[LightingMode, ...] = ()
    zones: tuple[str, ...] = ("entire_device",)
    persistence: LightingPersistence = LightingPersistence.UNKNOWN
    write_scope: LightingWriteScope = LightingWriteScope.LIGHTING_ONLY
    host_streamed_unsupported: bool = True
    runtime_write_authorized: bool = False
    notes: str = ""


SOURCE_BACKED_LIGHTING_KNOWLEDGE = (
    LightingDetectorKnowledge(
        "logitech-hidpp2-lighting", "OpenRGB HID++ feature families 0x8070/0x8071/0x0600",
        modes=(LightingMode.OFF, LightingMode.STATIC, LightingMode.BREATHING, LightingMode.SPECTRUM),
        zones=("enumerated",), notes="Resolve features and zones dynamically through HID++ ROOT.",
    ),
    LightingDetectorKnowledge(
        "redragon-ffa0-interface2", "OpenRGB Redragon implementations",
        interface_number=2, usage_page=0xFFA0, usage=0x01, report_type="feature",
        modes=(LightingMode.OFF, LightingMode.STATIC, LightingMode.BREATHING, LightingMode.SPECTRUM),
        notes="Exact collection required; apply/session side effects vary by family.",
    ),
    LightingDetectorKnowledge(
        "hyperx-haste-feature65", "OpenRGB HyperX Haste family",
        report_type="feature", report_length=65, modes=(LightingMode.OFF, LightingMode.STATIC),
        notes="Model and wired/wireless collection must be resolved; no brand-wide binding.",
    ),
    LightingDetectorKnowledge(
        "asus-aura-mouse", "OpenRGB ASUS Aura mouse protocol",
        modes=(LightingMode.OFF, LightingMode.STATIC, LightingMode.BREATHING, LightingMode.SPECTRUM),
        zones=("logo", "wheel", "underglow"), persistence=LightingPersistence.MANUAL_SAVE,
    ),
    LightingDetectorKnowledge(
        "sinowealth-shared-config-lighting", "OpenRGB historical whole-config mouse implementations",
        modes=(LightingMode.OFF, LightingMode.STATIC, LightingMode.BREATHING, LightingMode.SPECTRUM),
        write_scope=LightingWriteScope.SHARED_DEVICE_CONFIG,
        notes="Requires trustworthy baseline, byte-preserving RMW, integrity recomputation, and verification.",
    ),
    LightingDetectorKnowledge(
        "razer-native-effects", "OpenRGB/OpenRazer device-specific matrix evidence",
        modes=(LightingMode.OFF, LightingMode.STATIC, LightingMode.SPECTRUM),
        persistence=LightingPersistence.VOLATILE,
        notes="Breathing is excluded unless exact-device evidence proves a one-shot native effect.",
    ),
)
