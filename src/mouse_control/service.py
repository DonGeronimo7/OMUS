from pathlib import Path
import shutil
import subprocess


SERVICE_NAME = "mouse-control.service"


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

[Install]
WantedBy=default.target
"""


def is_service_active() -> bool:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", SERVICE_NAME],
    )
    return result.returncode == 0


def install_service() -> None:
    exe = shutil.which("mouse-control")
    if not exe:
        raise RuntimeError("mouse-control executable not found")

    path = service_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_service_text(exe), encoding="utf-8")

    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        check=True,
    )

    subprocess.run(
        ["systemctl", "--user", "enable", "--now", SERVICE_NAME],
        check=True,
    )


def start_service() -> None:
    subprocess.run(
        ["systemctl", "--user", "start", SERVICE_NAME],
        check=True,
    )


def stop_service() -> None:
    subprocess.run(
        ["systemctl", "--user", "stop", SERVICE_NAME],
        check=True,
    )


def restart_service() -> None:
    subprocess.run(
        ["systemctl", "--user", "restart", SERVICE_NAME],
        check=True,
    )


def status_service() -> int:
    result = subprocess.run(
        ["systemctl", "--user", "status", SERVICE_NAME],
    )
    return result.returncode
