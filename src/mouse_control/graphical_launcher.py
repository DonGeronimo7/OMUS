"""Desktop launcher for the canonical terminal-native Mouse Control TUI."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


TERMINAL_CANDIDATES = (
    "xdg-terminal-exec",
    "kitty",
    "foot",
    "alacritty",
    "wezterm",
    "gnome-terminal",
    "kgx",
    "konsole",
    "xfce4-terminal",
    "mate-terminal",
    "xterm",
)


def _mouse_control_command() -> list[str]:
    appimage = os.environ.get("MOUSE_CONTROL_APPIMAGE")
    if appimage:
        candidate = Path(appimage)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate)]
    executable = shutil.which("mouse-control")
    if executable:
        return [executable]
    return [sys.executable, "-m", "mouse_control"]


def _configured_terminal() -> list[str] | None:
    configured = os.environ.get("TERMINAL", "").strip()
    if not configured:
        return None
    try:
        arguments = shlex.split(configured)
    except ValueError:
        return None
    if not arguments:
        return None
    executable = shutil.which(arguments[0])
    if not executable:
        return None
    return [executable, *arguments[1:]]


def _terminal_command(terminal: list[str], command: list[str]) -> list[str]:
    executable, *configured_arguments = terminal
    name = Path(executable).name
    prefix = [executable, *configured_arguments]
    if name == "xdg-terminal-exec":
        return [*prefix, "--", *command]
    if name == "kitty":
        return [*prefix, "--class", "MouseControl", "--title", "Mouse Control", *command]
    if name == "foot":
        return [*prefix, "--app-id=mouse-control", "--title=Mouse Control", *command]
    if name == "alacritty":
        return [*prefix, "--class", "MouseControl,MouseControl", "--title", "Mouse Control", "-e", *command]
    if name == "wezterm":
        return [*prefix, "start", "--class", "MouseControl", "--always-new-process", "--", *command]
    if name in {"gnome-terminal", "kgx", "mate-terminal"}:
        return [*prefix, "--title=Mouse Control", "--", *command]
    if name == "konsole":
        return [*prefix, "--new-tab", "-p", "tabtitle=Mouse Control", "-e", *command]
    if name == "xfce4-terminal":
        return [*prefix, "--title=Mouse Control", "--execute", *command]
    if name == "xterm":
        return [*prefix, "-T", "Mouse Control", "-e", *command]
    # A user-supplied terminal takes precedence even when it is not one of the
    # recognized candidates.  The conventional -e interface is the only safe
    # generic contract available for that explicit override.
    return [*prefix, "-e", *command]


def select_terminal() -> list[str] | None:
    configured = _configured_terminal()
    if configured is not None:
        return configured
    for candidate in TERMINAL_CANDIDATES:
        executable = shutil.which(candidate)
        if executable:
            return [executable]
    return None


def _report_error(message: str) -> None:
    print(message, file=sys.stderr)
    notifier = shutil.which("notify-send")
    if notifier:
        subprocess.run(
            [notifier, "Mouse Control", message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> int:
    terminal = select_terminal()
    if terminal is None:
        _report_error(
            "Mouse Control requires a terminal emulator for its setup interface. "
            "Install a supported terminal or set $TERMINAL."
        )
        return 1
    arguments = _terminal_command(terminal, _mouse_control_command())
    try:
        subprocess.Popen(arguments, close_fds=True, start_new_session=True)
    except OSError as exc:
        _report_error(f"Mouse Control could not start the terminal: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
