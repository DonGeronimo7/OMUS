from types import SimpleNamespace

from mouse_control.discovery import MouseDevice
from mouse_control.hardware.capabilities import (
    DpiCapabilities,
    DpiRange,
    HardwareCapabilities,
    ReportRateCapabilities,
)
from mouse_control.setup_flow import SetupChoices, discover_choices
from mouse_control.setup_tui import ActionKind, SECTIONS, SetupController, SetupSection

MOUSE1 = MouseDevice("Range Mouse", "/dev/input/one", vendor=1, product=1, phys="usb-1")
MOUSE2 = MouseDevice("Other Mouse", "/dev/input/two", vendor=2, product=2, phys="usb-2")


class RangeBackend:
    protocol_adapter_name = "Test Protocol"
    has_proven_learned_adapter = False

    def __init__(self):
        self.dpi = 800
        self.rate = 1000
        self.closed = False
        self.set_dpi_calls = []

    def get_capabilities(self, _device):
        return HardwareCapabilities(
            dpi=DpiCapabilities(
                readable=True,
                writable=True,
                ranges=(DpiRange(200, 12000, 50),),
            ),
            report_rate=ReportRateCapabilities(
                readable=True,
                writable=True,
                values=(125, 250, 500, 1000),
            ),
        )

    def supports_dpi(self, _device): return True
    def get_dpi_values(self, _device): return []
    def get_dpi(self, _device): return self.dpi

    def set_dpi(self, _device, value):
        self.set_dpi_calls.append(value)
        self.dpi = value
        return value

    def supports_polling_rate(self, _device): return True
    def supports_polling_rate_writes(self, _device): return True
    def get_polling_rates(self, _device): return [125, 250, 500, 1000]
    def get_polling_rate(self, _device): return self.rate
    def supports_dpi_events(self, _device): return False
    def close(self): self.closed = True


def choices_factory(existing):
    dpi = existing.get("dpi", {})
    polling = existing.get("polling", {})
    return SetupChoices(
        stages=list(dpi.get("stages", [800, 1500, 2000, 2500, 3000])),
        active_dpi=dpi.get("active", 800),
        polling_rate=polling.get("rate_hz"),
        mappings=dict(existing.get("remap", {"BTN_LEFT": "passthrough"})),
    )


def make_controller(backends=None, existing=None):
    backends = backends or {MOUSE1.path: RangeBackend(), MOUSE2.path: RangeBackend()}
    return SetupController(
        [MOUSE1, MOUSE2],
        existing or {},
        choices_factory=choices_factory,
        backend_factory=lambda device: backends[device.path],
    ), backends


def test_range_capability_accepts_step_values_without_enumeration():
    backend = RangeBackend()
    choices = choices_factory({})
    discover_choices(backend, MOUSE1, choices)
    assert choices.dpi_values == []
    assert choices.dpi_ranges == [DpiRange(200, 12000, 50)]
    assert choices.dpi_increment == 50
    assert choices.accepts_dpi(1450)
    assert not choices.accepts_dpi(1475)
    assert choices.stages == [800, 1500, 2000, 2500, 3000]


def test_setup_order_is_discovery_then_dpi_polling_buttons():
    assert SECTIONS == (
        SetupSection.DEVICE,
        SetupSection.HARDWARE,
        SetupSection.LAB,
        SetupSection.DPI,
        SetupSection.POLLING,
        SetupSection.BUTTONS,
        SetupSection.LIGHTING,
        SetupSection.SERVICE,
        SetupSection.UPDATE,
        SetupSection.TOOLS,
        SetupSection.ABOUT,
        SetupSection.REVIEW,
    )


def test_device_enter_requests_automatic_discovery_before_configuration():
    controller, _ = make_controller()
    action = controller.handle_key("ENTER")
    assert controller.section is SetupSection.HARDWARE
    assert action.kind is ActionKind.AUTOMATIC_DISCOVERY


def test_review_edits_return_to_review():
    controller, _ = make_controller()
    controller.section_index = SECTIONS.index(SetupSection.REVIEW)
    controller.row_cursor = 1
    controller.handle_key("ENTER")
    assert controller.section is SetupSection.DPI
    controller.handle_key("BACK")
    assert controller.section is SetupSection.REVIEW

    controller.row_cursor = 2
    controller.handle_key("ENTER")
    assert controller.section is SetupSection.POLLING
    controller.handle_key("RIGHT")
    assert controller.section is SetupSection.REVIEW


def test_switching_devices_invalidates_old_discovery_state_and_rolls_back():
    first, second = RangeBackend(), RangeBackend()
    controller, _ = make_controller({MOUSE1.path: first, MOUSE2.path: second})
    controller.discovery_complete = True
    controller.discovery_result = SimpleNamespace(protocol=object(), capabilities={})
    controller.choices.measured_polling_rate = 1000
    controller.handle_key("DOWN")
    action = controller.handle_key("ENTER")
    assert action.kind is ActionKind.AUTOMATIC_DISCOVERY
    assert controller.selected == MOUSE2
    assert first.closed is True
    assert first.set_dpi_calls[-1] == 800
    assert controller.discovery_complete is False
    assert controller.discovery_result is None
    assert controller.choices.measured_polling_rate is None


def test_polling_measurement_is_separate_from_protocol_readback():
    controller, _ = make_controller()
    controller.apply_polling_measurement(
        SimpleNamespace(standard_hz=500, confidence="high", rejection_reason=None)
    )
    assert controller.choices.current_polling_rate == 1000
    assert controller.choices.measured_polling_rate == 500
    assert controller.choices.measured_polling_confidence == "high"


def test_hardware_summary_keeps_dpi_and_polling_independent():
    controller, _ = make_controller()
    controller.choices.dpi_readable = False
    controller.choices.dpi_writable = False
    lines = controller.hardware_lines()
    assert any("DPI capability not yet discovered" in line for line in lines)
    assert any("Polling capability: read/write" in line for line in lines)


class ObserveOnlyBackend(RangeBackend):
    def get_capabilities(self, _device):
        return HardwareCapabilities()

    def supports_dpi(self, _device): return False
    def get_dpi_values(self, _device): return []
    def supports_polling_rate(self, _device): return False
    def supports_polling_rate_writes(self, _device): return False
    def get_polling_rates(self, _device): return []
    def supports_dpi_events(self, _device): return True


def test_no_write_path_is_successful_discovery_and_skips_write_pages():
    backend = ObserveOnlyBackend()
    controller = SetupController(
        [MOUSE1],
        {},
        choices_factory=choices_factory,
        backend_factory=lambda _device: backend,
    )
    controller.discovery_complete = True

    assert controller.no_write_path is True
    lines = controller.hardware_lines()
    assert any("no verified host-accessible DPI/polling write path" in line for line in lines)
    assert any("Button remapping remains available" in line for line in lines)
    assert any("stage notifications available" in line for line in lines)

    controller.section_index = SECTIONS.index(SetupSection.HARDWARE)
    controller.row_cursor = controller.row_count() - 1
    controller.handle_key("ENTER")
    assert controller.section is SetupSection.BUTTONS
    controller.handle_key("LEFT")
    assert controller.section is SetupSection.HARDWARE


def test_capability_navigation_only_shows_writable_hardware_pages():
    controller, _ = make_controller()
    controller.choices.dpi_writable = False
    controller.choices.polling_writable = True
    controller.section_index = SECTIONS.index(SetupSection.HARDWARE)
    controller.handle_key("RIGHT")
    assert controller.section is SetupSection.POLLING

    controller.choices.dpi_writable = True
    controller.choices.polling_writable = False
    controller.section_index = SECTIONS.index(SetupSection.HARDWARE)
    controller.handle_key("RIGHT")
    assert controller.section is SetupSection.DPI
    controller.handle_key("RIGHT")
    assert controller.section is SetupSection.BUTTONS
