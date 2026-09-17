"""Final 0.9.2 setup presentation refinements.

This layer keeps the complete discovery catalog navigable in small supported
terminals and resolves the selected mouse by stable identity immediately before
exclusive button capture.  It deliberately refuses ambiguous replacements.
"""

from __future__ import annotations

import curses
import errno
import os
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
    def _input_error_message(exc: OSError, *, phase: str) -> str:
        if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK, errno.EBUSY}:
            return (
                f"Input device busy during {phase}. Mouse Control kept the current "
                "mappings unchanged."
            )
        return f"Input capture failed during {phase}: {exc}"

    @staticmethod
    def _exclude_selected_mouse_from_keyboards(devices, mouse_path: str):
        """Never let keyboard capture re-grab the mouse already owned by setup."""
        selected_realpath = os.path.realpath(mouse_path)
        kept = []
        for device in devices:
            try:
                same_device = os.path.realpath(device.path) == selected_realpath
            except OSError:
                same_device = False
            if same_device:
                try:
                    device.close()
                except OSError:
                    pass
                continue
            kept.append(device)
        return kept

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

    def _choose_button_action(self, button: str) -> str | None:
        """Choose an action while excluding the already-grabbed mouse from key capture."""
        from . import setup_tui_integrated as integrated_tui

        mouse_path = getattr(self, "_button_capture_path", None)
        if not mouse_path:
            mouse_path = self._resolved_button_path()
        original_open_keyboards = integrated_tui._open_keyboards

        def open_keyboards_without_selected_mouse():
            devices = original_open_keyboards()
            return self._exclude_selected_mouse_from_keyboards(devices, mouse_path)

        integrated_tui._open_keyboards = open_keyboards_without_selected_mouse
        try:
            return super()._choose_button_action(button)
        finally:
            integrated_tui._open_keyboards = original_open_keyboards

    def _button_editor(self) -> None:
        """Give the button editor sole Mouse Control ownership of the evdev node."""
        assert self.stdscr is not None
        device = None
        nodelay_enabled = False
        self._button_capture_path = None

        # Discovery backends may retain readers/sessions for live evidence. They
        # are useful everywhere else, but button mapping requires one exclusive
        # evdev owner. Relinquish all backend resources before opening/grabbing
        # the selected event node, then rebuild capabilities after capture.
        try:
            self.controller.backend.close()
        except Exception:
            pass

        try:
            path = self._resolved_button_path()
            self._button_capture_path = path

            try:
                device = InputDevice(path)
            except OSError as exc:
                raise ButtonCaptureError(
                    self._input_error_message(exc, phase="opening selected mouse")
                ) from exc

            try:
                device.grab()
            except OSError as exc:
                raise ButtonCaptureError(
                    self._input_error_message(exc, phase="exclusive mouse grab")
                ) from exc

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
                    raise ButtonCaptureError(
                        self._input_error_message(exc, phase="reading mouse events")
                    ) from exc
                for event in events:
                    if event.type != ecodes.EV_KEY or event.value != 1:
                        continue
                    button = get_button_name(event.code)
                    self.stdscr.nodelay(False)
                    try:
                        action = self._choose_button_action(button)
                    except OSError as exc:
                        self.controller.status = self._input_error_message(
                            exc, phase="keyboard capture"
                        )
                        action = None
                    finally:
                        self.stdscr.nodelay(True)
                    if action is not None:
                        self.controller.apply_button_mapping(button, action)
                    break
                curses.napms(20)
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
            self._button_capture_path = None
            try:
                self.controller.refresh_discovery_backend(
                    status="Button capture finished; hardware capabilities refreshed."
                )
            except Exception as exc:
                self.controller.status = f"Button capture ended; capability refresh failed: {exc}"


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
