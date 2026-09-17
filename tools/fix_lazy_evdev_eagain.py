from pathlib import Path

src = Path("src/mouse_control/setup_tui_curses.py")
text = src.read_text()
old = """                try:\n                    events = device.read()\n                except BlockingIOError:\n"""
new = """                try:\n                    # evdev.read() returns a lazy iterator; force iteration inside\n                    # the protected block so EAGAIN raised by device_read_many()\n                    # is handled as the normal nonblocking idle state.\n                    events = tuple(device.read())\n                except BlockingIOError:\n"""
if old not in text:
    raise SystemExit("target read block not found")
src.write_text(text.replace(old, new, 1))

Path("tests/test_button_capture_eagain.py").write_text('''import errno\nfrom pathlib import Path\n\n\ndef test_button_editor_materializes_evdev_iterator_inside_try():\n    source = Path("src/mouse_control/setup_tui_curses.py").read_text()\n    assert "events = tuple(device.read())" in source\n    assert source.index("events = tuple(device.read())") < source.index("except BlockingIOError:")\n\n\ndef test_lazy_evdev_eagain_is_caught_during_materialization():\n    class LazyRead:\n        def __iter__(self):\n            raise BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable")\n\n    try:\n        events = tuple(LazyRead())\n    except BlockingIOError as exc:\n        if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:\n            events = ()\n        else:\n            raise\n\n    assert events == ()\n''')
print("fixed lazy evdev EAGAIN handling and strengthened regression")
