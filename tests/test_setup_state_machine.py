from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mouse_control import cli, setup_entry
from mouse_control.discovery import MouseDevice
from mouse_control.hardware import HardwareError
from mouse_control.hardware.capabilities import (
    DpiCapabilities,
    DpiRange,
    HardwareCapabilities,
    ReportRateCapabilities,
)
from mouse_control.setup_flow import SetupChoices, discover_choices
from mouse_control.setup_tui import (
    ActionKind,
    SECTIONS,
    SetupController,
    SetupSection,
    run_setup_tui,
)
import mouse_control.setup_tui_curses as setup_tui_curses


MOUSE1 = MouseDevice("State Mouse", "/dev/input/state-one", vendor=0x1111, product=1, phys="usb-1")
MOUSE2 = MouseDevice("Second Mouse", "/dev/input/state-two", vendor=0x2222, product=2, phys="usb-2")


class PolicyBackend:
    protocol_adapter_name = "State Protocol"
    has_proven_learned_adapter = False

    def __init__(
        self,
        *,
        dpi_readable=True,
        dpi_writable=True,
        polling_readable=True,
        polling_writable=True,
        initial_dpi=800,
        initial_rate=1000,
    ):
        self.dpi_readable = dpi_readable
        self.dpi_writable = dpi_writable
        self.polling_readable = polling_readable
        self.polling_writable = polling_writable
        self.dpi = initial_dpi
        self.rate = initial_rate
        self.set_dpi_calls: list[int] = []
        self.closed = False

    def get_capabilities(self, _device):
        return HardwareCapabilities(
            dpi=DpiCapabilities(
                readable=self.dpi_readable,
                # Deliberately advertise a protocol write primitive even when
                # backend policy refuses it. Setup must obey backend policy.
                writable=True,
                ranges=(DpiRange(200, 12000, 50),),
            ),
            report_rate=ReportRateCapabilities(
                readable=self.polling_readable,
                writable=True,
                values=(125, 250, 500, 1000),
            ),
        )

    def supports_dpi(self, _device):
        return self.dpi_writable

    def get_dpi_values(self, _device):
        return []

    def get_dpi(self, _device):
        return self.dpi if self.dpi_readable or self.dpi_writable else None

    def set_dpi(self, _device, value):
        self.set_dpi_calls.append(value)
        self.dpi = value
        return value

    def supports_polling_rate(self, _device):
        return self.polling_readable

    def supports_polling_rate_writes(self, _device):
        return self.polling_writable

    def get_polling_rates(self, _device):
        return [125, 250, 500, 1000] if self.polling_readable else []

    def get_polling_rate(self, _device):
        return self.rate if self.polling_readable else None

    def supports_dpi_events(self, _device):
        return False

    def close(self):
        self.closed = True


class FailedDpiWriteBackend(PolicyBackend):
    def set_dpi(self, _device, value):
        self.set_dpi_calls.append(value)
        # Simulate a command echo with hardware stubbornly remaining at the old
        # value. Setup must reject it after readback.
        return value


class DpiDiscoveryFailureBackend(PolicyBackend):
    def get_capabilities(self, _device):
        raise HardwareError("DPI probe timed out")

    def supports_dpi(self, _device):
        raise HardwareError("DPI probe timed out")



def choices_factory(existing):
    dpi = existing.get("dpi", {})
    polling = existing.get("polling", {})
    return SetupChoices(
        stages=list(dpi.get("stages", [800, 1500, 2000, 2500, 3000])),
        active_dpi=dpi.get("active", 800),
        polling_rate=polling.get("rate_hz"),
        mappings=dict(existing.get("remap", {"BTN_LEFT": "passthrough"})),
    )


def make_controller(backend=None, *, existing=None):
    backend = backend or PolicyBackend()
    return SetupController(
        [MOUSE1],
        existing or {},
        choices_factory=choices_factory,
        backend_factory=lambda _device: backend,
    ), backend


@pytest.mark.parametrize(
    "section,previous",
    [
        (SetupSection.DEVICE, SetupSection.DEVICE),
        (SetupSection.HARDWARE, SetupSection.DEVICE),
        (SetupSection.DPI, SetupSection.HARDWARE),
        (SetupSection.POLLING, SetupSection.DPI),
        (SetupSection.BUTTONS, SetupSection.POLLING),
        (SetupSection.SERVICE, SetupSection.BUTTONS),
        (SetupSection.REVIEW, SetupSection.SERVICE),
    ],
)
def test_back_from_every_screen_is_logical(section, previous):
    controller, _ = make_controller()
    controller.section_index = SECTIONS.index(section)
    controller.handle_key("BACK")
    assert controller.section is previous


@pytest.mark.parametrize("section", SECTIONS)
def test_cancel_from_every_screen_is_deterministic(section):
    controller, _ = make_controller()
    controller.section_index = SECTIONS.index(section)
    action = controller.handle_key("QUIT")
    assert action.kind is ActionKind.CANCEL
    assert controller.section is section


@pytest.mark.parametrize(
    "row,target",
    [
        (1, SetupSection.DPI),
        (2, SetupSection.POLLING),
        (3, SetupSection.BUTTONS),
    ],
)
def test_review_edit_always_returns_to_review(row, target):
    controller, _ = make_controller()
    controller.section_index = SECTIONS.index(SetupSection.REVIEW)
    controller.row_cursor = row
    controller.handle_key("ENTER")
    assert controller.section is target
    controller.handle_key("RIGHT")
    assert controller.section is SetupSection.REVIEW


@pytest.mark.parametrize(
    "dpi_readable,dpi_writable,polling_readable,polling_writable,expected",
    [
        (True, True, True, True, (True, True, True, True)),
        (True, True, True, False, (True, True, True, False)),
        (False, False, True, True, (False, False, True, True)),
        (True, True, False, False, (True, True, False, False)),
        (False, False, False, False, (False, False, False, False)),
    ],
)
def test_capability_combinations_remain_independent(
    dpi_readable,
    dpi_writable,
    polling_readable,
    polling_writable,
    expected,
):
    backend = PolicyBackend(
        dpi_readable=dpi_readable,
        dpi_writable=dpi_writable,
        polling_readable=polling_readable,
        polling_writable=polling_writable,
    )
    choices = SetupChoices()
    discover_choices(backend, MOUSE1, choices)
    assert (
        choices.dpi_readable,
        choices.dpi_writable,
        choices.polling_readable,
        choices.polling_writable,
    ) == expected


def test_dpi_discovery_exception_does_not_erase_polling_support():
    backend = DpiDiscoveryFailureBackend(
        dpi_readable=False,
        dpi_writable=False,
        polling_readable=True,
        polling_writable=True,
    )
    choices = SetupChoices()
    discover_choices(backend, MOUSE1, choices)
    assert not choices.dpi_readable
    assert not choices.dpi_writable
    assert choices.polling_readable
    assert choices.polling_writable
    assert choices.polling_rates == [1000, 500, 250, 125]


def test_failed_dpi_readback_does_not_change_accepted_stage():
    controller, backend = make_controller(FailedDpiWriteBackend(initial_dpi=800))
    assert controller.choices.stages[0] == 800
    assert controller.set_dpi_value(0, 850) is False
    assert backend.set_dpi_calls == [850]
    assert controller.choices.stages[0] == 800
    assert controller.choices.current_dpi == 800
    assert 850 not in controller.choices.verified_dpi_values


def test_device_switch_preserves_reusable_config_but_not_runtime_discovery_state():
    first = PolicyBackend(initial_dpi=800, initial_rate=1000)
    second = PolicyBackend(initial_dpi=1200, initial_rate=500)
    existing = {
        "dpi": {"active": 2500, "stages": [800, 1500, 2000, 2500, 3000]},
        "polling": {"rate_hz": 500},
        "remap": {"BTN_EXTRA": "key:KEY_F13"},
    }
    controller = SetupController(
        [MOUSE1, MOUSE2],
        existing,
        choices_factory=choices_factory,
        backend_factory=lambda device: first if device is MOUSE1 else second,
    )
    controller.discovery_complete = True
    controller.discovery_result = SimpleNamespace(protocol=object(), capabilities={})
    controller.choices.measured_polling_rate = 1000

    controller.handle_key("DOWN")
    action = controller.handle_key("ENTER")

    assert action.kind is ActionKind.AUTOMATIC_DISCOVERY
    assert controller.selected is MOUSE2
    assert controller.choices.stages == [800, 1500, 2000, 2500, 3000]
    assert controller.choices.mappings == {"BTN_EXTRA": "key:KEY_F13"}
    assert controller.choices.original_dpi == 1200
    assert controller.choices.current_dpi == 1200
    assert controller.choices.measured_polling_rate is None
    assert controller.discovery_result is None
    assert controller.discovery_complete is False
    assert first.closed
    assert first.set_dpi_calls[-1] == 800


def test_back_from_dpi_after_normal_discovery_returns_to_hardware():
    controller, _ = make_controller()
    action = controller.handle_key("ENTER")
    assert action.kind is ActionKind.AUTOMATIC_DISCOVERY
    controller.discovery_complete = True
    controller.row_cursor = 1  # writable device: Continue to DPI
    controller.handle_key("ENTER")
    assert controller.section is SetupSection.DPI
    controller.handle_key("BACK")
    assert controller.section is SetupSection.HARDWARE


def test_interrupt_inside_curses_restores_temporary_dpi(monkeypatch):
    backend = PolicyBackend(initial_dpi=1200)

    def interrupt(app):
        app.controller.backend.set_dpi(app.controller.selected, 1500)
        raise KeyboardInterrupt

    monkeypatch.setattr(setup_tui_curses, "run_curses", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_setup_tui(
            [MOUSE1],
            {},
            choices_factory=choices_factory,
            backend_factory=lambda _device: backend,
        )

    assert backend.dpi == 1200
    assert backend.set_dpi_calls[-2:] == [1500, 1200]


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), EOFError()])
def test_tui_entry_interruptions_restore_running_service_and_do_not_save(interruption):
    with (
        patch.object(cli, "is_service_active", return_value=True),
        patch.object(cli, "stop_service") as stop,
        patch.object(cli, "restart_service") as restart,
        patch.object(cli, "get_mouse_devices", return_value=[MOUSE1]),
        patch.object(cli, "_load_setup_config", return_value={}),
        patch.object(cli, "save_config") as save,
        patch.object(setup_entry, "run_setup_tui", side_effect=interruption),
    ):
        assert setup_entry.run_tui_setup_wizard() == 1

    stop.assert_called_once()
    restart.assert_called_once()
    save.assert_not_called()


def test_tui_entry_handled_exception_restores_running_service_and_does_not_save():
    with (
        patch.object(cli, "is_service_active", return_value=True),
        patch.object(cli, "stop_service"),
        patch.object(cli, "restart_service") as restart,
        patch.object(cli, "get_mouse_devices", return_value=[MOUSE1]),
        patch.object(cli, "_load_setup_config", return_value={}),
        patch.object(cli, "save_config") as save,
        patch.object(setup_entry, "run_setup_tui", side_effect=RuntimeError("broken UI")),
    ):
        assert setup_entry.run_tui_setup_wizard() == 1

    restart.assert_called_once()
    save.assert_not_called()


def test_tui_entry_eof_with_inactive_service_does_not_start_service():
    with (
        patch.object(cli, "is_service_active", return_value=False),
        patch.object(cli, "stop_service") as stop,
        patch.object(cli, "restart_service") as restart,
        patch.object(cli, "get_mouse_devices", return_value=[MOUSE1]),
        patch.object(cli, "_load_setup_config", return_value={}),
        patch.object(setup_entry, "run_setup_tui", side_effect=EOFError()),
    ):
        assert setup_entry.run_tui_setup_wizard() == 1

    stop.assert_not_called()
    restart.assert_not_called()
