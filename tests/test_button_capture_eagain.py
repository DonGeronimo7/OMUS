import errno
from pathlib import Path


def test_button_editor_materializes_evdev_iterator_inside_try():
    source = Path("src/mouse_control/setup_tui_curses.py").read_text()
    assert "events = tuple(device.read())" in source
    assert source.index("events = tuple(device.read())") < source.index("except BlockingIOError:")


def test_lazy_evdev_eagain_is_caught_during_materialization():
    class LazyRead:
        def __iter__(self):
            raise BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable")

    try:
        events = tuple(LazyRead())
    except BlockingIOError as exc:
        if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:
            events = ()
        else:
            raise

    assert events == ()
