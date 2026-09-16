from types import SimpleNamespace

from mouse_control.setup_flow import SetupChoices
from mouse_control.setup_tui_curses import DpiEditSession


class FakeBackend:
    def __init__(self, dpi=800):
        self.dpi = dpi
        self.set_calls = []

    def get_dpi(self, _device):
        return self.dpi

    def set_dpi(self, _device, value):
        self.set_calls.append(value)
        self.dpi = value
        return value


def controller(*, dpi=800):
    backend = FakeBackend(dpi)
    choices = SetupChoices(
        stages=[800, 1500, 2000, 2500, 3000],
        active_dpi=800,
        original_dpi=800,
        dpi_values=[800, 1500, 2000, 2500, 3000],
        dpi_writable=True,
    )
    return SimpleNamespace(
        backend=backend,
        selected=object(),
        choices=choices,
        status="",
    )


def test_live_dpi_test_does_not_commit_stage():
    app = controller()
    edit = DpiEditSession(app, 0)

    assert edit.test_live(1500) is True
    assert app.backend.dpi == 1500
    assert app.choices.stages[0] == 800
    assert app.choices.active_dpi == 800
    assert app.choices.dpi_changed is False


def test_accept_commits_only_after_verified_live_test():
    app = controller()
    edit = DpiEditSession(app, 0)

    assert edit.test_live(1500) is True
    calls_before_accept = list(app.backend.set_calls)
    assert edit.accept(1500) is True

    assert app.backend.set_calls == calls_before_accept
    assert app.choices.stages[0] == 1500
    assert app.choices.active_dpi == 1500
    assert app.choices.dpi_changed is True


def test_accept_untested_value_verifies_it_before_commit():
    app = controller()
    edit = DpiEditSession(app, 2)

    assert edit.accept(2500) is True
    assert app.backend.set_calls == [2500]
    assert app.choices.stages[2] == 2500
    assert app.choices.dpi_changed is True


def test_cancel_restores_hardware_and_keeps_stage_unchanged():
    app = controller(dpi=1500)
    edit = DpiEditSession(app, 1)

    assert edit.test_live(2500) is True
    edit.cancel()

    assert app.backend.dpi == 1500
    assert app.backend.set_calls[-1] == 1500
    assert app.choices.stages[1] == 1500
    assert app.choices.dpi_changed is False


def test_set_to_current_uses_physical_current_dpi_without_auto_commit():
    app = controller(dpi=2000)
    edit = DpiEditSession(app, 4)

    assert edit.set_to_current() == 2000
    assert edit.candidate == 2000
    assert edit.tested_value == 2000
    assert app.choices.stages[4] == 3000
    assert app.choices.dpi_changed is False

    assert edit.accept() is True
    assert app.choices.stages[4] == 2000


def test_unsupported_dpi_never_writes_or_commits():
    app = controller()
    edit = DpiEditSession(app, 0)

    assert edit.test_live(825) is False
    assert app.backend.set_calls == []
    assert app.choices.stages[0] == 800
    assert app.choices.dpi_changed is False
