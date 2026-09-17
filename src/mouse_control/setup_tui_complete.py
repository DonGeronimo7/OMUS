"""Final 0.9.2 setup presentation refinements.

This layer keeps the complete discovery catalog navigable in small supported
terminals and resolves the selected mouse by stable identity immediately before
exclusive button capture.  It deliberately refuses ambiguous replacements.
"""

from __future__ import annotations

import curses
import errno
from typing import Any, Callable

from evdev import InputDevice, ecodes

from .discovery import get_mouse_devices
from .hardware import get_backend
from .setup_flow import SetupChoices
from .setup_tui import SetupController, SetupSection, SetupTuiResult
from .setup_tui_curses import run_curses
from .setup_tui_integrated import IntegratedCursesSetupApp
from .wizard import ButtonCaptureError, get_button_name


class CompleteCursesSetupApp(IntegratedCursesSetupApp):
    """Complete user-facing setup: one TUI, full discovery ladder, stable capture."""

    @staticmethod
    def _input_error_message(exc: OSError) -> str:
        if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK, errno.EBUSY}:
            return (
                "The input device is temporarily busy. Mouse Control kept the current "
                "mappings unchanged; release the competing grab and try button capture again."
            )
        return f"Input capture failed: {exc}"

    def _hardware_viewport(self, height: int):
        rows = self.controller.detail_rows()
        capacity = max(1, height - 8)
        if len(rows) <= capacity:
            return rows

        selected = next(
            (
                index
                for index, row in enumerate(rows)
                if row.cursor_index is not None
                and row.cursor_index == self.controller.row_cursor
            ),
            0,
        )
        # Keep the selected action visible with context above and below.  The
        # first/last rows naturally reveal that more content exists as the
        # cursor advances; no action can become unreachable at 80x20.
        start = max(0, selected - max(2, capacity // 3))
        start = min(start, max(0, len(rows) - capacity))
        return rows[start : start + capacity]

    def _draw(self) -> None:
        if (
            self.stdscr is None
            or self.controller.section is not SetupSection.HARDWARE
        ):
            super()._draw()
            return

        height, _width = self.stdscr.getmaxyx()
        if height < 20:
            super()._draw()
            return

        visible = self._hardware_viewport(height)
        controller = self.controller
        had_override = "detail_rows" in vars(controller)
        previous = vars(controller).get("detail_rows")
        controller.detail_rows = lambda: visible
        try:
            super()._draw()
        finally:
            if had_override:
                controller.detail_rows = previous
            else:
                delattr(controller, "detail_rows")

    def _resolved_button_path(self) -> str:
        selected = self.controller.selected
        candidates = [
            mouse
            for mouse in get_mouse_devices()
            if mouse.vendor == selected.vendor
            and mouse.product == selected.product
            and (
                selected.bustype is None
                or mouse.bustype is None
                or mouse.bustype == selected.bustype
            )
        ]

        if selected.phys:
            physical = [mouse for mouse in candidates if mouse.phys == selected.phys]
            if len(physical) == 1:
                return physical[0].path
            if len(physical) > 1:
                raise ButtonCaptureError(
                    "Button capture is ambiguous: multiple live event interfaces match the selected physical mouse."
                )

        if len(candidates) == 1:
            return candidates[0].path
        if not candidates:
            raise ButtonCaptureError(
                "The selected mouse is no longer available for button capture. Reconnect it and try again."
            )
        raise ButtonCaptureError(
            "Button capture is ambiguous: multiple matching mice are connected. Keep only the selected mouse attached or choose it again."
        )

    def _button_editor(self) -> None:
        assert self.stdscr is not None
        device = None
        try:
            path = self._resolved_button_path()
            device = InputDevice(path)
            device.grab()
        except OSError as exc:
            if device is not None:
                try:
                    device.close()
                except OSError:
                    pass
            raise ButtonCaptureError(self._input_error_message(exc)) from exc

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
                        "Capture is bound to the selected mouse's stable identity.",
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
                    raise ButtonCaptureError(self._input_error_message(exc)) from exc
                for event in events:
                    if event.type != ecodes.EV_KEY or event.value != 1:
                        continue
                    button = get_button_name(event.code)
                    self.stdscr.nodelay(False)
                    try:
                        action = self._choose_button_action(button)
                    except OSError as exc:
                        # Keyboard/key-chord capture can transiently lose an
                        # input fd or encounter an existing exclusive grab.
                        # Treat that as a recoverable editor failure rather than
                        # aborting the entire setup transaction.
                        self.controller.status = self._input_error_message(exc)
                        action = None
                    finally:
                        self.stdscr.nodelay(True)
                    if action is not None:
                        self.controller.apply_button_mapping(button, action)
                    break
                curses.napms(20)
        except OSError as exc:
            # No transient evdev I/O failure is allowed to escape the button
            # editor and tear down setup. Existing staged mappings are intact.
            raise ButtonCaptureError(self._input_error_message(exc)) from exc
        finally:
            if nodelay_enabled:
                self.stdscr.nodelay(False)
            if device is not None:
                try:
                    device.ungrab()
                except OSError:
                    pass
                try:
                    device.close()
                except OSError:
                    pass


def run_complete_setup_tui(
    devices: list[Any] | tuple[Any, ...],
    existing_config: dict[str, object],
    *,
    choices_factory: Callable[[dict[str, object]], SetupChoices],
    backend_factory: Callable[[Any], Any] = get_backend,
) -> SetupTuiResult:
    """Run the complete 0.9.2 setup surface and restore temporary state on abort."""
    controller = SetupController(
        devices,
        existing_config,
        choices_factory=choices_factory,
        backend_factory=backend_factory,
    )
    try:
        finished = run_curses(CompleteCursesSetupApp(controller))
    except BaseException:
        controller.restore_temporary_state()
        raise
    return SetupTuiResult(
        finished=bool(finished),
        selected=controller.selected,
        backend=controller.backend,
        choices=controller.choices,
    )
