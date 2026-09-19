"""Deterministic physical-to-virtual evdev frame transparency tests."""

from evdev import ecodes

from mouse_control.remapper import MouseRemapper


class TraceUInput:
    def __init__(self) -> None:
        self.frames: list[list[tuple[int, int, int]]] = []
        self._pending: list[tuple[int, int, int]] = []

    def write(self, event_type: int, code: int, value: int) -> None:
        self._pending.append((event_type, code, value))

    def syn(self) -> None:
        self.frames.append(self._pending)
        self._pending = []


def remapper(mappings: dict[str, str] | None = None) -> tuple[MouseRemapper, TraceUInput]:
    target = MouseRemapper("/dev/input/test", mappings or {})
    ui = TraceUInput()
    target.ui = ui
    return target, ui


def send(target: MouseRemapper, *events: tuple[int, int, int]) -> None:
    for event in events:
        target._process_event(*event)


def rel(code: int, value: int) -> tuple[int, int, int]:
    return ecodes.EV_REL, code, value


def key(code: int, value: int) -> tuple[int, int, int]:
    return ecodes.EV_KEY, code, value


REPORT = (ecodes.EV_SYN, ecodes.SYN_REPORT, 0)


def test_xy_motion_is_one_virtual_frame_with_exact_ordered_deltas() -> None:
    target, ui = remapper()

    send(target, rel(ecodes.REL_X, 7), rel(ecodes.REL_Y, -3), REPORT)

    assert ui.frames == [[rel(ecodes.REL_X, 7), rel(ecodes.REL_Y, -3)]]


def test_multiple_physical_motion_frames_remain_separate_virtual_frames() -> None:
    target, ui = remapper()

    send(
        target,
        rel(ecodes.REL_X, 7), rel(ecodes.REL_Y, -3), REPORT,
        rel(ecodes.REL_X, -11), rel(ecodes.REL_Y, 5), REPORT,
    )

    assert ui.frames == [
        [rel(ecodes.REL_X, 7), rel(ecodes.REL_Y, -3)],
        [rel(ecodes.REL_X, -11), rel(ecodes.REL_Y, 5)],
    ]


def test_single_axis_frames_remain_valid_and_separate() -> None:
    target, ui = remapper()

    send(target, rel(ecodes.REL_X, 4), REPORT, rel(ecodes.REL_Y, -9), REPORT)

    assert ui.frames == [[rel(ecodes.REL_X, 4)], [rel(ecodes.REL_Y, -9)]]


def test_mixed_motion_and_button_frame_preserves_boundary() -> None:
    target, ui = remapper()

    send(
        target,
        rel(ecodes.REL_X, 2), key(ecodes.BTN_LEFT, 1),
        rel(ecodes.REL_Y, 3), REPORT,
    )

    assert ui.frames == [[
        rel(ecodes.REL_X, 2), key(ecodes.BTN_LEFT, 1), rel(ecodes.REL_Y, 3)
    ]]


def test_remapped_key_is_emitted_inside_source_physical_frame() -> None:
    target, ui = remapper({"BTN_SIDE": "key:KEY_F13"})

    send(
        target,
        rel(ecodes.REL_X, 1), key(ecodes.BTN_SIDE, 1),
        rel(ecodes.REL_Y, -1), REPORT,
    )

    assert ui.frames == [[
        rel(ecodes.REL_X, 1), key(ecodes.KEY_F13, 1), rel(ecodes.REL_Y, -1)
    ]]


def test_rapid_button_activity_adds_no_motion_frame_boundaries() -> None:
    target, ui = remapper({"BTN_SIDE": "mouse:BTN_MIDDLE"})

    send(
        target,
        rel(ecodes.REL_X, 8), key(ecodes.BTN_SIDE, 1),
        key(ecodes.BTN_SIDE, 0), rel(ecodes.REL_Y, -6), REPORT,
        key(ecodes.BTN_LEFT, 1), key(ecodes.BTN_LEFT, 0), REPORT,
    )

    assert ui.frames == [
        [rel(ecodes.REL_X, 8), key(ecodes.BTN_MIDDLE, 1),
         key(ecodes.BTN_MIDDLE, 0), rel(ecodes.REL_Y, -6)],
        [key(ecodes.BTN_LEFT, 1), key(ecodes.BTN_LEFT, 0)],
    ]


def test_motion_values_are_not_scaled_reordered_duplicated_or_coalesced() -> None:
    target, ui = remapper()
    physical = [
        rel(ecodes.REL_Y, 1), rel(ecodes.REL_X, -327), rel(ecodes.REL_X, 0),
        rel(ecodes.REL_Y, 2048), rel(ecodes.REL_X, 19),
    ]

    send(target, *physical, REPORT)

    assert ui.frames == [physical]


def test_non_boundary_syn_code_stays_inside_the_physical_frame() -> None:
    target, ui = remapper()
    mt_report = (ecodes.EV_SYN, ecodes.SYN_MT_REPORT, 0)

    send(target, rel(ecodes.REL_X, 3), mt_report, rel(ecodes.REL_Y, 4), REPORT)

    assert ui.frames == [[rel(ecodes.REL_X, 3), mt_report, rel(ecodes.REL_Y, 4)]]


def test_syn_dropped_discards_until_report_releases_keys_and_recovers() -> None:
    target, ui = remapper({"BTN_SIDE": "key:KEY_F13"})
    observer = target.event_observer = type(
        "Observer", (), {
            "observe_evdev_event": lambda self, *_args: None,
            "invalidate_observer_continuity": lambda self: setattr(
                self, "invalidations", getattr(self, "invalidations", 0) + 1
            ),
        }
    )()

    send(target, key(ecodes.BTN_SIDE, 1), REPORT)
    send(
        target,
        rel(ecodes.REL_X, 99),
        (ecodes.EV_SYN, ecodes.SYN_DROPPED, 0),
        rel(ecodes.REL_Y, 88), key(ecodes.BTN_SIDE, 0), REPORT,
        rel(ecodes.REL_X, 5), rel(ecodes.REL_Y, -2), REPORT,
    )

    assert ui.frames == [
        [key(ecodes.KEY_F13, 1)],
        [key(ecodes.KEY_F13, 0)],
        [rel(ecodes.REL_X, 5), rel(ecodes.REL_Y, -2)],
    ]
    assert observer.invalidations == 1
    assert not target._pressed_keys
    assert not target._pending_frame
    assert not target._discard_until_syn_report


def test_shutdown_discards_unterminated_frame_without_stuck_synthetic_key() -> None:
    target, ui = remapper({"BTN_SIDE": "key:KEY_F13"})

    send(target, key(ecodes.BTN_SIDE, 1), rel(ecodes.REL_X, 12))
    target._pending_frame.clear()
    target._release_pressed_keys()

    assert ui.frames == []
    assert ui._pending == []
    assert not target._pressed_keys
