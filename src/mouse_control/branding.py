"""Small, dependency-free terminal presentation helpers."""

from __future__ import annotations

import os
import shutil
import sys
from typing import TextIO


# This mouse is the terminal rendition of the centered mouse mark in the
# approved social-preview artwork.  Keep it here so interactive flows share
# one canonical mark rather than each carrying a slightly different copy.
_MOUSE_LOGO = r"""
          .--------.
        .'  .--.    '.
       /   |    |     \
      |    |    |      |
      |       M         |
      |        |        |
       \       |       /
        '.     o     .'
          '---------'
""".strip("\n")

_COMPACT_LOGO = r"""
  .----.
 / .--. \
|   M   |
 \  |  /
  '--o-'
""".strip("\n")

_CODES = {
    "cyan": "36",
    "blue": "34",
    "purple": "35",
    "muted": "90",
    "success": "32",
    "warning": "33",
    "error": "31",
}


def color_enabled(stream: TextIO | None = None) -> bool:
    """Return whether ANSI styling is appropriate for this output stream."""
    stream = stream or sys.stdout
    return bool(
        getattr(stream, "isatty", lambda: False)()
        and not os.environ.get("NO_COLOR")
        and os.environ.get("TERM", "").lower() not in {"", "dumb"}
    )


def style(text: str, name: str, *, stream: TextIO | None = None) -> str:
    """Style text only when the active terminal can safely display it."""
    if color_enabled(stream) and name in _CODES:
        return f"\033[{_CODES[name]}m{text}\033[0m"
    return text


def render_logo(*, columns: int | None = None, stream: TextIO | None = None) -> str:
    """Render the canonical mouse mark, selecting a compact safe variant."""
    width = columns if columns is not None else shutil.get_terminal_size(fallback=(80, 24)).columns
    logo = _MOUSE_LOGO if width >= 36 else _COMPACT_LOGO if width >= 12 else ""
    return style(logo, "cyan", stream=stream) if logo else ""


def render_banner(*, columns: int | None = None, stream: TextIO | None = None) -> str:
    """Return the home/wizard banner without assuming a large terminal."""
    logo = render_logo(columns=columns, stream=stream)
    title = style("MOUSE CONTROL", "blue", stream=stream)
    subtitle = style("Linux Gaming Mouse Control", "muted", stream=stream)
    return "\n".join(part for part in (logo, title, subtitle) if part)


def print_banner(*, columns: int | None = None, stream: TextIO | None = None) -> None:
    """Print the canonical banner once at the start of an interactive flow."""
    print(render_banner(columns=columns, stream=stream), file=stream or sys.stdout)
