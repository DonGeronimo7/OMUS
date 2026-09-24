# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import subprocess

import pytest
from packaging.version import Version

from mouse_control import updater


def result(code=0, out="", err=""):
    return subprocess.CompletedProcess([], code, out, err)


def future_release_version():
    current = Version(updater.__version__)
    major, minor, micro = (current.release + (0, 0, 0))[:3]
    return f"{major}.{minor}.{micro + 1}"


def release(version=None):
    return updater.Release(version or future_release_version(), ())


def test_capture_and_interactive_helpers_have_distinct_stdio(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return result()

    monkeypatch.setattr(updater.subprocess, "run", fake_run)
    updater._run_capture(["rpm", "-q", "mouse-control"])
    updater._run_interactive(["dnf", "upgrade", "mouse-control"])

    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["text"] is True
    assert "capture_output" not in calls[1][1]
    assert "stdin" not in calls[1][1]
    assert "stdout" not in calls[1][1]
    assert "stderr" not in calls[1][1]


@pytest.mark.parametrize(("kind", "manager", "query"), [
    ("rpm", "dnf", "rpm"),
    ("deb", "apt", "dpkg-query"),
])
def test_normal_package_transaction_uses_terminal_runner(monkeypatch, kind, manager, query):
    installation = updater.Installation(kind, Path("/usr/bin/mouse-control"), "mouse-control")
    monkeypatch.setattr(updater.shutil, "which", lambda command: f"/usr/bin/{command}")
    installed = [updater.__version__]
    captured = []
    interactive = []
    target = future_release_version()

    def run_capture(args):
        captured.append(args)
        suffix = "-1" if kind == "deb" else ""
        return result(out=installed[0] + suffix + "\n") if args[0] == query else result()

    def run_interactive(args):
        interactive.append(args)
        installed[0] = target
        return result()

    updater._package_update(
        installation, release(target), run_capture=run_capture, run_interactive=run_interactive)

    assert len(interactive) == 1
    assert manager in interactive[0]
    assert captured[-1][0] == query
    assert "--assumeyes" not in interactive[0]
    assert "--yes" not in interactive[0]


@pytest.mark.parametrize(("kind", "flag"), [
    ("rpm", "--assumeyes"),
    ("deb", "--yes"),
])
def test_assume_yes_remains_noninteractive(monkeypatch, kind, flag):
    installation = updater.Installation(kind, Path("/usr/bin/mouse-control"), "mouse-control")
    monkeypatch.setattr(updater.shutil, "which", lambda command: f"/usr/bin/{command}")
    installed = [updater.__version__]
    interactive = []
    target = future_release_version()

    def run_capture(args):
        suffix = "-1" if kind == "deb" else ""
        return result(out=installed[0] + suffix + "\n")

    def run_interactive(args):
        interactive.append(args)
        installed[0] = target
        return result()

    updater._package_update(
        installation, release(target), assume_yes=True,
        run_capture=run_capture, run_interactive=run_interactive)

    assert len(interactive) == 1
    assert flag in interactive[0]


def test_run_update_routes_package_transaction_to_interactive_runner(monkeypatch):
    installation = updater.Installation("rpm", Path("/usr/bin/mouse-control"), "mouse-control")
    target = future_release_version()
    installed = [updater.__version__]
    interactive = []
    captured = []
    monkeypatch.setattr(updater, "detect_installation", lambda _: installation)
    monkeypatch.setattr(updater, "_shadowed", lambda _: None)
    monkeypatch.setattr(updater, "is_service_active", lambda: False)
    monkeypatch.setattr(updater.shutil, "which", lambda command: f"/usr/bin/{command}")

    def run_capture(args):
        captured.append(args)
        return result(out=installed[0] + "\n")

    def run_interactive(args):
        interactive.append(args)
        installed[0] = target
        return result()

    assert updater.run_update(
        assume_yes=False,
        fetcher=lambda: release(target),
        runner=run_capture,
        interactive_runner=run_interactive,
        input_func=lambda _: "y",
    ) == 0
    assert len(interactive) == 1
    assert "dnf" in interactive[0]
    assert captured and captured[-1][0] == "rpm"


def test_keyboard_interrupt_during_package_transaction_cancels_safely(monkeypatch, capsys):
    installation = updater.Installation("rpm", Path("/usr/bin/mouse-control"), "mouse-control")
    monkeypatch.setattr(updater, "detect_installation", lambda _: installation)
    monkeypatch.setattr(updater, "_shadowed", lambda _: None)
    monkeypatch.setattr(updater, "is_service_active", lambda: False)
    monkeypatch.setattr(updater.shutil, "which", lambda command: f"/usr/bin/{command}")

    def interrupted(_args):
        raise KeyboardInterrupt

    rc = updater.run_update(
        assume_yes=True, fetcher=release,
        runner=lambda _args: result(out=updater.__version__ + "\n"),
        interactive_runner=interrupted,
    )
    assert rc == 0
    assert "Update cancelled" in capsys.readouterr().out


def test_interactive_failure_without_captured_streams_keeps_useful_error():
    completed = subprocess.CompletedProcess(["dnf"], 1)
    assert updater._package_error(completed) == (
        "Package manager did not install the requested release.")
