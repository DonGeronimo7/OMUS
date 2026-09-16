"""Curses presentation/input adapter for the state-driven setup controller."""

from __future__ import annotations

import curses
from typing import Any, Callable

from evdev import InputDevice, ecodes

from . import __version__
from .device_topology import TopologyError
from .discovery_lab import DiscoveryTool, discovery_tool_specs, run_discovery_tool
from .guided_discovery import GuidedDiscoveryCancelled, GuidedStep, run_guided_discovery
from .hardware import HardwareError
from .keyboard_capture import capture_keyboard_chord, capture_keyboard_key
from .remapper import parse_action
from .setup_tui import ActionKind, SECTIONS, SetupController, SetupSection
from .wizard import ButtonCaptureError, get_button_name


def _dpi_number(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "display_value"):
        value = value.display_value
    if isinstance(value, tuple):
        value = value[0]
    return int(value)


class DpiEditSession:
    """One reversible DPI-stage edit with separate live-test and accept phases."""

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


class CursesSetupApp:
    """Yazi-inspired curses renderer around the pure setup controller."""

    def __init__(self, controller: SetupController) -> None:
        self.controller = controller
        self.stdscr = None
        self._highlight = curses.A_REVERSE
        self._ok = curses.A_BOLD
        self._accent = curses.A_BOLD
        self._warn = 0
        self._muted = curses.A_DIM

    @staticmethod
    def _put(window, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
        if width <= 0:
            return
        clipped = text[:width]
        try:
            window.addstr(y, x, clipped, attr)
        except curses.error:
            pass

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
            self._warn = curses.color_pair(4)
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
            return self._warn
        return 0

    @staticmethod
    def _device_identity(device: Any) -> str:
        parts: list[str] = []
        if device.vendor is not None and device.product is not None:
            parts.append(f"{device.vendor:04x}:{device.product:04x}")
        if device.path:
            parts.append(str(device.path))
        return "   ".join(parts)

    def _draw(self) -> None:
        assert self.stdscr is not None
        stdscr = self.stdscr
        height, width = stdscr.getmaxyx()
        stdscr.erase()

        if height < 20 or width < 80:
            self._put(stdscr, 1, 2, f"Mouse Control — Setup v{__version__}", max(0, width - 4), curses.A_BOLD)
            self._put(stdscr, 3, 2, "Terminal is too small. Resize to at least 80×20.", max(0, width - 4))
            self._put(stdscr, max(0, height - 2), 2, "q Cancel   ? Help", max(0, width - 4), self._highlight)
            stdscr.refresh()
            return

        sidebar = max(22, min(28, width // 4))
        self._put(stdscr, 0, 2, f" Mouse Control — Setup v{__version__} ", width - 4, curses.A_BOLD)
        try:
            stdscr.vline(1, sidebar, curses.ACS_VLINE, height - 4)
            stdscr.hline(height - 3, 0, curses.ACS_HLINE, width)
        except curses.error:
            pass

        for index, section in enumerate(SECTIONS):
            label = f" {index + 1}. {section.value} "
            self._put(stdscr, 2 + index, 1, label, sidebar - 2, self._highlight if section is self.controller.section else 0)

        x = sidebar + 2
        content_width = width - x - 2
        self._put(stdscr, 2, x, self.controller.section.value, content_width, self._accent)
        y = 4

        if self.controller.section is SetupSection.DEVICE:
            self._put(stdscr, y, x, "Select a device", content_width, curses.A_BOLD)
            y += 1
            self._put(stdscr, y, x, "Choose the mouse you want to configure.", content_width, self._muted)
            y += 2
            for index, device in enumerate(self.controller.devices):
                if y >= height - 5:
                    break
                selected = index == self.controller.device_cursor
                bound = index == self.controller.selected_index
                prefix = "●" if bound else "○"
                name = f" {prefix}  {device.name}"
                self._put(stdscr, y, x, name, content_width, self._line_attr(name, selected=selected))
                y += 1
                identity = self._device_identity(device)
                if identity:
                    self._put(stdscr, y, x, f"    {identity}", content_width, self._muted)
                y += 2
        else:
            for row in self.controller.detail_rows():
                if y >= height - 4:
                    break
                selected = row.cursor_index is not None and row.cursor_index == self.controller.row_cursor
                self._put(stdscr, y, x, row.text, content_width, self._line_attr(row.text, selected=selected, dim=row.dim))
                y += 1

        status = self.controller.status or self.controller.notice
        self._put(stdscr, height - 2, 1, f" {status} ", width - 2, self._accent)
        footer = " Enter Select/Edit   ↑↓ Navigate   ←→ Sections   b Back   q Quit   ? Help "
        self._put(stdscr, height - 1, 0, footer, width, self._highlight)
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
        try:
            win = curses.newwin(box_h, box_w, y0, x0)
        except curses.error:
            return
        win.erase()
        try:
            win.box()
        except curses.error:
            pass
        self._put(win, 1, 2, title, box_w - 4, curses.A_BOLD)
        for index, line in enumerate(lines[: box_h - 5]):
            self._put(win, 3 + index, 2, line, box_w - 4)
        self._put(win, box_h - 2, 2, prompt, box_w - 4, self._highlight)
        win.refresh()

    def _confirm(self, title: str, lines: list[str], *, yes="Enter Confirm", no="b Back") -> bool:
        while True:
            self._modal(title, lines, prompt=f"{yes}   {no}")
            key = self.stdscr.getch()
            if key == curses.KEY_RESIZE:
                continue
            if key in (10, 13, curses.KEY_ENTER):
                return True
            if key in (27, ord("b"), ord("B"), ord("q"), ord("Q")):
                return False

    def _show_help(self) -> None:
        self._confirm(
            "Setup help",
            [
                "↑ / ↓  navigate the current panel",
                "← / →  switch setup sections",
                "Enter  select, edit, or continue",
                "Hardware / Discovery contains the complete evidence ladder.",
                "LAB entries collect evidence; PROVE entries may write only through guarded engines.",
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

    def _run_discovery_tool(self, tool: DiscoveryTool) -> None:
        spec = next(spec for spec in discovery_tool_specs() if spec.tool is tool)
        if spec.writes_hardware:
            verb = "promotion" if spec.promotion else "evidence capture"
            confirmed = self._confirm(
                spec.label,
                [
                    spec.description,
                    "",
                    f"This {verb} can change live hardware state.",
                    "The underlying engine still requires exact identity, verification and rollback.",
                    "No result becomes writable unless that engine persists PROVEN authority.",
                ],
                yes="Enter Run guarded lab",
                no="b Cancel",
            )
            if not confirmed:
                self.controller.status = "Discovery lab cancelled; no authority changed."
                return
        else:
            confirmed = self._confirm(
                spec.label,
                [spec.description, "", "This measurement is read-only."],
                yes="Enter Run lab",
                no="b Cancel",
            )
            if not confirmed:
                self.controller.status = "Discovery lab cancelled."
                return

        def execute() -> int:
            print("\nReturning to Mouse Control setup when this lab finishes.\n")
            return run_discovery_tool(
                tool,
                devices=self.controller.devices,
                selected=self.controller.selected,
            )

        try:
            status = int(self._suspend_curses(execute))
        except (OSError, PermissionError, ValueError, HardwareError) as exc:
            self.controller.status = f"Discovery lab failed: {exc}"
            return
        if status == 0:
            self.controller.refresh_discovery_backend(status=f"✓ {spec.label} completed; capabilities refreshed.")
        elif status == 130:
            self.controller.status = f"{spec.label} cancelled."
        else:
            self.controller.refresh_discovery_backend(status=f"{spec.label} did not produce new PROVEN authority (exit {status}).")

    def _read_text(self, title: str, *, hint: str = "") -> str | None:
        value = ""
        while True:
            lines = ([hint] if hint else []) + [f"Action: {value or ' '}" ]
            self._modal(title, lines, prompt="Type action   Enter Accept   Esc Cancel")
            key = self.stdscr.getch()
            if key == curses.KEY_RESIZE:
                continue
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
            if key == curses.KEY_RESIZE:
                continue
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
                    raw = self._read_text("Manual Linux action", hint="Examples: key:KEY_F13  chord:KEY_LEFTCTRL+KEY_C  mouse:BTN_SIDE")
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

        nodelay_enabled = False
        try:
            self.stdscr.nodelay(True)
            nodelay_enabled = True
            while True:
                self._modal(
                    "Button mapping",
                    [
                        "Press a mouse button to configure it.",
                        "Existing mappings stay unchanged until you select a new action.",
                    ],
                    prompt="Enter Finish   Esc Finish",
                )
                key = self.stdscr.getch()
                if key == curses.KEY_RESIZE:
                    continue
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
            if nodelay_enabled:
                self.stdscr.nodelay(False)
            try:
                device.ungrab()
            except OSError:
                pass
            device.close()

    def _draw_dpi_editor(self, session: DpiEditSession, value: str, action_cursor: int) -> None:
        assert self.stdscr is not None
        stdscr = self.stdscr
        height, width = stdscr.getmaxyx()
        if height < 16 or width < 56:
            stdscr.erase()
            self._put(stdscr, 1, 2, "DPI editor paused", max(0, width - 4), curses.A_BOLD)
            self._put(stdscr, 3, 2, "Resize the terminal to at least 56×16 to continue.", max(0, width - 4))
            stdscr.refresh()
            return

        box_w = min(width - 6, 72)
        box_h = min(height - 4, 16)
        y0 = max(1, (height - box_h) // 2)
        x0 = max(2, (width - box_w) // 2)
        try:
            win = curses.newwin(box_h, box_w, y0, x0)
        except curses.error:
            return
        win.erase()
        try:
            win.box()
        except curses.error:
            pass

        self._put(win, 1, 2, f"DPI Configuration — Stage {session.index + 1}", box_w - 4, self._accent)
        self._put(win, 3, 2, f"Accepted stage value: {self.controller.choices.stages[session.index]} DPI", box_w - 4)
        self._put(win, 4, 2, f"Candidate DPI:       {value or ' '}", box_w - 4, curses.A_BOLD)
        if session.tested_value is not None:
            self._put(win, 5, 2, f"Live test:           {session.tested_value} DPI", box_w - 4, self._ok)
        else:
            self._put(win, 5, 2, "Live test:           not tested", box_w - 4, self._muted)

        actions = ("Test live", "Accept value", "Set to current", "Cancel")
        for index, label in enumerate(actions):
            prefix = "▶ " if index == action_cursor else "  "
            self._put(win, 7 + index, 2, prefix + label, box_w - 4, self._highlight if index == action_cursor else 0)
        self._put(win, box_h - 2, 2, "Type DPI   ↑↓ Action   Enter Run   Esc Cancel", box_w - 4, self._muted)
        win.refresh()

    def _dpi_editor(self, index: int) -> None:
        session = DpiEditSession(self.controller, index)
        value = str(session.candidate)
        editing_started = False
        action_cursor = 0

        while True:
            self._draw_dpi_editor(session, value, action_cursor)
            key = self.stdscr.getch()
            if key == curses.KEY_RESIZE:
                continue
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

    @staticmethod
    def _symbolic_key(key: int) -> str | None:
        mapping = {
            curses.KEY_UP: "UP",
            curses.KEY_DOWN: "DOWN",
            curses.KEY_LEFT: "LEFT",
            curses.KEY_RIGHT: "RIGHT",
            10: "ENTER",
            13: "ENTER",
            curses.KEY_ENTER: "ENTER",
            27: "ESC",
            ord("b"): "BACK",
            ord("B"): "BACK",
            ord("q"): "QUIT",
            ord("Q"): "QUIT",
            ord("?"): "HELP",
        }
        return mapping.get(key)

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
                except ButtonCaptureError as exc:
                    self.controller.status = str(exc)
            elif action.kind is ActionKind.GUIDED_DISCOVERY:
                self._run_guided()
            elif action.kind is ActionKind.RUN_DISCOVERY_TOOL:
                self._run_discovery_tool(DiscoveryTool(action.payload))
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