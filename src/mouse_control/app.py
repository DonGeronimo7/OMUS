"""Installed Mouse Control application entry point.

Interactive no-argument use opens the full-screen setup application directly.
Explicit subcommands and non-interactive callers retain the legacy CLI behavior
for packaging smoke tests, redirected automation, and compatibility callers.
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
    supplied_argv = sys.argv[1:] if argv is None else argv
    if not supplied_argv and sys.stdin.isatty() and sys.stdout.isatty():
        return run_tui_setup_wizard()

    # cli.main and run_home_screen resolve this global at call time. Keep the
    # override scoped to one invocation so importing this compatibility entry
    # point never mutates library behavior for other callers/tests.
    original = cli.run_setup_wizard
    cli.run_setup_wizard = run_setup_wizard
    try:
        return cli.main(supplied_argv)
    finally:
        cli.run_setup_wizard = original
