# SPDX-License-Identifier: AGPL-3.0-or-later
"""Login bootstrap for packaged desktops; systemd owns every runtime process."""
from __future__ import annotations

import subprocess

from . import service
from .config import get_config_path


def main() -> int:
    # First-run users have no desired device yet. Never launch a setup terminal.
    if not get_config_path().is_file():
        return 0
    path = service.service_path()
    existed = path.exists()
    enabled = subprocess.run(
        [service.SYSTEMCTL, "--user", "is-enabled", "--quiet", service.SERVICE_NAME],
        check=False,
    ).returncode == 0 if existed else True
    if not existed:
        service.install_service(start=False)
    elif not path.is_symlink():
        # Upgrade only an exact former OMUS-generated unit. User customizations
        # and explicit disabled state remain authoritative.
        current = service.build_service_text('/usr/bin/omus')
        former = current.replace('After=graphical-session-pre.target\nPartOf=graphical-session.target\nStartLimitIntervalSec=0\n', '').replace(
            'RestartSec=3\nTimeoutStopSec=15', 'RestartSec=2').replace(
            'WantedBy=graphical-session.target', 'WantedBy=default.target')
        if path.read_text() == former and enabled:
            service.install_service(start=False)
    if enabled:
        service.start_service()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
