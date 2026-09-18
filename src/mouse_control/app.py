"""Installed Mouse Control application entry point."""

from __future__ import annotations

from . import cli


def main(argv: list[str] | None = None) -> int:
    return cli.main(argv)
