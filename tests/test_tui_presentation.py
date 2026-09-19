from types import SimpleNamespace

from mouse_control.setup_tui import ActionKind, ControllerAction, DisplayRow, SECTIONS, SetupSection
from mouse_control.setup_tui import SetupController
from mouse_control.setup_flow import SetupChoices
from mouse_control.hardware.capabilities import BatteryState
from mouse_control.setup_tui_curses import CursesSetupApp
from mouse_control.tui_presentation import (
    LayoutMode,
    footer_hint,
    frame_layout,
    status_label,
    visible_window,
    wrap_text,
)
from test_setup_tui import controller as make_controller


def test_layout_uses_rail_compact_mode_and_clean_minimum_message():
    assert frame_layout(24, 100).mode is LayoutMode.FULL
    compact = frame_layout(16, 60)
    assert compact.mode is LayoutMode.COMPACT
    assert compact.sidebar_width == 0
    assert compact.content_width > 0
    assert frame_layout(11, 80).mode is LayoutMode.TOO_SMALL
    assert frame_layout(20, 47).mode is LayoutMode.TOO_SMALL


def test_viewport_keeps_focus_visible_for_long_and_short_lists():
    assert visible_window(3, 2, 8) == (0, 3)
    start, end = visible_window(100, 73, 9)
    assert start <= 73 < end
    assert end - start == 9
    assert visible_window(100, 99, 9) == (91, 100)


def test_status_wrap_and_labels_do_not_depend_on_color():
    lines = wrap_text("Imported evidence does not grant hardware write authority.", 20)
    assert len(lines) > 1
    assert "".join(lines).replace(" ", "") == (
        "Imported evidence does not grant hardware write authority.".replace(" ", "")
    )
    assert status_label("Hardware initialization failed: unavailable") == "ERROR"
    assert status_label("Known device ready") == "READY"
    assert status_label("Mouse Control is up to date") == "READY"
    assert status_label("Physical qualification pending") == "CHECK"


def test_footer_is_contextual_and_has_vim_and_arrow_navigation():
    full = footer_hint("DPI", backend_ready=True, compact=False)
    assert "↑↓/j/k" in full
    assert "←→/h/l" in full
    assert "page" in full
    assert "g/G first/last" in full
    assert "Enter edit" in full
    assert "help" in full
    review = footer_hint("Review / Save", backend_ready=True, compact=True)
    assert "h/l page" in review
    assert "q quit" in review
    assert "section" not in review


def test_no_device_controller_is_a_safe_navigable_empty_state():
    controller = SetupController(
        [], {}, choices_factory=lambda _existing: SetupChoices(),
        initialize_backend=False,
    )
    assert controller.selected is None
    assert controller.backend_ready is False
    assert controller.handle_key("DOWN").kind is ActionKind.NONE
    assert controller.handle_key("ENTER").kind is ActionKind.NONE
    assert "No mouse" in controller.status
    assert controller.handle_key("HELP").kind is ActionKind.HELP
    assert controller.handle_key("QUIT").kind is ActionKind.CANCEL


def test_dashboard_snapshots_battery_without_querying_during_redraw():
    device = SimpleNamespace(
        name="Wireless Mouse", vendor=0x1234, product=0x5678,
        phys="usb-receiver", path="/dev/input/event9",
    )

    class Backend:
        protocol_adapter_name = "Test"
        has_proven_learned_adapter = False

        def supports_dpi(self, _device): return False
        def supports_polling_rate(self, _device): return False
        def supports_polling_rate_writes(self, _device): return False
        def supports_dpi_events(self, _device): return False
        def supports_battery(self, _device): return True
        def get_battery_state(self, _device): return BatteryState(73, status="charging")
        def close(self): pass

    controller = SetupController(
        [device], {}, choices_factory=lambda _existing: SetupChoices(),
        backend_factory=lambda _device: Backend(),
    )
    assert controller.battery_state.percentage == 73
    assert "Battery / power: 73%, charging" in "\n".join(controller.hardware_lines())


def test_button_and_review_rows_are_dense_complete_summaries():
    device = SimpleNamespace(
        name="Scan Mouse", vendor=0x1234, product=0x5678,
        phys="usb-scan", path="/dev/input/event2",
    )

    class Backend:
        protocol_adapter_name = None
        has_proven_learned_adapter = False
        def supports_dpi(self, _device): return False
        def supports_polling_rate(self, _device): return False
        def supports_polling_rate_writes(self, _device): return False
        def supports_dpi_events(self, _device): return False
        def supports_battery(self, _device): return False
        def close(self): pass

    controller = SetupController(
        [device], {},
        choices_factory=lambda _existing: SetupChoices(
            mappings={"BTN_SIDE": "chord:KEY_LEFTCTRL+KEY_C"}
        ),
        backend_factory=lambda _device: Backend(),
    )
    controller.section_index = 5
    assert any("BTN_SIDE" in row.text and "KEY_LEFTCTRL" in row.text
               for row in controller.detail_rows())
    controller.section_index = SECTIONS.index(SetupSection.REVIEW)
    review = "\n".join(row.text for row in controller.detail_rows())
    assert "1234:5678" in review
    assert "usb-scan" in review
    assert "Capability limitation" in review


class _IdleScreen:
    def __init__(self):
        self.keys = iter((-1, -1, ord("q")))

    def keypad(self, _enabled):
        pass

    def timeout(self, _milliseconds):
        pass

    def getch(self):
        return next(self.keys)


class _RecordingScreen:
    def __init__(self, height=24, width=100):
        self.height = height
        self.width = width
        self.cells = [[" " for _ in range(width)] for _ in range(height)]

    def getmaxyx(self):
        return self.height, self.width

    def erase(self):
        self.cells = [[" " for _ in range(self.width)] for _ in range(self.height)]

    def addstr(self, y, x, text, _attr=0):
        for offset, character in enumerate(text):
            if 0 <= y < self.height and 0 <= x + offset < self.width:
                self.cells[y][x + offset] = character

    def addch(self, y, x, character):
        self.addstr(y, x, str(character)[0])

    def hline(self, y, x, character, count):
        self.addstr(y, x, str(character)[0] * count)

    def vline(self, y, x, character, count):
        for offset in range(count):
            self.addstr(y + offset, x, str(character)[0])

    def noutrefresh(self):
        pass

    def box(self):
        self.hline(0, 0, "-", self.width)
        self.hline(self.height - 1, 0, "-", self.width)

    def text(self):
        return "\n".join("".join(row).rstrip() for row in self.cells)


def test_idle_timeouts_do_not_trigger_redraw(monkeypatch):
    controller = SimpleNamespace(
        devices=(object(),),
        selected_index=0,
        section=SetupSection.DEVICE,
        backend_ready=True,
        handle_key=lambda _key: ControllerAction(ActionKind.CANCEL),
    )
    app = CursesSetupApp(controller)
    draws = []
    monkeypatch.setattr(app, "_draw", lambda: draws.append("draw"))
    monkeypatch.setattr(app, "_start_initialization", lambda _index: None)
    monkeypatch.setattr(app, "_poll_initialization", lambda: False)
    monkeypatch.setattr(app, "_finish_initialization", lambda: None)
    monkeypatch.setattr(app, "_init_colors", lambda: None)
    monkeypatch.setattr(app, "_confirm", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("mouse_control.setup_tui_curses.curses.curs_set", lambda _value: None)

    assert app.run(_IdleScreen()) is False
    # One immediate usable frame and one state/status frame after worker start;
    # the two idle timeout wakes do not repaint.
    assert draws == ["draw", "draw"]


def test_full_navigation_uses_compact_named_boxed_rows_without_numbers(monkeypatch):
    controller = SimpleNamespace(
        devices=(object(),),
        selected=SimpleNamespace(name="Example Mouse"),
        selected_index=0,
        device_cursor=0,
        section=SetupSection.DPI,
        backend_ready=True,
        row_cursor=0,
        status="Known device ready",
        notice="",
        choices=SimpleNamespace(polling_rates=(), polling_writable=False),
        detail_rows=lambda: [DisplayRow("3000 DPI     READ/WRITE", role="primary")],
    )
    screen = _RecordingScreen()
    app = CursesSetupApp(controller)
    app.stdscr = screen
    for name, character in {
        "ACS_VLINE": "│", "ACS_HLINE": "─", "ACS_ULCORNER": "┌",
        "ACS_URCORNER": "┐", "ACS_LLCORNER": "└", "ACS_LRCORNER": "┘",
    }.items():
        monkeypatch.setattr("mouse_control.setup_tui_curses.curses." + name, character, raising=False)
    monkeypatch.setattr("mouse_control.setup_tui_curses.curses.doupdate", lambda: None)
    app._draw()

    rendered = screen.text()
    assert "[ Device" in rendered
    assert "[ Hardware Discovery" in rendered
    assert " 01  Device" not in rendered
    assert " 02  Hardware Discovery" not in rendered
    assert "g/G first/last" in rendered
    assert "h/l page" in rendered


def test_dense_screen_page_scroll_does_not_change_selected_action():
    controller = SimpleNamespace(
        section=SetupSection.LAB,
        row_cursor=1,
        detail_rows=lambda: [DisplayRow(f"line {index}") for index in range(40)],
    )
    app = CursesSetupApp(controller)
    app.stdscr = SimpleNamespace(getmaxyx=lambda: (18, 76))
    app._scroll_content(1)
    assert app._content_offsets[SetupSection.LAB] > 0
    assert controller.row_cursor == 1
    app._scroll_content(-1)
    assert app._content_offsets[SetupSection.LAB] == 0


def test_deep_lab_navigation_renders_in_main_content_plane(monkeypatch):
    controller, _backends = make_controller()
    controller.section_index = SECTIONS.index(SetupSection.LAB)
    screen = _RecordingScreen(height=28, width=120)
    app = CursesSetupApp(controller)
    app.stdscr = screen
    app._open_advanced_tools()
    app._lab_views[-1].cursor = 1  # Protocol Analysis
    app._handle_lab_view_key("ENTER")
    app._lab_views[-1].cursor = 4  # Protocol Timing Profiler
    app._handle_lab_view_key("ENTER")

    for name, character in {
        "ACS_VLINE": "│", "ACS_HLINE": "─", "ACS_ULCORNER": "┌",
        "ACS_URCORNER": "┐", "ACS_LLCORNER": "└", "ACS_LRCORNER": "┘",
    }.items():
        monkeypatch.setattr("mouse_control.setup_tui_curses.curses." + name, character, raising=False)
    monkeypatch.setattr("mouse_control.setup_tui_curses.curses.doupdate", lambda: None)
    monkeypatch.setattr(
        "mouse_control.setup_tui_curses.curses.newwin",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("ordinary navigation created a nested window")
        ),
    )

    app._draw()

    rendered = screen.text()
    assert "Discovery Lab › Advanced Tools › Protocol Analysis" in rendered
    assert "Protocol Timing Profiler" in rendered
    assert "j/k scroll" in rendered
    assert "g/G top/bottom" in rendered
    assert "Enter open" not in rendered


def test_true_modal_dialog_still_creates_a_focused_overlay(monkeypatch):
    controller, _backends = make_controller()
    parent = _RecordingScreen(height=24, width=100)
    overlay = _RecordingScreen(height=8, width=48)
    app = CursesSetupApp(controller)
    app.stdscr = parent
    created = []
    monkeypatch.setattr(
        "mouse_control.setup_tui_curses.curses.newwin",
        lambda height, width, y, x: created.append((height, width, y, x)) or overlay,
    )
    monkeypatch.setattr("mouse_control.setup_tui_curses.curses.doupdate", lambda: None)

    app._modal("Warning", ["This action needs confirmation."], prompt="Enter Confirm   b Back")

    assert created
    assert "Warning" in overlay.text()
    assert "Enter Confirm" in overlay.text()
