from dataclasses import replace

import pytest

from mouse_control.discovery import MouseDevice
from mouse_control.hardware import HardwareBackend, HardwareError
from mouse_control.hardware.capabilities import (
    HardwareCapabilities,
    LightingCapabilities,
    LightingMode,
    LightingPersistence,
    LightingState,
    LightingWriteScope,
    LightingZoneCapabilities,
)
from mouse_control.lighting import (
    normalize_color,
    patch_shared_configuration,
    validate_lighting_state,
)
from mouse_control.setup_flow import SetupChoices, discover_choices
from mouse_control.setup_tui import SetupController, SetupSection
from mouse_control.hardware.supervisor import DesiredHardwareState, HardwareSupervisor
from mouse_control import cli
from mouse_control.lighting_knowledge import SOURCE_BACKED_LIGHTING_KNOWLEDGE
import tomllib


ZONE = LightingZoneCapabilities(
    "logo", "Logo",
    modes=(LightingMode.OFF, LightingMode.STATIC, LightingMode.BREATHING, LightingMode.SPECTRUM),
    rgb24=True,
    brightness_range=(0, 100),
    speed_range=(1, 10),
    persistence=(LightingPersistence.VOLATILE, LightingPersistence.ONBOARD),
    writable=True,
    readable=True,
)


class LightingBackend(HardwareBackend):
    name = "Lighting test"

    def __init__(self, zones=(ZONE,)):
        self.zones = zones
        self.states = {}
        self.set_calls = []

    def supports_device(self, _device): return True
    def get_capabilities(self, _device):
        return HardwareCapabilities(lighting=LightingCapabilities(tuple(self.zones)))
    def set_lighting_state(self, _device, state):
        self.set_calls.append(state)
        self.states[state.zone_id] = replace(state, confirmed=True)
        return self.states[state.zone_id]
    def get_lighting_state(self, _device, zone_id): return self.states.get(zone_id)


MOUSE = MouseDevice("RGB Mouse", "/dev/input/rgb", vendor=1, product=2, phys="usb-rgb")


@pytest.mark.parametrize("color", ("#000000", "#FFFFFF", "#8a2be2"))
def test_rgb24_accepts_full_range_and_normalizes(color):
    assert normalize_color(color) == color.upper()


@pytest.mark.parametrize("color", ("000000", "#FFFF", "#GG0000", "#1234567", ""))
def test_invalid_hex_is_rejected(color):
    with pytest.raises(ValueError):
        normalize_color(color)


def test_mode_brightness_speed_and_persistence_are_capability_gated():
    state = LightingState("logo", LightingMode.BREATHING, "#123456", 75, 5,
                          LightingPersistence.VOLATILE)
    assert validate_lighting_state(state, ZONE).color == "#123456"
    with pytest.raises(ValueError):
        validate_lighting_state(replace(state, brightness=101), ZONE)
    with pytest.raises(ValueError):
        validate_lighting_state(replace(state, speed=0), ZONE)
    with pytest.raises(ValueError):
        validate_lighting_state(replace(state, persistence=LightingPersistence.MANUAL_SAVE), ZONE)


def test_unsupported_and_host_streamed_modes_are_rejected():
    static_only = replace(ZONE, modes=(LightingMode.OFF, LightingMode.STATIC))
    with pytest.raises(ValueError):
        validate_lighting_state(
            LightingState("logo", LightingMode.BREATHING, "#FF0000"), static_only
        )
    assert not hasattr(LightingMode, "DIRECT")


def test_shared_config_requires_baseline_and_preserves_every_unrelated_byte():
    original = bytes(range(16))
    with pytest.raises(HardwareError):
        patch_shared_configuration(None, lambda record: None,
                                   write_scope=LightingWriteScope.SHARED_DEVICE_CONFIG)
    patched = patch_shared_configuration(
        original,
        lambda record: record.__setitem__(7, 0xFE),
        write_scope=LightingWriteScope.SHARED_DEVICE_CONFIG,
        integrity=lambda record: record.__setitem__(15, sum(record[:15]) & 0xFF),
    )
    assert patched[7] == 0xFE
    assert patched[15] == sum(patched[:15]) & 0xFF
    assert patched[:7] == original[:7]
    assert patched[8:15] == original[8:15]


def test_no_lighting_device_keeps_other_capabilities_usable():
    backend = LightingBackend(())
    choices = SetupChoices()
    discover_choices(backend, MOUSE, choices)
    assert choices.lighting_zones == []


def test_multi_zone_discovery_and_tui_staging_do_not_write_hardware():
    wheel = replace(ZONE, zone_id="wheel", name="Wheel", modes=(LightingMode.OFF, LightingMode.STATIC))
    backend = LightingBackend((ZONE, wheel))
    controller = SetupController(
        [MOUSE], {}, choices_factory=lambda _existing: SetupChoices(),
        backend_factory=lambda _device: backend,
    )
    assert [item.zone_id for item in controller.choices.lighting_zones] == ["logo", "wheel"]
    controller.section_index = tuple(SetupSection).index(SetupSection.LIGHTING)
    assert controller.set_lighting_state(
        LightingState("logo", LightingMode.STATIC, "#8a2be2", 75, None,
                      LightingPersistence.VOLATILE)
    )
    assert controller.choices.lighting["logo"].color == "#8A2BE2"
    assert backend.states == {}


def test_read_only_lighting_cannot_be_staged_as_writable():
    backend = LightingBackend((replace(ZONE, writable=False),))
    controller = SetupController(
        [MOUSE], {}, choices_factory=lambda _existing: SetupChoices(),
        backend_factory=lambda _device: backend,
    )
    assert not controller.set_lighting_state(
        LightingState("logo", LightingMode.STATIC, "#FFFFFF")
    )
    assert backend.states == {}


def test_lighting_config_round_trip_is_per_zone_and_backward_compatible():
    assert cli._initial_choices({}).lighting == {}
    state = LightingState("logo", LightingMode.STATIC, "#8A2BE2", 75, 5,
                          LightingPersistence.VOLATILE)
    content = cli.merge_setup_config(
        {}, MOUSE, mappings={}, dpi_stages=[800], active_dpi=800,
        polling_rate_hz=None, lighting={"logo": state},
    )
    loaded = tomllib.loads(content)
    restored = cli._initial_choices(loaded).lighting["logo"]
    assert restored == state


def test_volatile_reconcile_is_once_per_backend_and_reapplies_after_rebind():
    state = LightingState("logo", LightingMode.STATIC, "#FFFFFF", 50, 5,
                          LightingPersistence.VOLATILE)
    first = LightingBackend()
    second = LightingBackend()
    supervisor = HardwareSupervisor(
        first, MOUSE, lambda _device: second,
        DesiredHardwareState(volatile_lighting=(state,)),
    )
    supervisor.reconcile()
    supervisor.reconcile()
    assert len(first.set_calls) == 1
    assert supervisor.rebind(force=True)
    assert len(second.set_calls) == 1


def test_shared_config_capability_is_refused_without_backend_rmw_proof():
    shared = replace(ZONE, write_scope=LightingWriteScope.SHARED_DEVICE_CONFIG)
    backend = LightingBackend((shared,))
    state = LightingState("logo", LightingMode.STATIC, "#FFFFFF", 50, 5,
                          LightingPersistence.VOLATILE)
    cli._apply_lighting(backend, MOUSE, (state,))
    assert backend.states == {}


def test_source_lighting_fingerprints_remain_exact_and_write_disabled():
    records = {item.family: item for item in SOURCE_BACKED_LIGHTING_KNOWLEDGE}
    redragon = records["redragon-ffa0-interface2"]
    assert (redragon.interface_number, redragon.usage_page, redragon.usage) == (2, 0xFFA0, 1)
    hyperx = records["hyperx-haste-feature65"]
    assert (hyperx.report_type, hyperx.report_length) == ("feature", 65)
    shared = records["sinowealth-shared-config-lighting"]
    assert shared.write_scope is LightingWriteScope.SHARED_DEVICE_CONFIG
    assert all(not item.runtime_write_authorized for item in records.values())
    assert all(item.host_streamed_unsupported for item in records.values())
