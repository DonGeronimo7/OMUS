from pathlib import Path
import os
import shutil
import stat
import subprocess
import tempfile


SERVICE_NAME = "mouse-control.service"
SYSTEMCTL = "/usr/bin/systemctl"


class ServiceNotInstalled(RuntimeError):
    pass


def service_path() -> Path:
    return Path.home() / ".config/systemd/user" / SERVICE_NAME


def _quote_exec_argument(argument: str) -> str:
    """Quote one systemd ExecStart argument without invoking a shell."""
    return '"' + argument.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_service_text(executable: str) -> str:
    """Return the user service, retaining the executable selected at install time."""
    return f"""[Unit]
Description=Mouse Control remapping service

[Service]
Type=simple
ExecStart={_quote_exec_argument(executable)} run
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true

[Install]
WantedBy=default.target
"""


def is_service_active() -> bool:
    result = subprocess.run(
        [SYSTEMCTL, "--user", "is-active", "--quiet", SERVICE_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def install_service(*, start: bool = True) -> None:
    exe = shutil.which("mouse-control")
    if not exe:
        raise RuntimeError("mouse-control executable not found")
    executable = Path(exe).resolve(strict=True)
    mode = executable.stat().st_mode
    if not stat.S_ISREG(mode) or mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError("mouse-control executable must be a non-writable regular file")

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

    command = [SYSTEMCTL, "--user", "enable"]
    if start:
        command.append("--now")
    command.append(SERVICE_NAME)
    subprocess.run(command, check=True)


def start_service() -> None:
    _require_installed()
    subprocess.run(
        [SYSTEMCTL, "--user", "start", SERVICE_NAME],
        check=True,
    )


def stop_service() -> None:
    subprocess.run(
        [SYSTEMCTL, "--user", "stop", SERVICE_NAME],
        check=True,
    )


def disable_service() -> None:
    if not service_path().is_file():
        return
    subprocess.run(
        [SYSTEMCTL, "--user", "disable", SERVICE_NAME],
        check=True,
    )


def restart_service() -> None:
    _require_installed()
    subprocess.run(
        [SYSTEMCTL, "--user", "restart", SERVICE_NAME],
        check=True,
    )


def _require_installed() -> None:
    if not service_path().is_file():
        raise ServiceNotInstalled("mouse-control service is not installed. Run: mouse-control install-service")


def status_service() -> int:
    """Print the small, stable status summary appropriate for a CLI command."""
    if not service_path().is_file():
        print("mouse-control service is not installed. Run: mouse-control install-service")
        return 1
    active = subprocess.run([SYSTEMCTL, "--user", "is-active", SERVICE_NAME],
                            capture_output=True, text=True)
    enabled = subprocess.run([SYSTEMCTL, "--user", "is-enabled", SERVICE_NAME],
                             capture_output=True, text=True)
    active_text = active.stdout.strip() or ("failed" if active.returncode else "unknown")
    enabled_text = enabled.stdout.strip() or "disabled"
    print(f"mouse-control service: installed, {active_text}, {enabled_text}")
    return 0 if active.returncode == 0 else active.returncode or 1
