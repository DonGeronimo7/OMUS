import errno
from types import SimpleNamespace

from mouse_control.setup_tui_curses import CursesSetupApp


class Backend:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class StdScr:
    def nodelay(self, _value):
        pass

    def getch(self):
        return 10


def test_button_capture_releases_backend_before_exclusive_grab(monkeypatch):
    backend = Backend()
    refreshed = []

    class Device:
        def __init__(self, path):
            assert path == "/dev/input/titan"

        def grab(self):
            assert backend.closed is True

        def ungrab(self):
            pass

        def close(self):
            pass

    controller = SimpleNamespace(
        backend=backend,
        selected=SimpleNamespace(path="/dev/input/titan"),
        status="",
        refresh_discovery_backend=lambda **kwargs: refreshed.append(kwargs),
    )
    app = CursesSetupApp(controller)
    app.stdscr = StdScr()
    app._modal = lambda *args, **kwargs: None
    monkeypatch.setattr("mouse_control.setup_tui_curses.InputDevice", Device)

    app._button_editor()

    assert refreshed == [{"status": "Button capture finished; hardware capabilities refreshed."}]


def test_errno11_is_recoverable_and_preserves_mappings_message():
    exc = BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable")
    message = CursesSetupApp._input_error_message(exc, phase="exclusive mouse grab")
    assert "busy during exclusive mouse grab" in message
    assert "mappings unchanged" in message
