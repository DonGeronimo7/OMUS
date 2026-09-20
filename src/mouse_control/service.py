from pathlib import Path
import os
import shutil
import stat
import subprocess
import tempfile


SERVICE_NAME = "omus.service"
LEGACY_SERVICE_NAME = "mouse-control.service"
SYSTEMCTL = "/usr/bin/systemctl"


class ServiceNotInstalled(RuntimeError):
    pass


def service_path() -> Path:
    return Path.home() / ".config/systemd/user" / SERVICE_NAME


def legacy_service_path() -> Path:
    return Path.home() / ".config/systemd/user" / LEGACY_SERVICE_NAME


def _installed_service_name() -> str:
    return SERVICE_NAME if service_path().is_file() else LEGACY_SERVICE_NAME


def _installed_service_names() -> list[str]:
    names = []
    if service_path().is_file():
        names.append(SERVICE_NAME)
    if legacy_service_path().is_file():
        names.append(LEGACY_SERVICE_NAME)
    return names


def _quote_exec_argument(argument: str) -> str:
    """Quote one systemd ExecStart argument without invoking a shell."""
    return '"' + argument.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_service_text(executable: str) -> str:
    """Return the user service, retaining the executable selected at install time."""
    return f"""[Unit]
Description=OMUS mouse remapping service
Conflicts=mouse-control.service
After=graphical-session-pre.target
PartOf=graphical-session.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart={_quote_exec_argument(executable)} run
Restart=on-failure
RestartSec=3
TimeoutStopSec=15
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true

[Install]
WantedBy=graphical-session.target
"""


def is_service_active() -> bool:
    return any(subprocess.run(
        [SYSTEMCTL, "--user", "is-active", "--quiet", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0 for name in (SERVICE_NAME, LEGACY_SERVICE_NAME))


def install_service(*, start: bool = True) -> None:
    exe = os.environ.get("APPIMAGE") or os.environ.get("OMUS_APPIMAGE") or shutil.which("omus")
    if not exe:
        raise RuntimeError("omus executable not found")
    executable = Path(exe).resolve(strict=True)
    mode = executable.stat().st_mode
    if not stat.S_ISREG(mode) or mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError("omus executable must be a non-writable regular file")

    path = service_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise RuntimeError("refusing to replace a symlinked user service")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{SERVICE_NAME}.", suffix=".tmp", dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(build_service_text(str(executable)))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)

    subprocess.run(
        [SYSTEMCTL, "--user", "daemon-reload"],
        check=True,
    )

    # Stop and disable the former unit before enabling OMUS.  This ordering
    # prevents two evdev grabbers while retaining the old unit file as a
    # recoverable compatibility artifact.
    if legacy_service_path().is_file():
        subprocess.run([SYSTEMCTL, "--user", "disable", "--now", LEGACY_SERVICE_NAME], check=False)

    # Remove obsolete default.target links when migrating the generated unit.
    subprocess.run([SYSTEMCTL, "--user", "disable", SERVICE_NAME], check=True)
    command = [SYSTEMCTL, "--user", "enable"]
    if start:
        command.append("--now")
    command.append(SERVICE_NAME)
    subprocess.run(command, check=True)


def start_service() -> None:
    _require_installed()
    subprocess.run(
        [SYSTEMCTL, "--user", "start", _installed_service_name()],
        check=True,
    )


def stop_service() -> None:
    names = _installed_service_names()
    if names:
        subprocess.run([SYSTEMCTL, "--user", "stop", *names], check=True)


def request_stop_service() -> None:
    """Queue a stop without delaying the supervised foreground process."""
    names = _installed_service_names()
    if names:
        subprocess.run([SYSTEMCTL, "--user", "--no-block", "stop", *names], check=True)


def disable_service() -> None:
    if not service_path().is_file() and not legacy_service_path().is_file():
        return
    subprocess.run([SYSTEMCTL, "--user", "disable", *_installed_service_names()], check=True)


def restart_service() -> None:
    _require_installed()
    subprocess.run(
        [SYSTEMCTL, "--user", "restart", _installed_service_name()],
        check=True,
    )


def _require_installed() -> None:
    if not service_path().is_file() and not legacy_service_path().is_file():
        raise ServiceNotInstalled("OMUS service is not installed. Run: omus install-service")


def status_service() -> int:
    """Print the small, stable status summary appropriate for a CLI command."""
    if not service_path().is_file() and not legacy_service_path().is_file():
        print("OMUS service is not installed. Run: omus install-service")
        return 1
    name = SERVICE_NAME if service_path().is_file() else LEGACY_SERVICE_NAME
    active = subprocess.run([SYSTEMCTL, "--user", "is-active", name],
                            capture_output=True, text=True)
    enabled = subprocess.run([SYSTEMCTL, "--user", "is-enabled", name],
                             capture_output=True, text=True)
    active_text = active.stdout.strip() or ("failed" if active.returncode else "unknown")
    enabled_text = enabled.stdout.strip() or "disabled"
    label = "OMUS service" if name == SERVICE_NAME else "OMUS service (legacy unit)"
    print(f"{label}: installed, {active_text}, {enabled_text}")
    return 0 if active.returncode == 0 else active.returncode or 1
