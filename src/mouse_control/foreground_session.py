"""Systemd-supervised ownership for the interactive foreground session."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .service import (
    SERVICE_NAME,
    is_service_active,
    request_stop_service,
    restart_service,
    stop_service,
)


SESSION_UNIT = "omus-foreground.service"
SESSION_ENV = "MOUSE_CONTROL_FOREGROUND_SESSION"
SYSTEMD_RUN = "/usr/bin/systemd-run"


def _runtime_directory() -> Path:
    configured = os.environ.get("XDG_RUNTIME_DIR")
    return Path(configured) if configured else Path(f"/run/user/{os.getuid()}")


def _state_path() -> Path:
    return _runtime_directory() / "omus" / "foreground-session.json"


def _write_state(state: dict[str, object]) -> None:
    path = _state_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".foreground-session.", suffix=".tmp", dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            json.dump(state, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _read_state() -> dict[str, object] | None:
    path = _state_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def prepare() -> int:
    """Record prior runtime state, then suspend it before the TUI starts."""
    was_active = is_service_active()
    _write_state({"was_active": was_active, "preference": None})
    if was_active:
        request_stop_service()
    return 0


def complete_pending_suspension() -> None:
    """Wait for a queued stop before the TUI opens any hardware backend."""
    if not is_supervised():
        return
    state = _read_state()
    if state is not None and state.get("was_active") is True:
        stop_service()


def record_service_preference(enabled: bool) -> None:
    """Persist a service choice only after the configuration save succeeds."""
    state = _read_state()
    if state is None:
        return
    state["preference"] = "enabled" if enabled else "disabled"
    _write_state(state)


def restore() -> int:
    """Apply the saved preference or restore the pre-session active state."""
    path = _state_path()
    state = _read_state()
    if state is None:
        return 0

    preference = state.get("preference")
    should_run = preference == "enabled" or (
        preference is None and state.get("was_active") is True
    )
    if should_run:
        restart_service()
        if not is_service_active():
            raise RuntimeError(f"{SERVICE_NAME} did not become active after restoration")
    path.unlink(missing_ok=True)
    return 0


def _quote_systemd_argument(argument: str) -> str:
    return '"' + argument.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _systemd_command(arguments: list[str]) -> str:
    return " ".join(_quote_systemd_argument(argument) for argument in arguments)


def is_supervised() -> bool:
    return os.environ.get(SESSION_ENV) == "1"


def should_supervise(arguments: list[str], *, interactive: bool) -> bool:
    if is_supervised() or not interactive:
        return False
    return not arguments or arguments[0] in {"setup", "tui"}


def launch(arguments: list[str]) -> int:
    """Replace the launcher with systemd-run supervising the canonical TUI."""
    systemd_run = shutil.which("systemd-run") or SYSTEMD_RUN
    python = sys.executable
    helper = [python, "-m", "mouse_control.foreground_session"]
    command = [python, "-m", "mouse_control", *arguments]
    run_arguments = [
        systemd_run,
        "--user",
        "--pty",
        "--wait",
        "--collect",
        f"--unit={SESSION_UNIT.removesuffix('.service')}",
        "--service-type=exec",
        f"--setenv={SESSION_ENV}=1",
        "--property=KillMode=control-group",
        "--property=TimeoutStopSec=15s",
        f"--property=ExecStartPre={_systemd_command([*helper, 'prepare'])}",
        f"--property=ExecStopPost={_systemd_command([*helper, 'restore'])}",
        *command,
    ]
    os.execv(systemd_run, run_arguments)
    raise AssertionError("os.execv returned unexpectedly")


def main(arguments: list[str] | None = None) -> int:
    selected = sys.argv[1:] if arguments is None else arguments
    if selected == ["prepare"]:
        return prepare()
    if selected == ["restore"]:
        return restore()
    print("Expected foreground-session action: prepare or restore", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
