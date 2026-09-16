"""Release presentation layer for the Mouse Control setup TUI.

This module keeps the tested :class:`SetupController` as the source of truth and
adds the polished v0.9.1 curses presentation.  In particular, DPI editing is a
three-phase operation: choose a candidate, test it live, then explicitly accept
it.  Merely testing a DPI value never changes the staged configuration.
"""

from __future__ import annotations

import curses
from typing import Any, Callable

from .hardware import HardwareError, get_backend
from .setup_flow import SetupChoices
from .setup_tui import (
    ActionKind,
    SECTIONS,
    SetupController,
    SetupSection,
    SetupTuiResult,
)
from .setup_tui_curses import CursesSetupApp, run_curses


def _dpi_number(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "display_value"):
        value = value.display_value
    if isinstance(value, tuple):
        value = value[0]
    return int(value)


class DpiEditSession:
    """One reversible DPI-stage editing session.

    Live testing is intentionally separate from accepting the staged value.
    Cancel restores the hardware value that was active when the editor opened.
    """

    def __init__(self, controller: SetupController, index: int) -> None:
        self.controller = controller
        self.index = index
        self.candidate = int(controller.choices.stages[index])
        self.tested_value: int | None = None
        self.original_hardware = self._read_current()
        if self.original_hardware is None:
            self.original_hardware = controller.choices.original_dpi

    def _read_current(self) -> int | None:
        try:
            return _dpi_number(self.controller.backend.get_dpi(self.controller.selected))
        except (HardwareError, OSError, TypeError, ValueError, AttributeError):
            return None

    def _validate(self, requested: int) -> bool:
        choices = self.controller.choices
        if not choices.dpi_writable:
            self.controller.status = "Live DPI tuning is unavailable for this mouse."
            return False
        values = choices.dpi_values
        if not values:
            self.controller.status = "The mouse did not report safe DPI values for live tuning."
            return False
        if requested not in values:
            self.controller.status = (
                f"{requested} DPI is unsupported; choose a hardware-reported value "
                f"between {values[0]} and {values[-1]}."
            )
            return False
        return True

    def test_live(self, requested: int) -> bool:
        """Write and verify a candidate without changing the staged config."""
        if not self._validate(requested):
            return False
        try:
            result = self.controller.backend.set_dpi(self.controller.selected, requested)
            confirmed = _dpi_number(result)
            if confirmed is None:
                confirmed = self._read_current()
            if confirmed != requested:
                self.controller.status = (
                    f"Mouse reported {confirmed} DPI; {requested} DPI was not accepted."
                )
                return False
        except (HardwareError, OSError, TypeError, ValueError) as exc:
            self.controller.status = f"Could not test DPI: {exc}"
            return False
        self.candidate = requested
        self.tested_value = requested
        self.controller.status = (
            f"Testing {requested} DPI live. Move the mouse; accept it only if it feels right."
        )
        return True

    def set_to_current(self) -> int | None:
        """Use the mouse's current verified DPI as the candidate."""
        current = self._read_current()
        if current is None:
            self.controller.status = "Could not read the mouse's current DPI."
            return None
        if not self._validate(current):
            return None
        self.candidate = current
        self.tested_value = current
        self.controller.status = f"Candidate set to the mouse's current {current} DPI."
        return current

    def accept(self, requested: int | None = None) -> bool:
        """Explicitly commit a tested value to setup choices."""
        target = self.candidate if requested is None else int(requested)
        if self.tested_value != target and not self.test_live(target):
            return False
        self.candidate = target
        self.controller.choices.stages[self.index] = target
        if self.index == 0:
            self.controller.choices.active_dpi = target
        self.controller.choices.dpi_changed = True
        self.controller.status = f"Stage {self.index + 1} accepted at {target} DPI."
        return True

    def cancel(self) -> None:
        """Discard staged changes and restore pre-editor hardware DPI."""
        if self.original_hardware is None:
            self.controller.status = "DPI edit cancelled; staged configuration was unchanged."
            return
        try:
            self.controller.backend.set_dpi(self.controller.selected, self.original_hardware)
            self.controller.status = (
                "DPI edit cancelled; staged configuration was unchanged and the previous "
                "hardware DPI was restored."
            )
        except (HardwareError, OSError, TypeError, ValueError) as exc:
            self.controller.status = (
                "DPI edit cancelled; staged configuration was unchanged, but the previous "
                f"hardware DPI could not be restored: {exc}"
            )


class PolishedCursesSetupApp(CursesSetupApp):
    """Yazi-inspired v0.9.1 renderer around the existing setup controller."""

    def __init__(self, controller: SetupController) -> None:
        super().__init__(controller)
        self._highlight = curses.A_REVERSE
        self._ok = curses.A_BOLD
        self._accent = curses.A_BOLD
        self._muted = curses.A_DIM

    def _init_colors(self) -> None:
        if not curses.has_colors():
            return
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
            curses.init_pair(4, curses.COLOR_YELLOW, -1)
            self._highlight = curses.color_pair(1) | curses.A_BOLD
            self._ok = curses.color_pair(2) | curses.A_BOLD
            self._accent = curses.color_pair(3) | curses.A_BOLD
            self._muted = curses.A_DIM
        except curses.error:
            pass

    def _line_attr(self, text: str, *, selected: bool = False, dim: bool = False) -> int:
        if selected:
            return self._highlight
        if dim:
            return self._muted
        if text.startswith("✓"):
            return self._ok
        if text.startswith("?"):
            return curses.color_pair(4) if curses.has_colors() else 0
        return 0

    def _draw(self) -> None:
        assert self.stdscr is not None
        stdscr = self.stdscr
        height, width = stdscr.getmaxyx()
        stdscr.erase()

        if height < 20 or width < 80:
            self._put(stdscr, 1, 2, "Mouse Control — Setup", max(0, width - 4), curses.A_BOLD)
            self._put(
                stdscr,
                3,
                2,
                "Terminal is too small. Resize to at least 80×20.",
                max(0, width - 4),
            )
            self._put(
                stdscr,
                max(0, height - 2),
                2,
                "q Cancel   ? Help",
                max(0, width - 4),
                self._highlight,
            )
            stdscr.refresh()
            return

        sidebar = max(22, min(28, width // 4))
        self._put(stdscr, 0, 2, " Mouse Control — Setup v0.9.1 ", width - 4, curses.A_BOLD)
        try:
            stdscr.vline(1, sidebar, curses.ACS_VLINE, height - 4)
            stdscr.hline(height - 3, 0, curses.ACS_HLINE, width)
        except curses.error:
            pass

        for index, section in enumerate(SECTIONS):
            label = f" {index + 1}. {section.value} "
            self._put(
                stdscr,
                2 + index,
                1,
                label,
                sidebar - 2,
                self._highlight if section is self.controller.section else 0,
            )

        x = sidebar + 2
        content_width = width - x - 2
        self._put(stdscr, 2, x, self.controller.section.value, content_width, self._accent)
        y = 4

        if self.controller.section is SetupSection.DEVICE:
            self._put(stdscr, y, x, "Select a device", content_width, curses.A_BOLD)
            y += 1
            self._put(
                stdscr,
                y,
                x,
                "Choose the mouse you want to configure.",
                content_width,
                self._muted,
            )
            y += 2
            for index, device in enumerate(self.controller.devices):
                selected = index == self.controller.device_cursor
                bound = index == self.controller.selected_index
                prefix = "●" if bound else "○"
                name = f" {prefix}  {device.name}"
                self._put(
                    stdscr,
                    y,
                    x,
                    name,
                    content_width,
                    self._line_attr(name, selected=selected),
                )
                y += 1
                identity = f"    {device.vendor:04x}:{device.product:04x}   {device.path}"
                self._put(stdscr, y, x, identity, content_width, self._muted)
                y += 2
        else:
            for row in self.controller.detail_rows():
                if y >= height - 4:
                    break
                selected = (
                    row.cursor_index is not None
                    and row.cursor_index == self.controller.row_cursor
                )
                self._put(
                    stdscr,
                    y,
                    x,
                    row.text,
                    content_width,
                    self._line_attr(row.text, selected=selected, dim=row.dim),
                )
                y += 1

        status = self.controller.status or self.controller.notice
        self._put(stdscr, height - 2, 1, f" {status} ", width - 2, self._accent)
        footer = " Enter Select/Edit   ↑↓ Navigate   ←→ Sections   b Back   q Quit   ? Help "
        self._put(stdscr, height - 1, 0, footer, width, self._highlight)
        stdscr.refresh()

    def _draw_dpi_editor(
        self,
        session: DpiEditSession,
        value: str,
        action_cursor: int,
    ) -> None:
        assert self.stdscr is not None
        stdscr = self.stdscr
        height, width = stdscr.getmaxyx()
        box_w = min(width - 6, 72)
        box_h = min(height - 4, 16)
        y0 = max(1, (height - box_h) // 2)
        x0 = max(2, (width - box_w) // 2)
        win = curses.newwin(box_h, box_w, y0, x0)
        win.erase()
        try:
            win.box()
        except curses.error:
            pass

        self._put(win, 1, 2, f"DPI Configuration — Stage {session.index + 1}", box_w - 4, self._accent)
        self._put(
            win,
            3,
            2,
            f"Accepted stage value: {self.controller.choices.stages[session.index]} DPI",
            box_w - 4,
        )
        self._put(win, 4, 2, f"Candidate DPI:       {value or ' '}", box_w - 4, curses.A_BOLD)
        if session.tested_value is not None:
            self._put(
                win,
                5,
                2,
                f"Live test:           {session.tested_value} DPI",
                box_w - 4,
                self._ok,
            )
        else:
            self._put(win, 5, 2, "Live test:           not tested", box_w - 4, self._muted)

        actions = ("Test live", "Accept value", "Set to current", "Cancel")
        for index, label in enumerate(actions):
            prefix = "▶ " if index == action_cursor else "  "
            self._put(
                win,
                7 + index,
                2,
                prefix + label,
                box_w - 4,
                self._highlight if index == action_cursor else 0,
            )
        self._put(
            win,
            box_h - 2,
            2,
            "Type DPI   ↑↓ Action   Enter Run   Esc Cancel",
            box_w - 4,
            self._muted,
        )
        win.refresh()

    def _dpi_editor(self, index: int) -> None:
        session = DpiEditSession(self.controller, index)
        value = str(session.candidate)
        editing_started = False
        action_cursor = 0

        while True:
            self._draw_dpi_editor(session, value, action_cursor)
            key = self.stdscr.getch()

            if key in (27, ord("b"), ord("B"), ord("q"), ord("Q")):
                session.cancel()
                return
            if key == curses.KEY_UP:
                action_cursor = (action_cursor - 1) % 4
                continue
            if key == curses.KEY_DOWN:
                action_cursor = (action_cursor + 1) % 4
                continue
            if key in (curses.KEY_BACKSPACE, 127, 8):
                if not editing_started:
                    value = ""
                    editing_started = True
                else:
                    value = value[:-1]
                session.tested_value = None
                continue
            if ord("0") <= key <= ord("9"):
                if not editing_started:
                    value = ""
                    editing_started = True
                if len(value) < 6:
                    value += chr(key)
                    session.tested_value = None
                continue
            if key not in (10, 13, curses.KEY_ENTER):
                continue

            requested = int(value) if value else None
            if action_cursor == 0:
                if requested is None:
                    self.controller.status = "Enter a DPI value to test."
                elif session.test_live(requested):
                    value = str(session.candidate)
                    editing_started = False
            elif action_cursor == 1:
                if requested is None:
                    self.controller.status = "Enter a DPI value to accept."
                elif session.accept(requested):
                    return
            elif action_cursor == 2:
                current = session.set_to_current()
                if current is not None:
                    value = str(current)
                    editing_started = False
            else:
                session.cancel()
                return

    def run(self, stdscr) -> bool:
        self.stdscr = stdscr
        stdscr.keypad(True)
        self._init_colors()
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        while True:
            self._draw()
            key = stdscr.getch()
            if key == curses.KEY_RESIZE:
                continue
            symbolic = self._symbolic_key(key)
            if symbolic is None:
                continue
            action = self.controller.handle_key(symbolic)

            if action.kind is ActionKind.HELP:
                self._show_help()
            elif action.kind is ActionKind.CANCEL:
                if self._confirm(
                    "Cancel setup?",
                    [
                        "Existing configuration will remain unchanged.",
                        "Temporary DPI tests will be restored.",
                    ],
                ):
                    return False
            elif action.kind is ActionKind.EDIT_DPI:
                self._dpi_editor(int(action.payload))
            elif action.kind is ActionKind.CAPTURE_BUTTONS:
                try:
                    self._button_editor()
                except Exception as exc:
                    self.controller.status = str(exc)
            elif action.kind is ActionKind.GUIDED_DISCOVERY:
                self._run_guided()
            elif action.kind is ActionKind.SAVE:
                if self._confirm(
                    "Save configuration?",
                    ["Apply the reviewed settings and finish setup."],
                    yes="Enter Save and Finish",
                    no="b Back",
                ):
                    return True


def run_setup_tui(
    devices: list[Any] | tuple[Any, ...],
    existing_config: dict[str, object],
    *,
    choices_factory: Callable[[dict[str, object]], SetupChoices],
    backend_factory: Callable[[Any], Any] = get_backend,
) -> SetupTuiResult:
    """Run the polished full-screen setup UI with guaranteed rollback on errors."""
    controller = SetupController(
        devices,
        existing_config,
        choices_factory=choices_factory,
        backend_factory=backend_factory,
    )
    try:
        finished = run_curses(PolishedCursesSetupApp(controller))
    except BaseException:
        controller.restore_temporary_state()
        raise
    return SetupTuiResult(
        finished=bool(finished),
        selected=controller.selected,
        backend=controller.backend,
        choices=controller.choices,
    )
