from types import SimpleNamespace

import pytest

from mouse_control.lab_expert_tools import (
    GROUPS,
    LAB_INSTRUMENT_TO_TOOL,
    TOOLS,
    ExpertToolAction,
    tool_context,
    tool_status,
    tools_for_group,
)
from mouse_control.discovery_lab import LabInstrument
from mouse_control.setup_flow import SetupChoices
from mouse_control.setup_tui import ActionKind, SECTIONS, SetupSection
from mouse_control.setup_tui_curses import CursesSetupApp

from test_setup_tui import controller


EXPECTED_TOOLS = {
    "topology", "raw_observations", "feature_baseline", "usb_observations",
    "evidence", "conflicts", "repertoire", "logical_records", "differential",
    "dialogue", "timing", "dependency", "integrity",
    "dpi", "polling", "power", "freshness",
    "routing", "persistence", "reconnect", "restoration",
    "experiment", "actions", "information_gain", "authorized",
    "vendor_import", "import_review", "corpus",
}

ALLOWED_STATUSES = {
    "READY", "READ ONLY", "NEEDS HARDWARE", "NO EVIDENCE",
    "OBSERVED", "DECODED", "PROVEN", "DISABLED",
}


def empty_controller():
    return SimpleNamespace(
        lab_experiment=None,
        discovery_result=None,
        discovery_engine=None,
        vendor_capture_import=None,
        observed_hardware=SimpleNamespace(calibrated_dpi_cycle=()),
        choices=SetupChoices(),
    )


def test_lab_primary_routes_keep_full_lab_default_and_add_advanced_tools():
    app, _backend = controller()
    app.section_index = SECTIONS.index(SetupSection.LAB)
    app.discovery_complete = True
    app.discovery_result = SimpleNamespace(device=SimpleNamespace(ambiguous=False))

    actions = []
    labels = [row.text for row in app.detail_rows() if row.cursor_index is not None]
    for cursor in range(4):
        app.section_index = SECTIONS.index(SetupSection.LAB)
        app.row_cursor = cursor
        actions.append(app.handle_key("ENTER").kind)

    assert labels == [
        "Run Full Automatic Lab",
        "Advanced Tools",
        "Import Vendor Capture",
        "Continue to DPI configuration",
    ]
    assert actions == [
        ActionKind.RUN_DISCOVERY_LAB,
        ActionKind.OPEN_ADVANCED_TOOLS,
        ActionKind.IMPORT_VENDOR_CAPTURE,
        ActionKind.NONE,
    ]
    assert app.section is SetupSection.DPI


def test_expert_inventory_exposes_every_existing_tool_route_in_six_groups():
    assert {tool.tool_id for tool in TOOLS} == EXPECTED_TOOLS
    assert len(GROUPS) == 6
    assert tuple(tool for group in GROUPS for tool in tools_for_group(group)) == TOOLS
    assert TOOLS[0].group == "Inspect & Evidence"
    assert TOOLS[-1].group == "Capture & Corpus"
    assert set(LAB_INSTRUMENT_TO_TOOL) == set(LabInstrument)
    assert set(LAB_INSTRUMENT_TO_TOOL.values()) <= EXPECTED_TOOLS


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.tool_id)
def test_every_expert_tool_has_bounded_status_and_context(tool):
    app = empty_controller()
    statuses = tool_status(app, tool)
    context = tool_context(app, tool)

    assert statuses
    assert set(statuses) <= ALLOWED_STATUSES
    assert context and all(isinstance(line, str) and line for line in context)
    if tool.action is ExpertToolAction.INSPECT:
        assert "READ ONLY" in statuses


@pytest.mark.parametrize(
    ("tool_id", "expected_method"),
    (("authorized", "_run_discovery_lab"), ("vendor_import", "_run_vendor_capture_import")),
)
def test_executable_expert_routes_delegate_to_existing_safe_tui_actions(
    monkeypatch, tool_id, expected_method,
):
    app_state = empty_controller()
    if tool_id == "authorized":
        app_state.discovery_result = SimpleNamespace(device=SimpleNamespace(ambiguous=False))
        app_state.discovery_engine = SimpleNamespace()
    curses_app = CursesSetupApp(app_state)
    selected = next(tool for tool in TOOLS if tool.tool_id == tool_id)
    called = []
    previews = []
    monkeypatch.setattr(
        curses_app, "_confirm",
        lambda title, lines, **_kwargs: previews.append((title, lines)) or True,
    )
    monkeypatch.setattr(curses_app, expected_method, lambda: called.append(expected_method))

    curses_app._activate_expert_tool(selected)

    assert called == [expected_method]
    assert previews[0][0] == selected.title
    assert selected.description in previews[0][1]
    assert any(line.startswith("Status: ") for line in previews[0][1])
    assert previews[0][1][-1].startswith("No raw HID transmission")


@pytest.mark.parametrize("tool", [tool for tool in TOOLS if tool.action is ExpertToolAction.INSPECT])
def test_inspection_routes_preview_then_open_existing_state(monkeypatch, tool):
    curses_app = CursesSetupApp(empty_controller())
    opened = []
    monkeypatch.setattr(curses_app, "_confirm", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(curses_app, "_show_expert_tool_details", opened.append)

    curses_app._activate_expert_tool(tool)

    assert opened == [tool]


def test_disabled_authorized_experiment_opens_context_without_running(monkeypatch):
    curses_app = CursesSetupApp(empty_controller())
    selected = next(tool for tool in TOOLS if tool.tool_id == "authorized")
    opened = []
    run = []
    monkeypatch.setattr(curses_app, "_confirm", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(curses_app, "_show_expert_tool_details", opened.append)
    monkeypatch.setattr(curses_app, "_run_discovery_lab", lambda: run.append(True))

    curses_app._activate_expert_tool(selected)

    assert opened == [selected]
    assert run == []


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: "dashboard-" + tool.tool_id)
def test_every_tool_is_reachable_through_grouped_dashboard(monkeypatch, tool):
    curses_app = CursesSetupApp(empty_controller())
    group_index = GROUPS.index(tool.group)
    tool_index = tools_for_group(tool.group).index(tool)
    selections = iter((group_index, tool_index, None, None))
    opened = []
    monkeypatch.setattr(curses_app, "_expert_menu", lambda *_args, **_kwargs: next(selections))
    monkeypatch.setattr(curses_app, "_activate_expert_tool", opened.append)

    curses_app._open_advanced_tools()

    assert opened == [tool]
