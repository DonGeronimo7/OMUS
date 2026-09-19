"""Shared, terminal-independent presentation rules for the setup TUI.

The curses adapter is intentionally thin: geometry, wrapping, scrolling, and
contextual key guidance live here so every setup screen follows one visual
system and the important behavior can be tested without a real terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import textwrap


MINIMUM_WIDTH = 48
MINIMUM_HEIGHT = 12


class LayoutMode(Enum):
    FULL = "full"
    COMPACT = "compact"
    TOO_SMALL = "too_small"


@dataclass(frozen=True, slots=True)
class FrameLayout:
    mode: LayoutMode
    height: int
    width: int
    sidebar_width: int
    content_y: int
    content_x: int
    content_height: int
    content_width: int
    status_y: int
    footer_y: int

    @property
    def usable(self) -> bool:
        return self.mode is not LayoutMode.TOO_SMALL


def frame_layout(height: int, width: int) -> FrameLayout:
    """Return a bounded layout for normal, narrow, and genuinely tiny terms."""

    height = max(0, int(height))
    width = max(0, int(width))
    if height < MINIMUM_HEIGHT or width < MINIMUM_WIDTH:
        return FrameLayout(
            LayoutMode.TOO_SMALL, height, width, 0, 3, 1,
            max(0, height - 6), max(0, width - 2),
            max(0, height - 2), max(0, height - 1),
        )

    # A rail is useful only when it leaves a readable card. Narrow and short
    # terminals use a breadcrumb header instead of hiding content or actions.
    full = width >= 76 and height >= 18
    sidebar = max(20, min(27, width // 4)) if full else 0
    content_x = sidebar + 2 if full else 2
    content_y = 4 if full else 3
    return FrameLayout(
        LayoutMode.FULL if full else LayoutMode.COMPACT,
        height,
        width,
        sidebar,
        content_y,
        content_x,
        max(1, height - content_y - 4),
        max(1, width - content_x - 2),
        height - 3,
        height - 1,
    )


def visible_window(total: int, cursor: int, capacity: int) -> tuple[int, int]:
    """Return a stable viewport that always keeps the selected row visible."""

    total = max(0, total)
    capacity = max(0, capacity)
    if total == 0 or capacity == 0:
        return 0, 0
    cursor = min(max(0, cursor), total - 1)
    if total <= capacity:
        return 0, total
    start = min(max(0, cursor - capacity // 2), total - capacity)
    return start, start + capacity


def wrap_text(text: str, width: int) -> tuple[str, ...]:
    """Wrap status/safety prose without losing a critical tail off-screen."""

    if width <= 0:
        return ()
    if not text:
        return ("",)
    return tuple(textwrap.wrap(
        text,
        width=width,
        replace_whitespace=False,
        drop_whitespace=True,
        break_long_words=True,
        break_on_hyphens=False,
    )) or ("",)


def footer_hint(
    section_name: str, *, backend_ready: bool, compact: bool, action: str | None = None
) -> str:
    """Show only commands relevant to the current screen and readiness state."""

    if not backend_ready and section_name == "Device":
        default_action = "open"
    elif section_name == "Device":
        default_action = "open"
    elif section_name == "DPI":
        default_action = "edit"
    elif section_name in {"Polling", "Service"}:
        default_action = "set"
    else:
        default_action = "open"
    action = action or default_action
    back = "  b back" if section_name != "Device" else ""
    base = f"j/k move  h/l page  g/G first/last  Enter {action}  ? help{back}  q quit"
    if not compact:
        return base.replace("j/k", "↑↓/j/k").replace("h/l", "←→/h/l")
    return base


def status_label(text: str) -> str:
    """Give color-independent semantics to common state vocabulary."""

    lowered = text.lower()
    if any(word in lowered for word in ("failed", "error", "could not", "refused")):
        return "ERROR"
    if any(word in lowered for word in ("warning", "unknown", "unverified", "pending")):
        return "CHECK"
    if any(word in lowered for word in ("ready", "complete", "saved", "proven")):
        return "READY"
    if any(word in lowered for word in ("preparing", "loading", "progress")):
        return "WORKING"
    return "STATUS"
