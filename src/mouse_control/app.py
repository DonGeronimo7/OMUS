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
    if supplied_argv and supplied_argv[0] == "run":
        from .runtime_lock import runtime_lock
        try:
            with runtime_lock():
                return cli.main(supplied_argv)
        except (OSError, RuntimeError) as exc:
            print(f"OMUS runtime: {exc}", file=sys.stderr)
            return 1
    return cli.main(supplied_argv)
