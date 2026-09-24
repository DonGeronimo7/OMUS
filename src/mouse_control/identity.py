# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical OMUS identity and lossless legacy-state migration."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

PRODUCT_NAME = "OMUS"
PRODUCT_EXPANSION = "One Mouse Universal System"
TAGLINE = "Every mouse. One system."
COMMAND = "omus"
LEGACY_COMMAND = "mouse-control"


def _xdg_root(kind: str) -> Path:
    variable = {"config": "XDG_CONFIG_HOME", "data": "XDG_DATA_HOME", "cache": "XDG_CACHE_HOME"}[kind]
    default = {"config": Path.home() / ".config", "data": Path.home() / ".local" / "share", "cache": Path.home() / ".cache"}[kind]
    configured = os.environ.get(variable)
    return Path(configured).expanduser() if configured else default


def legacy_directory(kind: str) -> Path:
    return _xdg_root(kind) / "mouse-control"


def canonical_directory(kind: str, *, migrate: bool = True) -> Path:
    destination = _xdg_root(kind) / "omus"
    if migrate:
        migrate_legacy_directory(legacy_directory(kind), destination)
    return destination


def migrate_legacy_directory(source: Path, destination: Path) -> bool:
    """Atomically copy legacy state once while retaining the original backup."""
    if destination.exists() or not source.is_dir():
        return False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".omus-migrate-", dir=destination.parent))
    except OSError:
        # Read-only or unavailable homes must not prevent remapping.  The next
        # writable startup will retry because no canonical destination exists.
        return False
    try:
        shutil.rmtree(temporary)
        shutil.copytree(source, temporary, symlinks=True)
        try:
            os.replace(temporary, destination)
        except OSError:
            if destination.exists():
                return False
            raise
        return True
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
