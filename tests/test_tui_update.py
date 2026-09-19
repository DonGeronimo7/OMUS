from copy import deepcopy
from pathlib import Path

from packaging.version import Version

from mouse_control import updater
from mouse_control.setup_tui import ActionKind, SECTIONS, SetupSection
from mouse_control.setup_tui_curses import CursesSetupApp
from test_setup_tui import controller as make_controller


def _future_version() -> str:
    current = Version(updater.__version__)
    major, minor, micro = (current.release + (0, 0, 0))[:3]
    return f"{major}.{minor}.{micro + 1}"


def _installation(kind: str) -> updater.Installation:
    paths = {
        "rpm": Path("/usr/bin/mouse-control"),
        "deb": Path("/usr/bin/mouse-control"),
        "appimage": Path("/opt/Mouse-Control.AppImage"),
        "pip": Path("/home/user/.local/bin/mouse-control"),
        "arch": Path("/usr/bin/mouse-control"),
        "source": Path("/checkout/src/mouse_control/app.py"),
        "unknown": Path("/opt/mouse-control"),
    }
    package = "mouse-control" if kind in {"rpm", "deb", "pip"} else None
    return updater.Installation(kind, paths[kind], package)


def _status(kind: str, *, newer: bool = True, supported: bool | None = None):
    installation = _installation(kind)
    latest = _future_version() if newer else updater.__version__
    if supported is None:
        supported = kind in {"rpm", "deb", "appimage", "pip"}
    reason = "Source/development checkouts use their source workflow." if kind == "source" else ""
    release = updater.Release(latest, ())
    return updater.UpdateStatus(
        updater.__version__, latest, newer, installation, release, supported, reason
    )


def test_entering_and_redrawing_update_never_runs_updater_operation():
    controller, _ = make_controller()
    calls = []
    app = CursesSetupApp(
        controller,
        update_inspector=lambda **_kwargs: calls.append("check"),
        update_runner=lambda **_kwargs: calls.append("update") or 0,
    )
    controller.section_index = SECTIONS.index(SetupSection.SERVICE)

    assert controller.handle_key("RIGHT").kind is ActionKind.NONE
    assert controller.section is SetupSection.UPDATE
    controller.detail_rows()
    controller.detail_rows()

    assert calls == []
    assert "not checked" in "\n".join(row.text for row in controller.detail_rows())
    assert app._footer_action() == "check"


def test_explicit_check_calls_updater_once_and_renders_installed_latest_state():
    controller, _ = make_controller()
    expected = _status("rpm")
    calls = []

    def inspect(**kwargs):
        calls.append(kwargs)
        return expected

    app = CursesSetupApp(controller, update_inspector=inspect)
    controller.section_index = SECTIONS.index(SetupSection.UPDATE)
    detected = controller.update_installation
    assert controller.handle_key("ENTER").kind is ActionKind.CHECK_UPDATE
    app._check_for_updates()

    assert calls == [{"installation": detected}]
    text = "\n".join(row.text for row in controller.detail_rows())
    assert f"Installed version: {updater.__version__}" in text
    assert f"Latest stable version: {expected.available_version}" in text
    assert "Installation type: RPM package (DNF)" in text
    assert "compatible update available" in text
    assert controller.row_count() == 2


def test_current_release_and_failed_check_are_factual_and_non_destructive():
    controller, _ = make_controller()
    before = deepcopy(controller.choices)
    controller.section_index = SECTIONS.index(SetupSection.UPDATE)
    controller.apply_update_status(_status("pip", newer=False))
    assert "installed version is current" in "\n".join(
        row.text for row in controller.detail_rows()
    )

    app = CursesSetupApp(
        controller,
        update_inspector=lambda **_kwargs: (_ for _ in ()).throw(
            updater.UpdateError("network unavailable")
        ),
    )
    app._check_for_updates()

    assert controller.choices == before
    assert controller.update_action_available is False
    assert "setup state is unchanged" in controller.status
    assert "network unavailable" in "\n".join(row.text for row in controller.detail_rows())


def test_source_checkout_is_clear_and_never_offers_update_action():
    controller, _ = make_controller()
    controller.section_index = SECTIONS.index(SetupSection.UPDATE)
    controller.apply_update_status(_status("source", supported=False))

    text = "\n".join(row.text for row in controller.detail_rows())
    assert "Source/development checkout" in text
    assert "source workflow" in text
    assert "Update Mouse Control" not in text
    assert controller.row_count() == 1


def test_supported_install_owners_keep_their_updater_owned_labels_and_action():
    expected = {
        "rpm": "RPM package (DNF)",
        "deb": "DEB package (APT)",
        "appimage": "AppImage",
        "pip": "Python/pip installation",
    }
    for kind, label in expected.items():
        controller, _ = make_controller()
        controller.section_index = SECTIONS.index(SetupSection.UPDATE)
        controller.apply_update_status(_status(kind))
        text = "\n".join(row.text for row in controller.detail_rows())
        assert f"Installation type: {label}" in text
        assert "Update Mouse Control" in text

    for kind in ("source", "unknown", "arch"):
        controller, _ = make_controller()
        controller.section_index = SECTIONS.index(SetupSection.UPDATE)
        controller.apply_update_status(_status(kind, supported=False))
        assert "Update Mouse Control" not in "\n".join(
            row.text for row in controller.detail_rows()
        )


def test_update_action_delegates_without_unattended_package_manager_flags():
    controller, _ = make_controller()
    controller.apply_update_status(_status("deb"))
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        print("Mouse Control was updated successfully.")
        return 0

    app = CursesSetupApp(controller, update_runner=run)
    app._confirm = lambda *_args, **_kwargs: True
    app._start_update()

    assert len(calls) == 1
    assert calls[0]["check"] is False
    assert calls[0]["assume_yes"] is False
    assert calls[0]["input_func"]("prompt") == "y"
    assert "finished without an error" in controller.status


def test_cancel_and_back_leave_update_and_setup_state_unchanged():
    controller, _ = make_controller()
    before = deepcopy(controller.choices)
    controller.section_index = SECTIONS.index(SetupSection.UPDATE)
    controller.apply_update_status(_status("appimage"))
    calls = []
    app = CursesSetupApp(
        controller, update_runner=lambda **_kwargs: calls.append(True) or 0
    )
    app._confirm = lambda *_args, **_kwargs: False

    app._start_update()
    assert calls == []
    assert controller.choices == before
    assert "cancelled" in controller.status

    controller.handle_key("BACK")
    assert controller.section is SetupSection.SERVICE
