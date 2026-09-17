from types import SimpleNamespace

from mouse_control.discovery import MouseDevice
from mouse_control.discovery_lab import DiscoveryTool, discovery_tool_specs
from mouse_control.guided_discovery import GuidedDiscoveryOutcome, GuidedDpiLearningOutcome
from mouse_control.setup_flow import SetupChoices
from mouse_control.setup_tui import ActionKind, SECTIONS, SetupController, SetupSection


MOUSE1 = MouseDevice("Mouse One", "/dev/input/one", vendor=1, product=1, phys="usb-1")
MOUSE2 = MouseDevice("Mouse Two", "/dev/input/two", vendor=2, product=2, phys="usb-2")


class FakeBackend:
    def __init__(self, *, dpi=True, polling=True, protocol="Test Protocol", learned=False):
        self.protocol_adapter_name = protocol
        self.has_proven_learned_adapter = learned
        self._dpi = dpi
        self._polling = polling
        self.dpi = 800
        self.rate = 1000
        self.set_dpi_calls = []
        self.closed = False

    def supports_dpi(self, _device):
        return self._dpi

    def get_dpi_values(self, _device):
        return [800, 1500, 2000, 2500, 3000] if self._dpi else []

    def get_dpi(self, _device):
        return self.dpi if self._dpi else None

    def set_dpi(self, _device, value):
        self.set_dpi_calls.append(value)
        self.dpi = value
        return value

    def supports_polling_rate(self, _device):
        return self._polling

    def supports_polling_rate_writes(self, _device):
        return self._polling

    def get_polling_rates(self, _device):
        return [1000, 500, 250, 125] if self._polling else []

    def get_polling_rate(self, _device):
        return self.rate if self._polling else None

    def supports_dpi_events(self, _device):
        return self._dpi

    def close(self):
        self.closed = True


def choices_factory(existing):
    mappings = dict(existing.get("remap", {"BTN_LEFT": "passthrough"}))
    dpi = existing.get("dpi", {})
    polling = existing.get("polling", {})
    return SetupChoices(
        stages=list(dpi.get("stages", [800, 1500, 2000, 2500, 3000])),
        active_dpi=dpi.get("active", 800),
        polling_rate=polling.get("rate_hz"),
        mappings=mappings,
    )


def controller(*, backends=None, existing=None):
    backends = backends or {
        MOUSE1.path: FakeBackend(),
        MOUSE2.path: FakeBackend(),
    }
    return SetupController(
        [MOUSE1, MOUSE2],
        existing or {},
        choices_factory=choices_factory,
        backend_factory=lambda device: backends[device.path],
    ), backends


def test_device_selection_restores_temporary_state_before_switch():
    app, backends = controller()
    app.handle_key("DOWN")
    app.handle_key("ENTER")
    assert app.selected == MOUSE2
    assert app.section is SetupSection.HARDWARE
    assert backends[MOUSE1.path].set_dpi_calls[-1] == 800
    assert backends[MOUSE1.path].closed is True


def test_left_right_and_back_navigate_sections_without_terminal():
    app, _ = controller()
    assert app.section is SetupSection.DEVICE
    app.handle_key("RIGHT")
    assert app.section is SetupSection.HARDWARE
    app.handle_key("RIGHT")
    assert app.section is SetupSection.BUTTONS
    app.handle_key("BACK")
    assert app.section is SetupSection.HARDWARE
    app.handle_key("LEFT")
    assert app.section is SetupSection.DEVICE


def test_dpi_edit_is_verified_before_state_changes():
    app, backends = controller()
    app.section_index = SECTIONS.index(SetupSection.DPI)
    action = app.handle_key("ENTER")
    assert action.kind is ActionKind.EDIT_DPI
    assert action.payload == 0
    assert app.set_dpi_value(0, 1500) is True
    assert app.choices.stages[0] == 1500
    assert app.choices.active_dpi == 1500
    assert app.choices.dpi_changed is True
    assert backends[MOUSE1.path].set_dpi_calls[-1] == 1500
    before = list(backends[MOUSE1.path].set_dpi_calls)
    assert app.set_dpi_value(0, 825) is False
    assert backends[MOUSE1.path].set_dpi_calls == before


def test_polling_service_review_cancel_and_save_transitions():
    app, _ = controller()
    app.section_index = SECTIONS.index(SetupSection.POLLING)
    app.row_cursor = 1
    app.handle_key("ENTER")
    assert app.choices.polling_rate == 500
    assert app.choices.polling_changed is True

    app.section_index = SECTIONS.index(SetupSection.SERVICE)
    app.row_cursor = 1
    app.handle_key("ENTER")
    assert app.choices.enable_service is False

    app.section_index = SECTIONS.index(SetupSection.REVIEW)
    assert app.handle_key("QUIT").kind is ActionKind.CANCEL
    assert app.handle_key("ENTER").kind is ActionKind.SAVE


def test_existing_mappings_and_preferences_are_preserved_until_edited():
    existing = {
        "device": {"vendor": 1, "product": 1, "phys": "usb-1"},
        "dpi": {"active": 2500, "stages": [800, 1450, 2000, 2500, 3200]},
        "polling": {"rate_hz": 500},
        "remap": {"BTN_FORWARD": "dpi-cycle", "BTN_EXTRA": "key:KEY_F13"},
    }
    app, _ = controller(existing=existing)
    assert app.selected == MOUSE1
    assert app.choices.active_dpi == 2500
    assert app.choices.stages == [800, 1450, 2000, 2500, 3200]
    assert app.choices.polling_rate == 500
    assert app.choices.mappings == existing["remap"]
    app.apply_button_mapping("BTN_EXTRA", "disable")
    assert app.choices.mappings["BTN_FORWARD"] == "dpi-cycle"
    assert app.choices.mappings["BTN_EXTRA"] == "disable"


def test_known_protocol_and_proven_learned_devices_skip_unnecessary_guided_observation():
    known = {MOUSE1.path: FakeBackend(protocol="Logitech HID++ 2"), MOUSE2.path: FakeBackend()}
    app, _ = controller(backends=known)
    assert app.guided_discovery_available is False
    assert any("Logitech HID++ 2" in line for line in app.hardware_lines())
    assert any(action[0] == "tool" for action in app.hardware_actions())

    learned = {
        MOUSE1.path: FakeBackend(protocol=None, learned=True),
        MOUSE2.path: FakeBackend(),
    }
    app, _ = controller(backends=learned)
    assert app.guided_discovery_available is False
    assert "✓ Learned exact-model support" in app.hardware_lines()
    assert any(action[0] == "tool" for action in app.hardware_actions())


def test_unknown_device_offers_guided_discovery_complete_labs_and_continue():
    unknown = {
        MOUSE1.path: FakeBackend(dpi=False, polling=False, protocol=None),
        MOUSE2.path: FakeBackend(),
    }
    app, _ = controller(backends=unknown)
    app.section_index = SECTIONS.index(SetupSection.HARDWARE)
    assert app.guided_discovery_available is True
    assert app.handle_key("ENTER").kind is ActionKind.GUIDED_DISCOVERY

    actions = app.hardware_actions()
    tool_rows = [item for item in actions if item[0] == "tool"]
    assert len(tool_rows) == len(discovery_tool_specs())
    sensor_index = next(
        index for index, item in enumerate(actions)
        if item[2] is DiscoveryTool.SENSOR_CALIBRATION
    )
    app.row_cursor = sensor_index
    action = app.handle_key("ENTER")
    assert action.kind is ActionKind.RUN_DISCOVERY_TOOL
    assert action.payload is DiscoveryTool.SENSOR_CALIBRATION

    app.row_cursor = len(actions) - 1
    assert app.handle_key("ENTER").kind is ActionKind.NONE
    assert app.section is SetupSection.BUTTONS
    assert "BTN_LEFT" in app.choices.mappings


def test_read_only_learning_updates_status_but_never_grants_write_authority():
    unknown = {
        MOUSE1.path: FakeBackend(dpi=False, polling=False, protocol=None),
        MOUSE2.path: FakeBackend(),
    }
    app, _ = controller(backends=unknown)
    result = SimpleNamespace(
        capabilities={},
        device=SimpleNamespace(ambiguous=False, hidraw_nodes=[object()]),
    )
    learning = GuidedDpiLearningOutcome(
        learned=object(), controls=(), samples=(), action_identified=True, teacher_used=False
    )
    app.apply_guided_outcome(GuidedDiscoveryOutcome(result=result, learning=learning, learning_available=True))
    assert app.choices.dpi_writable is False
    assert app.choices.polling_writable is False
    assert any("DPI button behavior identified" in line for line in app.hardware_lines())
    assert "DPI write command not yet proven" in " ".join(app.hardware_lines())


def test_ambiguous_discovery_result_never_promotes_writable_state():
    unknown = {
        MOUSE1.path: FakeBackend(dpi=False, polling=False, protocol=None),
        MOUSE2.path: FakeBackend(),
    }
    app, _ = controller(backends=unknown)
    result = SimpleNamespace(
        capabilities={},
        device=SimpleNamespace(ambiguous=True, hidraw_nodes=[object()]),
    )
    app.apply_guided_outcome(GuidedDiscoveryOutcome(
        result=result,
        learning_skipped_reason="Mouse identity is ambiguous; writes refused.",
    ))
    assert app.choices.dpi_writable is False
    assert app.choices.polling_writable is False
    assert "ambiguous" in app.status.lower()
