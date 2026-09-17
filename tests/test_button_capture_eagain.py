import errno
from pathlib import Path


def test_button_editor_treats_plain_oserror_eagain_as_idle():
    source = Path("src/mouse_control/setup_tui_curses.py").read_text()
    assert "if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:" in source
    assert "events = ()" in source
    assert source.index("if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:") < source.index(
        "self._input_error_message(exc, phase=\"reading mouse events\")"
    )
