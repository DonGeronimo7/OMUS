"""Installed Mouse Control application entry point.

Interactive setup is routed to the full-screen TUI.  Non-interactive callers
retain the legacy prompt path so packaging smoke tests, redirected automation,
and compatibility callers never require a terminal.
"""

from __future__ import annotations

import sys

from . import cli
from .setup_entry import run_tui_setup_wizard


_LEGACY_SETUP = cli.run_setup_wizard


def run_setup_wizard() -> int:
    if sys.stdin.isatty() and sys.stdout.isatty():
        return run_tui_setup_wizard()
    return _LEGACY_SETUP()


def main(argv: list[str] | None = None) -> int:
    # cli.main and run_home_screen resolve this global at call time. Keep the
    # override scoped to one invocation so importing this compatibility entry
    # point never mutates library behavior for other callers/tests.
    original = cli.run_setup_wizard
    cli.run_setup_wizard = run_setup_wizard
    try:
        return cli.main(argv)
    finally:
        cli.run_setup_wizard = original
