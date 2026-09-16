"""Curses presentation/input adapter for the state-driven setup controller."""

from __future__ import annotations

import curses
from typing import Any, Callable

from evdev import InputDevice, ecodes

from .device_topology import TopologyError
from .guided_discovery import GuidedDiscoveryCancelled, GuidedStep, run_guided_discovery
from .hardware import HardwareError
from .keyboard_capture import capture_keyboard_chord, capture_keyboard_key
from .remapper import parse_action
from .setup_tui import ActionKind, SECTIONS, SetupController, SetupSection
from .wizard import ButtonCaptureError, get_button_name


class CursesSetupApp:
    def __init__(self, controller: SetupController) -> None:
        self.controller = controller
        self.stdscr = None

    @staticmethod
    def _put(window, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
        if width <= 0:
            return
        clipped = text[:width]
        try:
            window.addstr(y, x, clipped, attr)
        except curses.error:
            pass

    def _draw(self) -> None:
        assert self.stdscr is not None
        stdscr = self.stdscr
        height, width = stdscr.getmaxyx()
        stdscr.erase()
        if height < 18 or width < 72:
            self._put(stdscr, 1, 2, "Mouse Control — Setup", max(0, width - 4), curses.A_BOLD)
            self._put(stdscr, 3, 2, "Terminal is too small. Resize to at least 72×18.", max(0, width - 4))
            self._put(stdscr, max(0, height - 2), 2, "q Cancel   ? Help", max(0, width - 4), curses.A_REVERSE)
            stdscr.refresh()
            return

        header = " Mouse Control — Setup "
        self._put(stdscr, 0, 2, header, width - 4, curses.A_BOLD)
        tabs = "  ".join(
            (f"[{section.value}]" if section is self.controller.section else section.value)
            for section in SECTIONS
        )
        self._put(stdscr, 1, 2, tabs, width - 4, curses.A_BOLD)

        left = max(24, min(32, width // 3))
        split = left
        try:
            stdscr.vline(2, split, curses.ACS_VLINE, height - 5)
            stdscr.hline(height - 3, 0, curses.ACS_HLINE, width)
        except curses.error:
            pass
        self._put(stdscr, 3, 2, "Devices", left - 4, curses.A_BOLD)
        for index, device in enumerate(self.controller.devices):
            prefix = "▶ " if index == self.controller.selected_index else "  "
            attr = curses.A_REVERSE if (
                self.controller.section is SetupSection.DEVICE
                and index == self.controller.device_cursor
            ) else 0
            self._put(stdscr, 5 + index, 2, prefix + device.name, left - 4, attr)

        self._put(stdscr, 3, split + 2, self.controller.section.value, width - split - 4, curses.A_BOLD)
        y = 5
        for row in self.controller.detail_rows():
            if y >= height - 4:
                break
            attr = curses.A_DIM if row.dim else 0
            if row.cursor_index is not None and row.cursor_index == self.controller.row_cursor:
                attr |= curses.A_REVERSE
            self._put(stdscr, y, split + 2, row.text, width - split - 4, attr)
            y += 1

        status = self.controller.status or self.controller.notice
        self._put(stdscr, height - 2, 1, f" {status} ", width - 2)
        footer = " Enter Select/Edit   ↑↓ Navigate   ←→ Sections   b Back   q Quit   ? Help "
        self._put(stdscr, height - 1, 0, footer, width, curses.A_REVERSE)
        stdscr.refresh()

    def _modal(self, title: str, lines: list[str], *, prompt: str = "Enter Continue   b Back") -> None:
        assert self.stdscr is not None
        stdscr = self.stdscr
        height, width = stdscr.getmaxyx()
        desired_w = max([len(title) + 6, *(len(line) + 6 for line in lines), len(prompt) + 6])
        box_w = min(max(4, width - 4), max(20, desired_w))
        box_h = min(max(4, height - 2), max(5, len(lines) + 6))
        if box_w < 4 or box_h < 4:
            return
        y0 = max(0, (height - box_h) // 2)
        x0 = max(0, (width - box_w) // 2)
        win = curses.newwin(box_h, box_w, y0, x0)
        win.erase()
        try:
            win.box()
        except curses.error:
            pass
        self._put(win, 1, 2, title, box_w - 4, curses.A_BOLD)
        for index, line in enumerate(lines[: box_h - 5]):
            self._put(win, 3 + index, 2, line, box_w - 4)
        self._put(win, box_h - 2, 2, prompt, box_w - 4, curses.A_REVERSE)
        win.refresh()

    def _confirm(self, title: str, lines: list[str], *, yes="Enter Confirm", no="b Back") -> bool:
        while True:
            self._modal(title, lines, prompt=f"{yes}   {no}")
            key = self.stdscr.getch()
            if key in (10, 13, curses.KEY_ENTER):
                return True
            if key in (27, ord("b"), ord("B"), ord("q"), ord("Q")):
                return False

    def _read_number(self, title: str, initial: int) -> int | None:
        value = str(initial)
        while True:
            self._modal(title, [f"Value: {value or ' '}"], prompt="Digits Type   Enter Test/Accept   Esc Cancel")
            key = self.stdscr.getch()
            if key in (10, 13, curses.KEY_ENTER):
                return int(value) if value else None
            if key == 27:
                return None
            if key in (curses.KEY_BACKSPACE, 127, 8):
                value = value[:-1]
            elif ord("0") <= key <= ord("9") and len(value) < 6:
                value += chr(key)

    def _show_help(self) -> None:
        self._confirm(
            "Setup help",
            [
                "↑ / ↓  navigate the current panel",
                "← / →  switch setup sections",
                "Enter  select, edit, or continue",
                "b / Esc  go back",
                "q  cancel setup (confirmation required)",
                "No configuration is saved until Review → Save and Finish.",
            ],
            yes="Enter Close",
            no="Esc Close",
        )

    def _guided_prompt(self, step: GuidedStep) -> bool:
        return self._confirm(
            f"DPI learning — Step {step.index} of {step.total}",
            [step.instructions, "", "No unknown configuration commands will be sent."],
            yes="Enter Begin sample",
            no="b Cancel learning",
        )

    def _guided_progress(self, message: str) -> None:
        if message.startswith("Captured "):
            message = "✓ Sample captured"
        elif message.startswith("Skipped unreadable HID"):
            message = "Some hardware interfaces could not be observed"
        self.controller.status = message
        self._draw()

    def _run_guided(self) -> None:
        try:
            outcome = run_guided_discovery(
                self.controller.selected,
                prompt=self._guided_prompt,
                progress=self._guided_progress,
            )
        except GuidedDiscoveryCancelled:
            self.controller.status = "Guided discovery cancelled; no hardware authority changed."
            return
        except (TopologyError, PermissionError, OSError, HardwareError) as exc:
            self.controller.status = f"Guided discovery unavailable: {exc}"
            return
        self.controller.apply_guided_outcome(outcome)
        lines = []
        if outcome.dpi_action_identified:
            lines.append("✓ DPI button behavior identified")
        elif outcome.learning is not None:
            lines.append("? DPI behavior was not conclusive")
        if self.controller.choices.dpi_writable:
            lines.append("✓ DPI control safely proven for this exact mouse")
        else:
            lines.append("? DPI write command not yet proven")
        if self.controller.choices.polling_writable:
            lines.append("✓ Polling-rate control safely proven")
        else:
            lines.append("? Polling-rate control could not yet be safely proven")
            lines.append("Current polling rate will remain unchanged.")
        self._confirm("Discovery result", lines, yes="Enter Continue", no="Esc Continue")

    def _suspend_curses(self, function: Callable[[], Any]) -> Any:
        assert self.stdscr is not None
        curses.def_prog_mode()
        curses.endwin()
        try:
            return function()
        finally:
            curses.reset_prog_mode()
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            self.stdscr.refresh()

    def _read_text(self, title: str, *, hint: str = "") -> str | None:
        value = ""
        while True:
            lines = ([hint] if hint else []) + [f"Action: {value or ' '}" ]
            self._modal(
                title,
                lines,
                prompt="Type action   Enter Accept   Esc Cancel",
            )
            key = self.stdscr.getch()
            if key in (10, 13, curses.KEY_ENTER):
                value = value.strip()
                return value or None
            if key == 27:
                return None
            if key in (curses.KEY_BACKSPACE, 127, 8):
                value = value[:-1]
            elif 32 <= key <= 126 and len(value) < 120:
                value += chr(key)

    def _choose_button_action(self, button: str) -> str | None:
        options = [
            ("Passthrough", "passthrough"),
            ("Mouse: left button", "mouse:BTN_LEFT"),
            ("Mouse: right button", "mouse:BTN_RIGHT"),
            ("Mouse: middle button", "mouse:BTN_MIDDLE"),
            ("Keyboard key", "__key__"),
            ("Keyboard chord", "__chord__"),
            ("Manual Linux action", "__manual__"),
            ("Disable", "disable"),
            ("Cycle configured DPI stages", "dpi-cycle"),
        ]
        cursor = 0
        while True:
            lines = [f"Detected: {button}", ""] + [
                ("▶ " if index == cursor else "  ") + label
                for index, (label, _action) in enumerate(options)
            ]
            self._modal("Choose button action", lines, prompt="↑↓ Navigate   Enter Select   Esc Cancel")
            key = self.stdscr.getch()
            if key == curses.KEY_UP:
                cursor = (cursor - 1) % len(options)
            elif key == curses.KEY_DOWN:
                cursor = (cursor + 1) % len(options)
            elif key == 27:
                return None
            elif key in (10, 13, curses.KEY_ENTER):
                action = options[cursor][1]
                if action == "__key__":
                    name = self._suspend_curses(capture_keyboard_key)
                    return f"key:{name}" if name else None
                if action == "__chord__":
                    return self._suspend_curses(capture_keyboard_chord)
                if action == "__manual__":
                    raw = self._read_text(
                        "Manual Linux action",
                        hint="Examples: key:KEY_F13  chord:KEY_LEFTCTRL+KEY_C  mouse:BTN_SIDE",
                    )
                    if raw is None:
                        return None
                    try:
                        parse_action(raw)
                    except ValueError as exc:
                        self.controller.status = f"Invalid action: {exc}"
                        return None
                    return raw
                try:
                    parse_action(action)
                except ValueError:
                    self.controller.status = "That action is not valid."
                    return None
                return action

    def _button_editor(self) -> None:
        assert self.stdscr is not None
        device = None
        try:
            device = InputDevice(self.controller.selected.path)
            device.grab()
        except OSError as exc:
            if device is not None:
                device.close()
            raise ButtonCaptureError(f"Could not reserve the mouse for button capture: {exc}") from exc

        old_nodelay = False
        try:
            self.stdscr.nodelay(True)
            old_nodelay = True
            done = False
            while not done:
                self._modal(
                    "Button mapping",
                    [
                        "Press a mouse button to configure it.",
                        "Existing mappings stay unchanged until you select a new action.",
                    ],
                    prompt="Enter Finish   Esc Finish",
                )
                key = self.stdscr.getch()
                if key in (10, 13, curses.KEY_ENTER, 27):
                    break
                try:
                    events = device.read()
                except BlockingIOError:
                    events = ()
                except OSError as exc:
                    raise ButtonCaptureError(f"Mouse disconnected during button capture: {exc}") from exc
                for event in events:
                    if event.type != ecodes.EV_KEY or event.value != 1:
                        continue
                    button = get_button_name(event.code)
                    self.stdscr.nodelay(False)
                    action = self._choose_button_action(button)
                    self.stdscr.nodelay(True)
                    if action is not None:
                        self.controller.apply_button_mapping(button, action)
                    break
                curses.napms(20)
        finally:
            if old_nodelay:
                self.stdscr.nodelay(False)
            try:
                device.ungrab()
            except OSError:
                pass
            device.close()

    @staticmethod
    def _symbolic_key(key: int) -> str | None:
        mapping = {
            curses.KEY_UP: "UP", curses.KEY_DOWN: "DOWN",
            curses.KEY_LEFT: "LEFT", curses.KEY_RIGHT: "RIGHT",
            10: "ENTER", 13: "ENTER", curses.KEY_ENTER: "ENTER",
            27: "ESC", ord("b"): "BACK", ord("B"): "BACK",
            ord("q"): "QUIT", ord("Q"): "QUIT",
            ord("?"): "HELP",
        }
        return mapping.get(key)

    def run(self, stdscr) -> bool:
        self.stdscr = stdscr
        stdscr.keypad(True)
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
                    ["Existing configuration will remain unchanged.", "Temporary DPI tests will be restored."],
                ):
                    return False
            elif action.kind is ActionKind.EDIT_DPI:
                index = int(action.payload)
                requested = self._read_number(
                    f"Edit DPI stage {index + 1}", self.controller.choices.stages[index]
                )
                if requested is not None:
                    self.controller.set_dpi_value(index, requested)
            elif action.kind is ActionKind.CAPTURE_BUTTONS:
                try:
                    self._button_editor()
                except ButtonCaptureError as exc:
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


def run_curses(app: CursesSetupApp) -> bool:
    """Run one curses app under the stdlib terminal-restoration wrapper."""
    return bool(curses.wrapper(app.run))
