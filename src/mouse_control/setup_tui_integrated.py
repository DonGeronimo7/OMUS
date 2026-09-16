"""Integrated Mouse Control setup presentation.

The legacy experiment CLIs remain useful developer adapters, but setup must not
leave the full-screen TUI.  This module embeds their stdin/stdout contract inside
curses and keeps safe keyboard capture under the same UI.  The experiment
engines themselves remain the source of truth for identity, evidence,
verification and rollback.
"""

from __future__ import annotations

import builtins
from contextlib import redirect_stderr, redirect_stdout
import curses
from io import TextIOBase
from select import select
from typing import Any, Callable
from unittest.mock import patch

from evdev import ecodes

from .discovery_lab import DiscoveryTool, discovery_tool_specs, run_discovery_tool
from .hardware import HardwareError, get_backend
from .keyboard_capture import (
    KeyboardGrabError,
    _exclusive_keyboards,
    _open_keyboards,
    _prepare_neutral_keyboards,
    keyboard_key_name,
)
from .setup_flow import SetupChoices
from .setup_tui import SetupController, SetupTuiResult
from .setup_tui_curses import CursesSetupApp, run_curses


class _TuiWriter(TextIOBase):
    """Turn line-oriented experiment output into an in-TUI rolling transcript."""

    def __init__(self, app: "IntegratedCursesSetupApp") -> None:
        self.app = app
        self.pending = ""

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        self.pending += str(value)
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line.strip():
                self.app._append_lab_line(line.rstrip())
        return len(value)

    def flush(self) -> None:
        if self.pending.strip():
            self.app._append_lab_line(self.pending.rstrip())
        self.pending = ""


class IntegratedCursesSetupApp(CursesSetupApp):
    """0.9.2 setup surface: all normal user interaction remains in curses."""

    def __init__(self, controller: SetupController) -> None:
        super().__init__(controller)
        self._lab_title = "Automatic Discovery"
        self._lab_lines: list[str] = []

    def _append_lab_line(self, line: str) -> None:
        self._lab_lines.append(line)
        self._lab_lines = self._lab_lines[-200:]
        if self.stdscr is not None:
            self._modal(
                self._lab_title,
                self._lab_lines[-10:] or ["Working…"],
                prompt="Automatic Discovery is running",
            )

    def _lab_input(self, prompt: str = "") -> str:
        lines = list(self._lab_lines[-8:])
        if prompt.strip():
            lines.extend(("", prompt.strip()))
        while True:
            self._modal(
                self._lab_title,
                lines or ["Ready for the next measurement."],
                prompt="Enter Continue   Esc Cancel",
            )
            key = self.stdscr.getch()
            if key == curses.KEY_RESIZE:
                continue
            if key in (10, 13, curses.KEY_ENTER):
                return ""
            if key in (27, ord("b"), ord("B"), ord("q"), ord("Q")):
                raise KeyboardInterrupt

    def _tool_extra_args(self, tool: DiscoveryTool) -> list[str]:
        """Supply TUI-owned experiment parameters without hiding their meaning."""
        if tool is DiscoveryTool.CALIBRATED_DPI_DISCOVERY:
            labels = ",".join(str(value) for value in self.controller.choices.stages)
            accepted = self._confirm(
                "DPI-state calibration labels",
                [
                    "The calibrated-state experiment needs labels for the physical DPI cycle.",
                    f"Current setup labels: {labels}",
                    "These are comparison labels only; physical CPI remains the independent evidence.",
                    "If these labels are not the mouse's actual cycle, edit them before using this stage.",
                ],
                yes="Enter Use current labels",
                no="b Back",
            )
            if not accepted:
                raise KeyboardInterrupt
            return ["--dpi-values", labels]
        if tool is DiscoveryTool.DPI_GENERALIZATION:
            return ["--baseline", str(self.controller.choices.active_dpi)]
        if tool is DiscoveryTool.POLLING_REPLAY and self.controller.choices.polling_rate:
            return ["--target", str(self.controller.choices.polling_rate)]
        if tool is DiscoveryTool.POLLING_STATE_MACHINE:
            rates = tuple(self.controller.choices.polling_rates or ())
            if len(rates) >= 2:
                return ["--first", str(rates[0]), "--second", str(rates[1])]
        return []

    def _run_discovery_tool(self, tool: DiscoveryTool) -> None:
        spec = next(spec for spec in discovery_tool_specs() if spec.tool is tool)
        warning = (
            "This guarded stage may change live hardware state."
            if spec.writes_hardware
            else "This stage is read-only."
        )
        if not self._confirm(
            spec.label,
            [
                spec.description,
                "",
                warning,
                "Identity, evidence, verification and rollback rules remain enforced by the engine.",
                "Only a successful promotion may persist PROVEN write authority.",
            ],
            yes="Enter Begin",
            no="b Back",
        ):
            self.controller.status = "Discovery stage cancelled."
            return

        try:
            extra_args = self._tool_extra_args(tool)
        except KeyboardInterrupt:
            self.controller.status = "Discovery stage cancelled."
            return

        try:
            self.controller.backend.close()
        except Exception:
            pass

        self._lab_title = spec.label
        self._lab_lines = [f"Evidence phase: {spec.evidence_phase.upper()}", spec.description]
        stream = _TuiWriter(self)
        status = 1
        try:
            with patch.object(builtins, "input", self._lab_input), redirect_stdout(stream), redirect_stderr(stream):
                try:
                    status = int(
                        run_discovery_tool(
                            tool,
                            devices=self.controller.devices,
                            selected=self.controller.selected,
                            extra_args=extra_args,
                        )
                    )
                except SystemExit as exc:
                    status = int(exc.code or 0)
        except KeyboardInterrupt:
            status = 130
        except (OSError, PermissionError, ValueError, HardwareError, RuntimeError) as exc:
            self._append_lab_line(f"FAILED: {exc}")
            status = 1
        finally:
            stream.flush()

        if self._lab_lines:
            result_lines = self._lab_lines[-10:]
            result_lines.append("")
            result_lines.append(
                "Completed successfully."
                if status == 0
                else "Cancelled." if status == 130
                else f"No new PROVEN authority was produced (exit {status})."
            )
            self._confirm(
                f"{spec.label} — Result",
                result_lines,
                yes="Enter Continue",
                no="Esc Continue",
            )

        message = (
            f"✓ {spec.label} completed; capabilities refreshed."
            if status == 0
            else f"{spec.label} cancelled; capabilities refreshed."
            if status == 130
            else f"{spec.label} finished without new PROVEN authority; capabilities refreshed."
        )
        self.controller.refresh_discovery_backend(status=message)

    def _capture_key_tui(self) -> str | None:
        all_devices = []
        try:
            all_devices = _open_keyboards()
            devices = _prepare_neutral_keyboards(all_devices)
            if not devices:
                self.controller.status = "No readable keyboard devices are available."
                return None
            with _exclusive_keyboards(devices):
                controls = {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL}
                pending_ctrl: dict[tuple[int, int], str] = {}
                while devices:
                    self._modal(
                        "Keyboard key",
                        ["Press the keyboard key to assign.", "Ctrl+C cancels safely."],
                        prompt="Waiting for key…",
                    )
                    ready, _, _ = select(devices, [], [], 0.10)
                    for device in ready:
                        try:
                            events = device.read()
                        except BlockingIOError:
                            continue
                        except OSError:
                            devices.remove(device)
                            continue
                        for event in events:
                            if event.type != ecodes.EV_KEY:
                                continue
                            identity = (device.fd, event.code)
                            if event.value == 0 and identity in pending_ctrl:
                                return pending_ctrl.pop(identity)
                            if event.value != 1:
                                continue
                            name = keyboard_key_name(event.code)
                            if name is None:
                                continue
                            if event.code == ecodes.KEY_C and pending_ctrl:
                                return None
                            if event.code in controls:
                                pending_ctrl[identity] = name
                                continue
                            return next(iter(pending_ctrl.values()), name)
        except KeyboardGrabError as exc:
            self.controller.status = f"Keyboard capture unavailable: {exc}"
        finally:
            for device in all_devices:
                try:
                    device.close()
                except OSError:
                    pass
        return None

    def _capture_chord_tui(self) -> str | None:
        all_devices = []
        try:
            all_devices = _open_keyboards()
            devices = _prepare_neutral_keyboards(all_devices)
            if not devices:
                self.controller.status = "No readable keyboard devices are available."
                return None
            with _exclusive_keyboards(devices):
                active: set[tuple[int, int]] = set()
                names: list[str] = []
                seen: set[int] = set()
                while devices:
                    self._modal(
                        "Keyboard chord",
                        ["Press and hold the shortcut, then release all keys.", "Escape cancels."],
                        prompt="Waiting for chord…",
                    )
                    ready, _, _ = select(devices, [], [], 0.10)
                    for device in ready:
                        try:
                            events = device.read()
                        except BlockingIOError:
                            continue
                        except OSError:
                            devices.remove(device)
                            continue
                        for event in events:
                            if event.type != ecodes.EV_KEY:
                                continue
                            identity = (device.fd, event.code)
                            if event.value == 1 and event.code == ecodes.KEY_ESC:
                                return None
                            if event.value == 1:
                                name = keyboard_key_name(event.code)
                                if name is None or identity in active:
                                    continue
                                active.add(identity)
                                if event.code not in seen:
                                    names.append(name)
                                    seen.add(event.code)
                            elif event.value == 0 and identity in active:
                                active.remove(identity)
                                if not active:
                                    if len(names) >= 2:
                                        return "chord:" + "+".join(names)
                                    names.clear()
                                    seen.clear()
        except KeyboardGrabError as exc:
            self.controller.status = f"Keyboard capture unavailable: {exc}"
        finally:
            for device in all_devices:
                try:
                    device.close()
                except OSError:
                    pass
        return None

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
        from .remapper import parse_action

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
                continue
            if key == curses.KEY_DOWN:
                cursor = (cursor + 1) % len(options)
                continue
            if key == 27:
                return None
            if key not in (10, 13, curses.KEY_ENTER):
                continue
            action = options[cursor][1]
            if action == "__key__":
                name = self._capture_key_tui()
                return f"key:{name}" if name else None
            if action == "__chord__":
                return self._capture_chord_tui()
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
            except ValueError as exc:
                self.controller.status = f"Invalid action: {exc}"
                return None
            return action


def run_integrated_setup_tui(
    devices: list[Any] | tuple[Any, ...],
    existing_config: dict[str, object],
    *,
    choices_factory: Callable[[dict[str, object]], SetupChoices],
    backend_factory: Callable[[Any], Any] = get_backend,
) -> SetupTuiResult:
    """Run the complete setup surface without leaving curses for sub-wizards."""
    controller = SetupController(
        devices,
        existing_config,
        choices_factory=choices_factory,
        backend_factory=backend_factory,
    )
    try:
        finished = run_curses(IntegratedCursesSetupApp(controller))
    except BaseException:
        controller.restore_temporary_state()
        raise
    return SetupTuiResult(
        finished=bool(finished),
        selected=controller.selected,
        backend=controller.backend,
        choices=controller.choices,
    )
