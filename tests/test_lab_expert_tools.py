# SPDX-License-Identifier: AGPL-3.0-or-later
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


def lab_app():
    app_state, _backend = controller()
    app_state.section_index = SECTIONS.index(SetupSection.LAB)
    return CursesSetupApp(app_state)


def _open_tool(curses_app, tool):
    curses_app._open_advanced_tools()
    curses_app._lab_views[-1].cursor = GROUPS.index(tool.group)
    assert curses_app._handle_lab_view_key("ENTER") is True
    curses_app._lab_views[-1].cursor = tools_for_group(tool.group).index(tool)
    assert curses_app._handle_lab_view_key("ENTER") is True


def test_drill_down_replaces_content_without_opening_a_modal(monkeypatch):
    curses_app = lab_app()
    timing = next(tool for tool in TOOLS if tool.tool_id == "timing")
    monkeypatch.setattr(
        curses_app, "_modal",
        lambda *_args, **_kwargs: pytest.fail("ordinary navigation opened a modal"),
    )

    _open_tool(curses_app, timing)

    assert len(curses_app._lab_views) == 3
    assert curses_app._lab_views[-1].tool is timing
    assert curses_app._lab_breadcrumb() == (
        "Discovery Lab › Advanced Tools › Protocol Analysis › Protocol Timing Profiler"
    )


def test_back_restores_parent_view_and_its_selection_state():
    curses_app = lab_app()
    timing = next(tool for tool in TOOLS if tool.tool_id == "timing")
    group_cursor = GROUPS.index(timing.group)
    tool_cursor = tools_for_group(timing.group).index(timing)

    _open_tool(curses_app, timing)
    assert curses_app._handle_lab_view_key("BACK") is True
    assert curses_app._lab_views[-1].kind == "tools"
    assert curses_app._lab_views[-1].cursor == tool_cursor
    assert curses_app._handle_lab_view_key("BACK") is True
    assert curses_app._lab_views[-1].kind == "groups"
    assert curses_app._lab_views[-1].cursor == group_cursor
    assert curses_app._handle_lab_view_key("BACK") is True
    assert curses_app._lab_views == []


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: "dashboard-" + tool.tool_id)
def test_every_tool_is_reachable_through_replacement_view_stack(monkeypatch, tool):
    curses_app = lab_app()
    monkeypatch.setattr(
        curses_app, "_modal",
        lambda *_args, **_kwargs: pytest.fail("ordinary navigation opened a modal"),
    )

    _open_tool(curses_app, tool)

    assert curses_app._lab_views[-1].kind == "detail"
    assert curses_app._lab_views[-1].tool is tool


@pytest.mark.parametrize(
    "tool",
    [tool for tool in TOOLS if tool.action is ExpertToolAction.INSPECT],
    ids=lambda tool: "inspection-" + tool.tool_id,
)
def test_inspection_detail_is_read_only_and_scrollable_without_enter_action(tool):
    curses_app = lab_app()
    _open_tool(curses_app, tool)

    rows = curses_app._lab_view_rows()
    assert rows[0].text == tool.description
    assert any(row.text.startswith("Status: ") for row in rows)
    assert all(row.cursor_index is None for row in rows)
    assert curses_app._lab_view_enter_enabled() is False
    assert curses_app._lab_view_is_inspection() is True
    curses_app._handle_lab_view_key("LAST")
    assert curses_app._lab_views[-1].offset == len(rows) - 1
    curses_app._handle_lab_view_key("FIRST")
    assert curses_app._lab_views[-1].offset == 0


def test_authorized_route_delegates_only_when_existing_gates_enable_it(monkeypatch):
    curses_app = lab_app()
    tool = next(tool for tool in TOOLS if tool.tool_id == "authorized")
    ran = []
    monkeypatch.setattr(curses_app, "_run_discovery_lab", lambda: ran.append(True))

    _open_tool(curses_app, tool)
    curses_app._handle_lab_view_key("ENTER")
    assert ran == []

    curses_app.controller.discovery_result = SimpleNamespace(
        device=SimpleNamespace(ambiguous=False),
    )
    curses_app.controller.discovery_engine = SimpleNamespace()
    assert curses_app._lab_view_enter_enabled() is True
    curses_app._handle_lab_view_key("ENTER")
    assert ran == [True]


def test_vendor_capture_uses_pages_until_the_short_file_prompt(monkeypatch):
    curses_app = lab_app()
    tool = next(tool for tool in TOOLS if tool.tool_id == "vendor_import")
    calls = []
    monkeypatch.setattr(
        curses_app, "_run_vendor_capture_import",
        lambda *, show_intro=True: calls.append(show_intro),
    )

    _open_tool(curses_app, tool)
    curses_app._handle_lab_view_key("ENTER")
    assert curses_app._lab_views[-1].kind == "vendor"
    assert calls == []
    curses_app._handle_lab_view_key("ENTER")
    assert calls == [False]


def test_help_remains_a_true_modal_interaction(monkeypatch):
    curses_app = lab_app()
    curses_app._open_advanced_tools()
    shown = []
    monkeypatch.setattr(curses_app, "_show_help", lambda: shown.append(True))

    assert curses_app._handle_lab_view_key("HELP") is True
    assert shown == [True]
    assert curses_app._lab_views[-1].kind == "groups"


def test_page_navigation_closes_lab_drilldown_before_controller_handles_it():
    curses_app = lab_app()
    curses_app._open_advanced_tools()

    assert curses_app._handle_lab_view_key("RIGHT") is False
    assert curses_app._lab_views == []
