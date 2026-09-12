from pathlib import Path
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mouse_control.hidpp import HidppDevice, HidppFeature
from mouse_control.hidpp_debug import coordinated_discovery, debug_dpi


DEVICE = HidppDevice(0x046D, 0x4074, 1, "G305", Path("/dev/hidraw6"),
                     (4, 2), {})


def test_controlled_discovery_saves_live_metadata():
    save = Mock(return_value=Path("/tmp/cache.json"))
    with patch("mouse_control.hidpp_debug._candidate_identities",
               return_value=[(0x046D, 0x4074)]):
        assert coordinated_discovery(discover=Mock(return_value=DEVICE),
                                     save=save) == [DEVICE]
    save.assert_called_once_with(DEVICE)


def test_debug_capture_learns_and_saves_observed_event_index():
    packet = bytes([0x11, 1, 7, 0x10, 4]) + bytes(15)
    discovered = HidppDevice(
        0x046D, 0x4074, 1, "G305", Path("/dev/hidraw6"), (4, 2),
        {0x2201: HidppFeature(0x2201, 0x1A, 0, 1)},
    )
    with patch("mouse_control.hidpp_debug.coordinated_discovery", return_value=[discovered]), \
         patch("mouse_control.hidpp_debug.os.open", return_value=9), \
         patch("mouse_control.hidpp_debug.select.select",
               side_effect=[([9], [], []), KeyboardInterrupt()]), \
         patch("mouse_control.hidpp_debug.os.read", return_value=packet), \
         patch("mouse_control.hidpp_debug.os.close"), \
         patch("mouse_control.hidpp_debug.save_hidpp_device",
               return_value=Path("/tmp/cache.json")) as save:
        assert debug_dpi() == 0
    saved = save.call_args.args[0]
    assert saved.feature(0x2201).index == 0x1A
    assert saved.dpi_event.feature_index == 0x07


def test_debug_capture_does_not_save_conflicting_event_indexes():
    packets = [bytes([0x11, 1, index, 0x10, stage]) + bytes(15)
               for index, stage in ((7, 0), (8, 1))]
    discovered = HidppDevice(
        0x046D, 0x4074, 1, "G305", Path("/dev/hidraw6"), (4, 2),
        {0x2201: HidppFeature(0x2201, 0x1A, 0, 1)},
    )
    with patch("mouse_control.hidpp_debug.coordinated_discovery", return_value=[discovered]), \
         patch("mouse_control.hidpp_debug.os.open", return_value=9), \
         patch("mouse_control.hidpp_debug.select.select",
               side_effect=[([9], [], []), ([9], [], []), KeyboardInterrupt()]), \
         patch("mouse_control.hidpp_debug.os.read", side_effect=packets), \
         patch("mouse_control.hidpp_debug.os.close"), \
         patch("mouse_control.hidpp_debug.save_hidpp_device") as save:
        assert debug_dpi() == 0
    save.assert_not_called()
