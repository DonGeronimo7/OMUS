"""Temporary exclusive evdev keyboard capture for the setup wizard."""

from contextlib import contextmanager
import os
from select import select
import sys
import termios

from evdev import InputDevice, ecodes

from .discovery import _iter_candidate_paths


class KeyboardGrabError(RuntimeError):
    """The wizard could not safely reserve every keyboard used for capture."""


def keyboard_key_name(code: int) -> str | None:
    """Resolve aliases to a KEY_* name accepted by the remapper."""
    names = ecodes.bytype.get(ecodes.EV_KEY, {}).get(code, ())
    if isinstance(names, str):
        names = [names]
    return next((name for name in names if name.startswith("KEY_")
                 and name != "KEY_RESERVED" and getattr(ecodes, name, None) == code), None)


def _open_keyboards(*, exclude_paths: tuple[str, ...] = ()) -> list[InputDevice]:
    devices = []
    seen = set()
    excluded = {os.path.realpath(item) for item in exclude_paths}
    paths = sorted(_iter_candidate_paths(),
                   key=lambda path: not path.endswith("-event-kbd"))
    try:
        for path in paths:
            realpath = os.path.realpath(path)
            if realpath in excluded or realpath in seen:
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


def _drain_queued_events(device: InputDevice) -> None:
    """Discard events queued before a capture window begins."""
    while True:
        try:
            list(device.read())
        except BlockingIOError:
            return


def _prepare_neutral_keyboards(devices: list[InputDevice]) -> list[InputDevice]:
    """Drain stale input and let pre-existing held keys release before grabbing.

    Waiting for release while devices are still ungrabbed avoids suppressing a
    key-up whose key-down was already delivered to the compositor (for example
    the Enter press that selected shortcut capture in the wizard).
    """
    active = devices[:]
    held: dict[int, set[int]] = {}
    for device in active[:]:
        try:
            _drain_queued_events(device)
            held[device.fd] = set(device.active_keys())
        except OSError:
            active.remove(device)
            held.pop(device.fd, None)

    while active and any(held.get(device.fd) for device in active):
        ready, _, _ = select(active, [], [])
        for device in ready:
            try:
                for event in device.read():
                    if event.type == ecodes.EV_KEY and event.value == 0:
                        held[device.fd].discard(event.code)
            except BlockingIOError:
                continue
            except OSError:
                active.remove(device)
                held.pop(device.fd, None)
    return active


@contextmanager
def _exclusive_keyboards(devices: list[InputDevice]):
    """Exclusively reserve all capture devices, rolling back partial grabs."""
    grabbed: list[InputDevice] = []
    try:
        for device in devices:
            try:
                device.grab()
            except OSError as exc:
                raise KeyboardGrabError(str(exc)) from exc
            grabbed.append(device)
        yield
    finally:
        for device in reversed(grabbed):
            try:
                device.ungrab()
            except OSError:
                pass


def _print_grab_failure(*, chord: bool = False) -> None:
    print("Safe keyboard capture is unavailable because Mouse Control could not")
    print("temporarily reserve every keyboard input device.")
    print("No shortcut was recorded.")
    if chord:
        print("Enter the Linux KEY_* chord manually with option 7 instead.")
    else:
        print("Enter the Linux KEY_* value manually with option 5 instead.")


def capture_keyboard_key(*, exclude_paths: tuple[str, ...] = ()) -> str | None:
    """Capture a fresh key press, or return None on cancellation/unavailability.

    Ctrl is resolved on release so Ctrl+C can cancel even without a terminal.
    Release events never create a mapping without a preceding captured press.
    """
    devices: list[InputDevice] = []
    all_devices: list[InputDevice] = []
    try:
        with _capture_terminal():
            all_devices = _open_keyboards(exclude_paths=exclude_paths)
            devices = _prepare_neutral_keyboards(all_devices)
            if not devices:
                print("No readable keyboard devices found. Check input permissions or use manual entry.")
                return None
            try:
                with _exclusive_keyboards(devices):
                    print("Press the keyboard key you want to assign... (Ctrl+C to cancel)", flush=True)
                    controls = {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL}
                    pending_ctrl: dict[tuple[int, int], str] = {}
                    while devices:
                        ready, _, _ = select(devices, [], [])
                        for device in ready:
                            try:
                                for event in device.read():
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
                    print("Keyboard devices disconnected. Try again or use manual entry.")
            except KeyboardGrabError:
                _print_grab_failure()
    except KeyboardInterrupt:
        print("\nKeyboard capture cancelled.")
    except OSError:
        print("Keyboard capture stopped. Use manual entry.")
    finally:
        for device in all_devices:
            try:
                device.close()
            except OSError:
                pass
    return None


def capture_keyboard_chord(*, exclude_paths: tuple[str, ...] = ()) -> str | None:
    """Capture keys held together, in press order, until all are released."""
    devices: list[InputDevice] = []
    all_devices: list[InputDevice] = []
    try:
        # Escape cancels; disabling terminal signals permits Ctrl+C chords.
        with _capture_terminal(keep_signals=False):
            all_devices = _open_keyboards(exclude_paths=exclude_paths)
            devices = _prepare_neutral_keyboards(all_devices)
            if not devices:
                print("No readable keyboard devices found. Use manual chord entry.")
                return None
            try:
                with _exclusive_keyboards(devices):
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
                                active.clear()
                                names.clear()
                                seen.clear()
                    print("Keyboard devices disconnected. Use manual chord entry.")
            except KeyboardGrabError:
                _print_grab_failure(chord=True)
    except KeyboardInterrupt:
        print("\nKeyboard chord capture cancelled.")
    except OSError:
        print("Keyboard chord capture stopped. Use manual chord entry.")
    finally:
        for device in all_devices:
            try:
                device.close()
            except OSError:
                pass
    return None
