"""Import-order regression tests for the standalone discovery command."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_discovery_cli_imports_in_fresh_python_process():
    """The console script must not rely on hardware modules being pre-imported."""

    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    source_path = str(root / "src")
    env["PYTHONPATH"] = (
        source_path if not existing else os.pathsep.join((source_path, existing))
    )
    subprocess.run(
        [sys.executable, "-c", "import mouse_control.discovery_cli"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
