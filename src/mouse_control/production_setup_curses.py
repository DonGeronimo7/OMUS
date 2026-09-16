"""Production hardening layer for the full-screen setup application.

The base curses renderer remains the stable presentation contract.  This class
only overrides hardware-interaction seams that need stronger unknown-device
resilience or deeper production discovery orchestration.
"""

from __future__ import annotations

import curses

from evdev import InputDevice, ecodes

from .button_capture import is_mouse_button_code, resolve_button_capture_path
from .setup_tui_curses import CursesSetupApp as _BaseCursesSetupApp
from .setup_tui_curses import run_curses
from .wizard import ButtonCaptureError, get_button_name


class CursesSetupApp(_BaseCursesSetupApp):
    """Production setup renderer with crash-safe composite-device capture."""

    def _button_editor(self) -> None:
        assert self.stdscr is not None
        device = None
        grabbed = False
        nodelay_enabled = False

        try:
            capture_path = resolve_button_capture_path(self.controller.selected)
            device = InputDevice(capture_path)
            device.grab()
            grabbed = True

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
                    raise ButtonCaptureError(
                        f"Mouse disconnected during button capture: {exc}"
                    ) from exc

                for event in events:
                    if (
                        event.type != ecodes.EV_KEY
                        or event.value != 1
                        or not is_mouse_button_code(event.code)
                    ):
                        continue
                    button = get_button_name(event.code)
                    # Modal action selection needs blocking terminal input.  Always
                    # restore nodelay even if keyboard capture/action parsing fails.
                    self.stdscr.nodelay(False)
                    try:
                        action = self._choose_button_action(button)
                    finally:
                        self.stdscr.nodelay(True)
                    if action is not None:
                        self.controller.apply_button_mapping(button, action)
                    break
                curses.napms(20)
        except ButtonCaptureError:
            raise
        except (OSError, PermissionError) as exc:
            raise ButtonCaptureError(
                f"Could not reserve the mouse for button capture: {exc}"
            ) from exc
        except Exception as exc:
            # Unknown hardware must never tear down the full setup transaction.
            # Preserve staged mappings and return to the Buttons panel instead.
            raise ButtonCaptureError(
                f"Button capture stopped safely: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            if nodelay_enabled:
                try:
                    self.stdscr.nodelay(False)
                except curses.error:
                    pass
            if device is not None:
                if grabbed:
                    try:
                        device.ungrab()
                    except OSError:
                        pass
                try:
                    device.close()
                except OSError:
                    pass

    def _suspend_curses(self, function):
        """Run external capture while guaranteeing curses restoration."""

        assert self.stdscr is not None
        try:
            curses.def_prog_mode()
            curses.endwin()
            return function()
        finally:
            try:
                curses.reset_prog_mode()
            except curses.error:
                # curses.wrapper still performs final terminal restoration; do
                # not mask the original capture failure with a secondary error.
                pass
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            try:
                self.stdscr.nodelay(False)
                self.stdscr.refresh()
            except curses.error:
                pass
