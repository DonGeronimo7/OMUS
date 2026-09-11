from pathlib import Path
import sys
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mouse_control.hidpp_debug import (G305_DPI_PROFILE, dpi_stage_event,
                                       find_g305_hidraw, parse_hidpp_report,
                                       watch_dpi_events)


def test_parse_hidpp_report_header_and_preserve_parameters():
    report = parse_hidpp_report(bytes.fromhex('11 ff 0c 20 00 05 dc'))
    assert report is not None
    assert report.report_id == 0x11
    assert report.device_index == 0xFF
    assert report.feature_index == 0x0C
    assert report.function_or_event == 2
    assert report.software_id == 0
    assert report.parameters == bytes.fromhex('00 05 dc')


def test_non_hidpp_report_is_not_misdecoded():
    assert parse_hidpp_report(bytes.fromhex('01 02 03 04')) is None
    assert parse_hidpp_report(b'\x11\xff') is None


def test_hidraw_resolution_uses_exact_g305_identity(tmp_path):
    sysfs = tmp_path / 'hidraw'
    for name, identity in [('hidraw3', '0003:0000046D:0000C53F'),
                           ('hidraw6', '0003:0000046D:00004074')]:
        directory = sysfs / name / 'device'
        directory.mkdir(parents=True)
        (directory / 'uevent').write_text(f'HID_ID={identity}\nHID_NAME=Logitech\n')
    assert find_g305_hidraw(sysfs, Path('/dev')) == [Path('/dev/hidraw6')]


def packet(stage, *, device=1, feature=7, event=1, swid=0):
    return bytes([0x11, device, feature, (event << 4) | swid, stage]) + bytes(15)


def test_real_g305_packet_structure_returns_stage_indexes():
    assert [dpi_stage_event(packet(stage), G305_DPI_PROFILE)
            for stage in (0, 1, 2, 3, 4, 0)] == [0, 1, 2, 3, 4, 0]


def test_dpi_filter_ignores_raw_traffic_and_unrelated_hidpp_events():
    assert dpi_stage_event(bytes.fromhex('02 00 01 02 03'), G305_DPI_PROFILE) is None
    assert dpi_stage_event(packet(1, device=2), G305_DPI_PROFILE) is None
    assert dpi_stage_event(packet(1, feature=8), G305_DPI_PROFILE) is None
    assert dpi_stage_event(packet(1, event=2), G305_DPI_PROFILE) is None
    assert dpi_stage_event(packet(1, swid=1), G305_DPI_PROFILE) is None


def test_missing_hidraw_permission_is_nonfatal():
    stop = threading.Event()
    def denied(*args, **kwargs):
        stop.set()
        raise PermissionError('denied')
    with patch('mouse_control.hidpp_debug.find_hidraw', return_value=[Path('/dev/hidraw6')]), \
         patch('mouse_control.hidpp_debug.os.open', side_effect=denied):
        watch_dpi_events(G305_DPI_PROFILE, '', lambda stage: None, stop,
                         retry_interval=0)


def test_disappearing_hidraw_is_closed_and_nonfatal():
    stop = threading.Event()
    def disappeared(*args, **kwargs):
        stop.set()
        raise OSError('unplugged')
    with patch('mouse_control.hidpp_debug.find_hidraw', return_value=[Path('/dev/hidraw6')]), \
         patch('mouse_control.hidpp_debug.os.open', return_value=9), \
         patch('mouse_control.hidpp_debug.select.select', return_value=([9], [], [])), \
         patch('mouse_control.hidpp_debug.os.read', side_effect=disappeared), \
         patch('mouse_control.hidpp_debug.os.close') as close:
        watch_dpi_events(G305_DPI_PROFILE, '', lambda stage: None, stop,
                         retry_interval=0)
    close.assert_called_once_with(9)
