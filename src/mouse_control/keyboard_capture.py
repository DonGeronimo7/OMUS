"""Temporary, non-exclusive evdev keyboard capture for the setup wizard."""

from contextlib import contextmanager
import os
from select import select
import sys
import termios

from evdev import InputDevice, ecodes

from .discovery import _iter_candidate_paths


def keyboard_key_name(code: int) -> str | None:
    """Resolve aliases to a KEY_* name accepted by the remapper."""
    names = ecodes.bytype.get(ecodes.EV_KEY, {}).get(code, ())
    if isinstance(names, str):
        names = [names]
    return next((name for name in names if name.startswith("KEY_")
                 and name != "KEY_RESERVED" and getattr(ecodes, name, None) == code), None)


def _open_keyboards() -> list[InputDevice]:
    devices = []
    seen = set()
    paths = sorted(_iter_candidate_paths(),
                   key=lambda path: not path.endswith("-event-kbd"))
    try:
        for path in paths:
            realpath = os.path.realpath(path)
            if realpath in seen:
                continue
            device = None
            try:
                device = InputDevice(path)
                keys = device.capabilities(verbose=False).get(ecodes.EV_KEY, [])
                # Include separate media-key interfaces, but exclude our remapper.
                if (not device.name.startswith("mouse-control:")
                        and any(keyboard_key_name(code) for code in keys)):
                    devices.append(device)
                    seen.add(realpath)
                    device = None
            except OSError:
                continue
            finally:
                if device is not None:
                    device.close()
        return devices
    except BaseException:
        for device in devices:
            device.close()
        raise


@contextmanager
def _capture_terminal(*, keep_signals: bool = True):
    """Suppress echo and discard captured terminal input on exit."""
    fd = None
    settings = None
    try:
        if sys.stdin.isatty():
            fd = sys.stdin.fileno()
            settings = termios.tcgetattr(fd)
            capture = termios.tcgetattr(fd)
            capture[3] &= ~(termios.ICANON | termios.ECHO)
            if not keep_signals:
                capture[3] &= ~termios.ISIG
            termios.tcsetattr(fd, termios.TCSANOW, capture)
        yield
    finally:
        if settings is not None:
            termios.tcsetattr(fd, termios.TCSAFLUSH, settings)


def capture_keyboard_key() -> str | None:
    """Capture a fresh key press, or return None on cancellation/unavailability.

    Ctrl is resolved on release so Ctrl+C can cancel even without a terminal.
    Release events never create a mapping without a preceding captured press.
    """
    devices = []
    try:
        with _capture_terminal():
            devices = _open_keyboards()
            blocked = {}
            for device in devices[:]:
                try:
                    # Discard events queued during discovery, including menu Enter.
                    while True:
                        try:
                            list(device.read())
                        except BlockingIOError:
                            break
                    blocked[device.fd] = set(device.active_keys())
                except OSError:
                    devices.remove(device)
                    device.close()
            if not devices:
                print("No readable keyboard devices found. Check input permissions or use manual entry.")
                return None
            print("Press the keyboard key you want to assign... (Ctrl+C to cancel)", flush=True)
            controls = {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL}
            pending_ctrl = {}
            while devices:
                ready, _, _ = select(devices, [], [])
                for device in ready:
                    try:
                        for event in device.read():
                            if event.type != ecodes.EV_KEY:
                                continue
                            identity = (device.fd, event.code)
                            if event.code in blocked[device.fd]:
                                if event.value == 0:
                                    blocked[device.fd].discard(event.code)
                                continue
                            if event.value == 0 and identity in pending_ctrl:
                                return pending_ctrl.pop(identity)
                            if event.value != 1:
                                continue
                            name = keyboard_key_name(event.code)
                            if name is None:
                                continue
                            if event.code == ecodes.KEY_C and pending_ctrl:
                                raise KeyboardInterrupt
                            if event.code in controls:
                                pending_ctrl[identity] = name
                                continue
                            return next(iter(pending_ctrl.values()), name)
                    except BlockingIOError:
                        continue
                    except OSError:
                        devices.remove(device)
                        pending_ctrl = {key: value for key, value in pending_ctrl.items()
                                        if key[0] != device.fd}
                        device.close()
            print("Keyboard devices disconnected. Try again or use manual entry.")
    except KeyboardInterrupt:
        print("\nKeyboard capture cancelled.")
    finally:
        for device in devices:
            device.close()
    return None


def capture_keyboard_chord() -> str | None:
    """Capture keys held together, in press order, until all are released."""
    devices = []
    try:
        # Escape cancels; disabling terminal signals permits Ctrl+C chords.
        with _capture_terminal(keep_signals=False):
            devices = _open_keyboards()
            blocked = {}
            for device in devices[:]:
                try:
                    while True:
                        try:
                            list(device.read())
                        except BlockingIOError:
                            break
                    blocked[device.fd] = set(device.active_keys())
                except OSError:
                    devices.remove(device)
                    device.close()
            if not devices:
                print("No readable keyboard devices found. Use manual chord entry.")
                return None
            print("Press and hold the keyboard shortcut, then release it... (Esc to cancel)",
                  flush=True)
            active: set[tuple[int, int]] = set()
            names: list[str] = []
            seen: set[int] = set()
            while devices:
                ready, _, _ = select(devices, [], [])
                for device in ready:
                    try:
                        for event in device.read():
                            if event.type != ecodes.EV_KEY:
                                continue
                            identity = (device.fd, event.code)
                            if event.code in blocked[device.fd]:
                                if event.value == 0:
                                    blocked[device.fd].discard(event.code)
                                continue
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
                    except BlockingIOError:
                        continue
                    except OSError:
                        devices.remove(device)
                        device.close()
                        active.clear()
                        names.clear()
                        seen.clear()
            print("Keyboard devices disconnected. Use manual chord entry.")
    except KeyboardInterrupt:
        print("\nKeyboard chord capture cancelled.")
    except OSError:
        print("Keyboard chord capture stopped. Use manual chord entry.")
    finally:
        for device in devices:
            device.close()
    return None
