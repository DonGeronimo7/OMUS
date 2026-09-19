"""Installed OMUS application entry point."""

from __future__ import annotations

import sys

from . import cli


def main(argv: list[str] | None = None) -> int:
    supplied_argv = sys.argv[1:] if argv is None else argv
    from .foreground_session import launch, should_supervise
    if should_supervise(
        supplied_argv,
        interactive=sys.stdin.isatty() and sys.stdout.isatty(),
    ):
        return launch(supplied_argv)
    return cli.main(supplied_argv)
