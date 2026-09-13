from pathlib import Path
import shutil
import subprocess


SERVICE_NAME = "mouse-control.service"


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

[Install]
WantedBy=default.target
"""


def is_service_active() -> bool:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", SERVICE_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
    _require_installed()
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
    _require_installed()
    subprocess.run(
        ["systemctl", "--user", "restart", SERVICE_NAME],
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
    active = subprocess.run(["systemctl", "--user", "is-active", SERVICE_NAME],
                            capture_output=True, text=True)
    enabled = subprocess.run(["systemctl", "--user", "is-enabled", SERVICE_NAME],
                             capture_output=True, text=True)
    active_text = active.stdout.strip() or ("failed" if active.returncode else "unknown")
    enabled_text = enabled.stdout.strip() or "disabled"
    print(f"mouse-control service: installed, {active_text}, {enabled_text}")
    return 0 if active.returncode == 0 else active.returncode or 1
