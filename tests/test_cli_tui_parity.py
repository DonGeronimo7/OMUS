from pathlib import Path

from mouse_control import updater
from mouse_control.cli import _build_parser
from mouse_control.product_capabilities import CAPABILITIES
from mouse_control.setup_tui import ActionKind, SetupSection
from test_setup_tui import controller as make_controller


def _public_cli_commands():
    parser = _build_parser()
    subparsers = next(
        action for action in parser._actions if getattr(action, "choices", None)
    )
    return set(subparsers.choices)


def test_every_public_mouse_control_command_has_a_tui_route():
    mapped = {item.cli for item in CAPABILITIES}
    assert _public_cli_commands() <= mapped
    assert all(item.tui_route and item.shared_implementation for item in CAPABILITIES)


def test_canonical_tui_has_required_product_surfaces():
    assert {
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
    } <= set(SetupSection)


def test_parser_mechanics_are_not_invented_as_product_capabilities():
    assert all(not item.cli.startswith("--") for item in CAPABILITIES)


def test_service_update_and_tools_rows_dispatch_canonical_actions():
    controller, _ = make_controller()
    controller.section_index = tuple(SetupSection).index(SetupSection.SERVICE)
    controller.row_cursor = 5
    action = controller.activate()
    assert (action.kind, action.payload) == (ActionKind.SERVICE_ACTION, "restart")

    controller.section_index = tuple(SetupSection).index(SetupSection.UPDATE)
    controller.row_cursor = 0
    assert controller.activate().kind is ActionKind.CHECK_UPDATE
    state = updater.UpdateStatus(
        updater.__version__,
        "999.0",
        True,
        updater.Installation("rpm", Path("/usr/bin/mouse-control"), "mouse-control"),
        updater.Release("999.0", ()),
        True,
    )
    controller.apply_update_status(state)
    controller.row_cursor = 1
    assert controller.activate().kind is ActionKind.START_UPDATE

    controller.section_index = tuple(SetupSection).index(SetupSection.TOOLS)
    controller.row_cursor = 0
    assert controller.activate().kind is ActionKind.OPEN_PRODUCT_TOOL
