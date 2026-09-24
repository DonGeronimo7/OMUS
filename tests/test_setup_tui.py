# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mouse_control.discovery import MouseDevice
from mouse_control.guided_discovery import GuidedDiscoveryOutcome, GuidedDpiLearningOutcome
from mouse_control.discovery_view import DiscoveryView
from mouse_control.setup_flow import SetupChoices
from mouse_control.setup_tui import ActionKind, SECTIONS, SetupController, SetupSection
from mouse_control.setup_tui_curses import CursesSetupApp


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


def controller(*, backends=None, existing=None, known_device_loader=lambda _device: None):
    backends = backends or {
        MOUSE1.path: FakeBackend(),
        MOUSE2.path: FakeBackend(),
    }
    return SetupController(
        [MOUSE1, MOUSE2],
        existing or {},
        choices_factory=choices_factory,
        backend_factory=lambda device: backends[device.path],
        known_device_loader=known_device_loader,
    ), backends


def test_deferred_controller_does_not_open_hardware_before_first_frame():
    opened = []
    app = SetupController(
        [MOUSE1],
        {},
        choices_factory=choices_factory,
        backend_factory=lambda device: opened.append(device) or FakeBackend(),
        known_device_loader=lambda _device: None,
        initialize_backend=False,
    )

    assert app.backend is None
    assert opened == []
    assert app.detail_rows()[0].text == "Select the mouse to configure."
    ready = app.initialized_copy(0)
    assert opened == [MOUSE1]
    assert ready.backend_ready is True


def test_discovery_view_is_rendered_in_hardware_and_lab_without_implying_proof():
    app, _ = controller()
    view = DiscoveryView(
        "escalation",
        ("Interface 2: admitted", "Protocol Genome records: 4",
         "Advice candidates: 2", "Grammar alternatives: 2"),
        ("protocol_genome: loaded family knowledge",
         "grammar: retained 2 alternatives",
         "escalation: human evidence required"),
        "change DPI once using the physical DPI button",
    )
    app.apply_discovery_view(view)
    app.section_index = SECTIONS.index(SetupSection.HARDWARE)
    hardware = "\n".join(row.text for row in app.detail_rows())
    assert "Discovery engine" in hardware
    assert "Grammar alternatives: 2" in hardware
    assert "Next required evidence: change DPI once" in hardware
    app.section_index = SECTIONS.index(SetupSection.LAB)
    lab = "\n".join(row.text for row in app.detail_rows())
    assert "Automatic Discovery boundary" in lab
    assert "Requested action: change DPI once" in lab
    assert "No inferred or community evidence grants write authority" in lab


def test_device_rebind_clears_stale_discovery_view():
    app, _ = controller()
    app.apply_discovery_view(DiscoveryView("grammar", (), (), "capture one action"))
    app._bind_device(1)
    assert app.discovery_view is None


def test_automatic_outcome_populates_canonical_discovery_view_with_proof_distinction():
    app, _ = controller()
    outcome = SimpleNamespace(
        result=SimpleNamespace(
            protocol=SimpleNamespace(name="Candidate Family"),
            capabilities={"dpi": SimpleNamespace(mode="inferred")},
        ),
        engine=None,
        research_plan=SimpleNamespace(
            blockers=("one physical DPI observation is missing",),
            deeper_learning_recommended=False,
        ),
        cached_profile_used=False,
        bound_protocol_used=True,
    )
    app.apply_automatic_discovery(outcome)
    assert app.discovery_view is not None
    assert "RECOGNIZED / UNVERIFIED" in app.discovery_view.overview[0]
    assert "dpi: inferred" in app.discovery_view.overview[2]
    assert app.discovery_view.human_action == "one physical DPI observation is missing"


def test_known_configured_device_loads_persisted_state_without_automatic_discovery():
    result = SimpleNamespace(device=SimpleNamespace(), protocol=None, capabilities={})
    outcome = SimpleNamespace(
        result=result,
        engine=SimpleNamespace(),
        research_plan=None,
        cached_profile_used=True,
    )
    loaded = []
    existing = {
        "device": {"vendor": 1, "product": 1, "phys": "usb-1"},
        "dpi": {"active": 800, "stages": [800, 1600]},
        "remap": {"BTN_LEFT": "passthrough"},
    }
    app, _ = controller(
        existing=existing,
        known_device_loader=lambda device: loaded.append(device) or outcome,
    )

    assert loaded == [MOUSE1]
    assert app.discovery_complete is True
    assert "Known device ready" in app.status
    assert app.handle_key("ENTER").kind is ActionKind.NONE
    assert app.section is SetupSection.HARDWARE

    app.row_cursor = 0
    assert app.handle_key("ENTER").kind is ActionKind.RETRY_DISCOVERY


def test_different_physical_device_does_not_reuse_configured_discovery_state():
    loaded = []
    existing = {
        "device": {"vendor": 1, "product": 1, "phys": "usb-other-instance"},
        "dpi": {"active": 800, "stages": [800, 1600]},
        "remap": {"BTN_LEFT": "passthrough"},
    }
    app, _ = controller(
        existing=existing,
        known_device_loader=lambda device: loaded.append(device),
    )

    assert loaded == []
    assert app.discovery_complete is False
    assert app.handle_key("ENTER").kind is ActionKind.AUTOMATIC_DISCOVERY


def test_device_selection_restores_temporary_state_before_switch():
    app, backends = controller()
    app.handle_key("DOWN")
    action = app.handle_key("ENTER")
    assert app.selected == MOUSE2
    assert app.section is SetupSection.HARDWARE
    assert action.kind is ActionKind.AUTOMATIC_DISCOVERY
    assert backends[MOUSE1.path].set_dpi_calls[-1] == 800
    assert backends[MOUSE1.path].closed is True


def test_left_right_and_back_navigate_sections_without_terminal():
    app, _ = controller()
    assert app.section is SetupSection.DEVICE
    app.handle_key("RIGHT")
    assert app.section is SetupSection.HARDWARE
    app.handle_key("RIGHT")
    assert app.section is SetupSection.DPI
    app.handle_key("BACK")
    assert app.section is SetupSection.HARDWARE
    app.handle_key("LEFT")
    assert app.section is SetupSection.DEVICE


def test_normal_navigation_reuses_session_without_hardware_queries():
    backend = FakeBackend()
    calls = {
        name: 0 for name in (
            'get_dpi', 'get_polling_rate', 'get_dpi_values', 'get_polling_rates'
        )
    }
    for name in calls:
        original = getattr(backend, name)
        def counted(*args, _name=name, _original=original, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)
        setattr(backend, name, counted)
    app, _ = controller(backends={MOUSE1.path: backend, MOUSE2.path: FakeBackend()})
    baseline = dict(calls)

    for key in ('RIGHT', 'RIGHT', 'LEFT', 'RIGHT', 'RIGHT', 'BACK', 'LEFT', 'RIGHT'):
        assert app.handle_key(key).kind is ActionKind.NONE

    assert calls == baseline


def test_vim_key_translation_is_additive_to_existing_navigation():
    import curses

    assert CursesSetupApp._symbolic_key(curses.KEY_DOWN) == "DOWN"
    assert CursesSetupApp._symbolic_key(curses.KEY_UP) == "UP"
    assert CursesSetupApp._symbolic_key(curses.KEY_LEFT) == "LEFT"
    assert CursesSetupApp._symbolic_key(curses.KEY_RIGHT) == "RIGHT"
    assert CursesSetupApp._symbolic_key(curses.KEY_HOME) == "FIRST"
    assert CursesSetupApp._symbolic_key(curses.KEY_END) == "LAST"
    assert CursesSetupApp._symbolic_key(10) == "ENTER"
    assert CursesSetupApp._symbolic_key(27) == "ESC"
    assert CursesSetupApp._symbolic_key(ord("j")) == "DOWN"
    assert CursesSetupApp._symbolic_key(ord("k")) == "UP"
    assert CursesSetupApp._symbolic_key(ord("h")) == "LEFT"
    assert CursesSetupApp._symbolic_key(ord("l")) == "RIGHT"
    assert CursesSetupApp._symbolic_key(ord("g")) == "FIRST"
    assert CursesSetupApp._symbolic_key(ord("G")) == "LAST"


def test_vim_directions_match_arrows_and_first_last_reuse_controller_actions():
    import curses

    app, _ = controller()
    app.handle_key("LAST")
    assert app.device_cursor == len(app.devices) - 1
    app.handle_key("FIRST")
    assert app.device_cursor == 0

    arrow_app, _ = controller()
    vim_app, _ = controller()
    for arrow_key, vim_key in (
        (curses.KEY_DOWN, ord("j")),
        (curses.KEY_UP, ord("k")),
        (curses.KEY_RIGHT, ord("l")),
        (curses.KEY_LEFT, ord("h")),
    ):
        arrow = CursesSetupApp._symbolic_key(arrow_key)
        vim = CursesSetupApp._symbolic_key(vim_key)
        assert arrow == vim
        arrow_action = arrow_app.handle_key(arrow)
        vim_action = vim_app.handle_key(vim)
        assert vim_app.section == arrow_app.section
        assert vim_app.row_cursor == arrow_app.row_cursor
        assert vim_app.device_cursor == arrow_app.device_cursor
        assert vim_action.kind is arrow_action.kind

    enter_app, _ = controller()
    enter_action = enter_app.handle_key("ENTER")
    assert enter_action.kind is ActionKind.AUTOMATIC_DISCOVERY
    assert enter_app.section is SetupSection.HARDWARE


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


def test_known_protocol_and_proven_learned_devices_skip_unnecessary_learning():
    known = {MOUSE1.path: FakeBackend(protocol="Logitech HID++ 2"), MOUSE2.path: FakeBackend()}
    app, _ = controller(backends=known)
    assert app.guided_discovery_available is False
    assert any("Logitech HID++ 2" in line for line in app.hardware_lines())

    learned = {
        MOUSE1.path: FakeBackend(protocol=None, learned=True),
        MOUSE2.path: FakeBackend(),
    }
    app, _ = controller(backends=learned)
    assert app.guided_discovery_available is False
    assert "✓ Learned exact-model support" in app.hardware_lines()


def test_unknown_device_offers_deeper_learning_only_after_automatic_research_plan():
    unknown = {
        MOUSE1.path: FakeBackend(dpi=False, polling=False, protocol=None),
        MOUSE2.path: FakeBackend(),
    }
    app, _ = controller(backends=unknown)
    app.section_index = SECTIONS.index(SetupSection.HARDWARE)
    # Deeper learning is not a pre-discovery generic escape hatch.
    assert app.guided_discovery_available is False
    assert app.handle_key("ENTER").kind is ActionKind.AUTOMATIC_DISCOVERY

    app.discovery_complete = True
    app.research_plan = SimpleNamespace(deeper_learning_recommended=True)
    assert app.guided_discovery_available is True
    app.row_cursor = 2
    assert app.handle_key("ENTER").kind is ActionKind.GUIDED_DISCOVERY
    app.row_cursor = 3
    assert app.handle_key("ENTER").kind is ActionKind.NONE
    # No verified write path is a successful result; skip non-configurable pages.
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


def calibrated_profile(*, sources=()):
    return {
        "dpi_cycle": {
            "confidence": "validated",
            "states": [
                {"measured_cpi": 812.0, "polling_hz": 500, "confidence": "high"},
                {"measured_cpi": 1595.0, "polling_hz": 500, "confidence": "high"},
                {"measured_cpi": 2410.0, "polling_hz": 500, "confidence": "high"},
                {"measured_cpi": 808.0, "polling_hz": 500, "confidence": "high"},
            ],
        },
        "transition_sources": [{"kind": kind} for kind in sources],
    }


def unknown_controller_with_old_config():
    unknown = {
        MOUSE1.path: FakeBackend(dpi=False, polling=False, protocol=None),
        MOUSE2.path: FakeBackend(dpi=False, polling=False, protocol=None),
    }
    return controller(
        backends=unknown,
        existing={
            "dpi": {"active": 1000, "stages": [1000, 1500, 2000, 2500, 3000]},
            "polling": {"rate_hz": 1000},
        },
    )


def test_read_only_review_separates_old_preferences_from_missing_measurements():
    app, _ = unknown_controller_with_old_config()
    app.discovery_complete = True
    app.section_index = SECTIONS.index(SetupSection.REVIEW)
    text = "\n".join(row.text for row in app.detail_rows())

    assert "Measured physical DPI cycle: unavailable" in text
    assert "Measured polling: unavailable" in text
    assert "Configured software stages: 1000 → 1500 → 2000 → 2500 → 3000" in text
    assert "Configured polling preference: 1000 Hz" in text
    assert "DPI write control: unavailable / unproven" in text
    assert "Polling write control: unavailable / unproven" in text


def test_exact_device_profile_surfaces_calibration_polling_and_source_state():
    app, _ = unknown_controller_with_old_config()
    physical = SimpleNamespace(hidraw_nodes=[object()], ambiguous=False)
    outcome = SimpleNamespace(
        result=SimpleNamespace(device=physical, capabilities={}, protocol=None),
        engine=object(),
        research_plan=SimpleNamespace(
            deeper_learning_recommended=True,
            reversible_probe_available=False,
            dpi=SimpleNamespace(status=SimpleNamespace(value="no-evidence")),
            polling=SimpleNamespace(status=SimpleNamespace(value="no-evidence")),
        ),
    )
    with patch(
        "mouse_control.setup_tui.find_calibrated_profile",
        return_value=(Path("calibrated.json"), calibrated_profile()),
    ):
        app.apply_automatic_discovery(outcome)

    assert app.observed_hardware.calibrated_dpi_cycle == (812, 1595, 2410)
    assert app.observed_hardware.measured_polling_rate == 500
    assert app.deep_learning_label == "Learn runtime DPI transition source"
    lines = app.hardware_lines()
    assert "✓ Physical DPI cycle already calibrated" in lines
    assert "? Runtime DPI transition source unresolved" in lines
    assert any("ruler calibration will be reused" in line for line in lines)

    app.section_index = SECTIONS.index(SetupSection.REVIEW)
    text = "\n".join(row.text for row in app.detail_rows())
    assert "Measured physical DPI cycle: ~812 → ~1595 → ~2410" in text
    assert "Measured polling: ~500 Hz (high confidence)" in text
    assert "Configured polling preference: 1000 Hz" in text


def test_runtime_source_status_distinguishes_absolute_and_trigger_semantics():
    app, _ = unknown_controller_with_old_config()
    app.discovery_result = SimpleNamespace(device=SimpleNamespace())
    outcome = SimpleNamespace(profile_path=Path("calibrated.json"), wrap_confirmed=True)

    with patch(
        "mouse_control.setup_tui.find_calibrated_profile",
        return_value=(Path("calibrated.json"), calibrated_profile(sources=("hid_state",))),
    ):
        app.apply_deep_learning_outcome(outcome)
    assert "synchronize and resynchronize safely" in app.status

    with patch(
        "mouse_control.setup_tui.find_calibrated_profile",
        return_value=(Path("calibrated.json"), calibrated_profile(sources=("hid_cycle_trigger",))),
    ):
        app.apply_deep_learning_outcome(outcome)
    assert "unsynchronized at startup and after reconnect" in app.status


def test_device_switch_clears_exact_device_observed_evidence():
    app, _ = unknown_controller_with_old_config()
    app.observed_hardware = app.observed_hardware.__class__(
        calibrated_dpi_cycle=(800, 1600), profile_path=Path("first.json")
    )
    app.handle_key("DOWN")
    app.handle_key("ENTER")
    assert app.selected is MOUSE2
    assert not app.observed_hardware.has_physical_calibration


def test_hardware_discovery_opens_first_class_lab_and_runs_analyzer_action():
    app, _ = controller()
    app.section_index = SECTIONS.index(SetupSection.HARDWARE)
    app.discovery_complete = True
    app.discovery_result = SimpleNamespace(device=SimpleNamespace())
    app.discovery_engine = SimpleNamespace(repertoire_candidates=(
        SimpleNamespace(family=SimpleNamespace(name="lamzu-aurora-feature64")),
    ))
    app.row_cursor = 1
    assert app.handle_key("ENTER").kind is ActionKind.NONE
    assert app.section is SetupSection.LAB
    rows = app.detail_rows()
    assert any("Run Full Automatic Lab" in row.text for row in rows)
    assert any("Current question:" in row.text for row in rows)
    assert any("Best experiment:" in row.text for row in rows)
    assert any("Your part:" in row.text for row in rows)
    assert any("Known protocol family candidate: LAMZU Aurora" in row.text for row in rows)
    assert any("Exact hardware proof: incomplete" in row.text for row in rows)
    assert any("Writes: disabled pending verification" in row.text for row in rows)
    assert app.handle_key("ENTER").kind is ActionKind.RUN_DISCOVERY_LAB

    analysis = SimpleNamespace(
        ranked_fields=(SimpleNamespace(
            stream_id="stream", offset=2,
            signals=(SimpleNamespace(value="action_correlated"),), score=105,
        ),),
        next_recommended_experiment=SimpleNamespace(
            experiment="alternate-negative-control",
            reason="separate candidates",
            requires_hardware_write=False,
        ),
        contradictions=(),
    )
    timing = SimpleNamespace(
        summaries=(SimpleNamespace(
            relationship=SimpleNamespace(value="request_response_latency"),
            median_ns=3_000_000, accepted_count=3, spread_ns=200_000,
            minimum_ns=2_900_000, maximum_ns=3_100_000,
        ),),
        differentials=(),
    )
    app.apply_lab_experiment(SimpleNamespace(
        analysis=analysis, observations=(1, 2, 3), timing_profile=timing,
    ))
    text = "\n".join(row.text for row in app.detail_rows())
    assert "Just learned: 1 action-correlated field" in text
    assert "Protocol timing" in text
    assert "median 3.0 ms, stable across 3 samples" in text
    assert "Hardware write required: no" in text

    assessment = SimpleNamespace(
        effective_state=SimpleNamespace(value="state_physically_effective"),
        classifications=(SimpleNamespace(value="reconnect_persistent"),),
        strongest_confirmed_level=SimpleNamespace(name="DEVICE_RECONNECT"),
        contradictions=("stale state superseded",),
        restoration=SimpleNamespace(required=True),
    )
    app.apply_lab_experiment(SimpleNamespace(
        analysis=analysis, observations=(1, 2, 3), timing_profile=timing,
        persistence_assessment=assessment,
    ))
    effect_text = "\n".join(row.text for row in app.detail_rows())
    assert "Effect / persistence" in effect_text
    assert "state physically effective" in effect_text
    assert "reconnect persistent" in effect_text
    assert "Strongest tested level: device reconnect" in effect_text
    assert "Restore original state manually" in effect_text

    routing = SimpleNamespace(
        summary=("child 0x01: high", "receiver-local: medium"),
        evidence=(
            SimpleNamespace(status=SimpleNamespace(value="confirmed_route")),
        ),
        ambiguities=("report 0x13 ownership",),
        next_plan=SimpleNamespace(
            selected_action=SimpleNamespace(label="power-cycle the selected mouse"),
        ),
    )
    app.apply_lab_experiment(SimpleNamespace(
        analysis=analysis, observations=(1, 2, 3), timing_profile=timing,
        routing_analysis=routing,
    ))
    route_text = "\n".join(row.text for row in app.detail_rows())
    assert "Receiver / Device Routing" in route_text
    assert "child 0x01: high" in route_text
    assert "Confirmed logical routes: 1" in route_text
    assert "Unresolved routing questions: 1" in route_text
    assert "Best next routing experiment: power-cycle the selected mouse" in route_text

    power = SimpleNamespace(
        summary=(
            "Battery candidate: raw 73; percentage unknown",
            "Update cadence: approximately 60 s",
        ),
        contradictions=("stale cache differs",),
        pending_natural_observation=True,
        next_plan=SimpleNamespace(
            selected_action=SimpleNamespace(label="connect or disconnect charging once"),
        ),
    )
    app.apply_lab_experiment(SimpleNamespace(
        analysis=analysis, observations=(1, 2, 3), timing_profile=timing,
        power_analysis=power,
    ))
    power_text = "\n".join(row.text for row in app.detail_rows())
    assert "Battery / Power" in power_text
    assert "percentage unknown" in power_text
    assert "Power contradictions retained: 1" in power_text
    assert "Passive follow-up" in power_text
    assert "Best next power experiment: connect or disconnect charging once" in power_text
