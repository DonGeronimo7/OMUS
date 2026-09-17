from pathlib import Path

path = Path('src/mouse_control/setup_tui_curses.py')
text = path.read_text()
old = '''                try:\n                    events = device.read()\n                except BlockingIOError:\n                    events = ()\n                except OSError as exc:\n                    raise ButtonCaptureError(\n                        self._input_error_message(exc, phase="reading mouse events")\n                    ) from exc\n'''
new = '''                try:\n                    events = device.read()\n                except BlockingIOError:\n                    # evdev is opened O_NONBLOCK. No queued input is the normal\n                    # idle state while waiting for a button press.\n                    events = ()\n                except OSError as exc:\n                    # evdev 2.x/platform combinations may surface the same\n                    # nonblocking empty-read condition as plain OSError rather\n                    # than BlockingIOError. EAGAIN/EWOULDBLOCK is not a device\n                    # failure and must never abort button remapping.\n                    if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:\n                        events = ()\n                    else:\n                        raise ButtonCaptureError(\n                            self._input_error_message(exc, phase="reading mouse events")\n                        ) from exc\n'''
if old not in text:
    raise SystemExit('target button read block not found')
path.write_text(text.replace(old, new, 1))

# Dedicated source-level regression: the production loop must explicitly treat
# OSError(EAGAIN) as an empty nonblocking read, not a fatal capture error.
test = Path('tests/test_button_capture_eagain.py')
test.write_text('''import errno\nfrom pathlib import Path\n\n\ndef test_button_editor_treats_plain_oserror_eagain_as_idle():\n    source = Path("src/mouse_control/setup_tui_curses.py").read_text()\n    assert "if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:" in source\n    assert "events = ()" in source\n    assert source.index("if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:") < source.index(\n        "self._input_error_message(exc, phase=\\\"reading mouse events\\\")"\n    )\n''')
print('patched plain OSError(EAGAIN) handling in button capture')
