"""Installed Mouse Control application entry point.

The full-screen TUI is the primary interactive product surface. Non-interactive
callers retain the legacy prompt path so packaging smoke tests, redirected
automation, and compatibility callers never require a terminal.
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
    supplied = sys.argv[1:] if argv is None else list(argv)

    # An ordinary interactive launch is Mouse Control itself, not a legacy text
    # menu in front of Mouse Control. Enter the complete TUI immediately.
    if not supplied and sys.stdin.isatty() and sys.stdout.isatty():
        return run_tui_setup_wizard()

    # Explicit setup still routes through the TUI. Keep the override scoped to
    # this invocation so library callers/tests retain the compatibility API.
    original = cli.run_setup_wizard
    cli.run_setup_wizard = run_setup_wizard
    try:
        return cli.main(argv)
    finally:
        cli.run_setup_wizard = original
