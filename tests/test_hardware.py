"""Hardware tests use no daemon, input device, or real writes."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys

import pytest

from mouse_control import cli
from mouse_control.discovery import MouseDevice
from mouse_control.hardware import HardwareBackend, HardwareError, get_backend
from mouse_control.hardware.capabilities import (HardwareCapabilities,
                                                 ReportRateCapabilities)
from mouse_control.hardware.generic import GenericBackend
from mouse_control.hardware.native_hid import NativeHidBackend
from mouse_control.hardware.openrazer import OpenRazerBackend

G305 = MouseDevice("G305", "/dev/input/test", vendor=0x046d, product=0x4074)
RAZER = MouseDevice("Razer", "/dev/input/test", vendor=0x1532, product=0x0099)


def razer_device(features=("dpi", "poll_rate", "supported_poll_rates"), **kwargs):
    return SimpleNamespace(_vid=0x1532, _pid=0x0099, type="mouse", name="Razer mouse",
                           has=lambda feature: feature in features, dpi=(800, 800),
                           max_dpi=20000, available_dpi=[400, 800, 1600],
                           poll_rate=500, supported_poll_rates=[125, 500, 1000], **kwargs)


def razer_backend(*devices):
    return OpenRazerBackend(lambda: SimpleNamespace(devices=list(devices)))


def test_native_hid_is_first_backend_and_unknown_falls_back():
    native, later = Mock(spec=HardwareBackend), Mock()
    native.supports_device.return_value = True
    assert get_backend(G305, [lambda: native, later]) is native
    later.assert_not_called()
    unknown = MouseDevice("unknown", "/test", vendor=1, product=2)
    assert isinstance(get_backend(unknown, [NativeHidBackend]), GenericBackend)


def test_transient_backend_enumeration_failure_falls_back_without_retry_log_spam(caplog):
    backend = Mock(spec=HardwareBackend)
    backend.supports_device.side_effect = OSError("hidraw not ready")
    assert isinstance(get_backend(G305, [lambda: backend]), GenericBackend)
    assert caplog.text.count("Hardware discovery failed") == 1
    caplog.clear()
    assert isinstance(get_backend(G305, [lambda: backend], log_failures=False), GenericBackend)
    assert "Hardware discovery failed" not in caplog.text


def test_native_hid_watcher_failure_propagates_to_supervisor():
    from mouse_control.hidpp import HidppError

    backend = NativeHidBackend()
    backend._driver = Mock(side_effect=HidppError("receiver absent"))

    with pytest.raises(HidppError, match="receiver absent"):
        backend.watch_dpi_events(G305, Mock(), Mock())
    backend._driver.assert_called_once_with(G305)


def test_native_hid_refuses_ambiguous_interfaces_and_keeps_devices_distinct():
    interfaces = [SimpleNamespace(path="/dev/hidraw1"),
                  SimpleNamespace(path="/dev/hidraw2")]
    sessions = []
    class Session:
        closed = False
        def __init__(self, path): self.path = path; sessions.append(self)
        def close(self): self.closed = True
    driver = SimpleNamespace(name="G305", capabilities=SimpleNamespace())
    backend = NativeHidBackend(discovery=lambda _device: interfaces,
                               session_factory=Session,
                               connectors=(lambda _session: driver,))
    with pytest.raises(HardwareError, match="multiple interfaces"):
        backend.supports_device(G305)
    assert all(session.closed for session in sessions)

    first = G305
    second = MouseDevice("G305", "/dev/input/other", vendor=0x046d, product=0x4074)
    backend = NativeHidBackend(
        discovery=lambda device: [SimpleNamespace(path=device.path)],
        session_factory=Session, connectors=(lambda _session: driver,))
    assert backend.supports_device(first) and backend.supports_device(second)
    assert len(backend._bound) == 2


def test_native_hid_exposes_report_rate_read_and_write_separately():
    capabilities = HardwareCapabilities(
        report_rate=ReportRateCapabilities(
            readable=True, writable=False, values=(1000, 500, 250, 125)))
    driver = SimpleNamespace(name="G305", capabilities=capabilities,
                             get_report_rate=Mock(return_value=1000),
                             set_report_rate=Mock())
    backend = NativeHidBackend(
        discovery=lambda _device: [SimpleNamespace(path="/dev/fake")],
        session_factory=lambda _path: SimpleNamespace(closed=False, close=lambda: None),
        connectors=(lambda _session: driver,))
    assert backend.supports_polling_rate(G305)
    assert not backend.supports_polling_rate_writes(G305)
    assert backend.get_polling_rates(G305) == [1000, 500, 250, 125]
    assert backend.get_polling_rate(G305) == 1000
    with pytest.raises(HardwareError, match="writes are unsupported"):
        backend.set_polling_rate(G305, 500)
    driver.set_report_rate.assert_not_called()


def test_hardware_apply_skips_nonwritable_report_rate():
    backend = Mock(spec=HardwareBackend)
    backend.supports_dpi.return_value = False
    backend.supports_polling_rate_writes.return_value = False
    cli._apply_hardware(backend, G305, [], 0, 1000)
    backend.set_polling_rate.assert_not_called()


def test_razer_backend_remains_available():
    backend = razer_backend(razer_device())
    assert get_backend(RAZER, [lambda: backend]) is backend
    assert backend.get_device_name(RAZER) == "Razer mouse"
    assert backend.get_dpi(RAZER) == (800, 800)
    backend.set_dpi(RAZER, 1500)
    assert backend._devices[RAZER].dpi == (1500, 1500)


def test_ambiguous_razer_identity_refuses_writes():
    backend = razer_backend(razer_device(), razer_device())
    assert isinstance(get_backend(RAZER, [lambda: backend]), GenericBackend)


def test_generic_capability_defaults():
    backend = GenericBackend()
    assert not backend.supports_dpi(G305)
    assert not backend.supports_dpi_stages(G305)
    assert not backend.supports_dpi_monitoring(G305)
    assert backend.get_dpi_values(G305) == []
    assert backend.get_capabilities(G305).dpi.values is None
    with pytest.raises(HardwareError):
        backend.set_dpi(G305, 800)


def test_openrazer_rejects_unreported_values_and_rates():
    target = razer_device(("dpi", "available_dpi", "poll_rate", "supported_poll_rates"))
    backend = razer_backend(target)
    backend.set_dpi(RAZER, 800)
    assert target.dpi == (800, 0)
    with pytest.raises(HardwareError):
        backend.set_dpi(RAZER, 1500)
    with pytest.raises(HardwareError):
        backend.set_polling_rate(RAZER, 8000)


@pytest.mark.parametrize("unavailable", [False, True])
def test_startup_remaps_despite_hardware_failure(unavailable, caplog):
    backend = Mock(spec=HardwareBackend)
    backend.name = "Test"
    backend.supports_dpi.side_effect = HardwareError("disconnected")
    backend.supports_polling_rate.return_value = True
    backend.supports_polling_rate_writes.return_value = True
    config = {"device": {"event_path": RAZER.path}, "dpi": {"active": 800},
              "polling": {"rate_hz": 1000}, "remap": {"BTN_SIDE": "key:KEY_F13"}}
    with patch.object(cli, "load_config", return_value=config), \
         patch.object(cli, "get_mouse_devices", return_value=[RAZER]), \
         patch.object(cli, "MouseRemapper") as remapper:
        if unavailable:
            with patch.dict(sys.modules, {"openrazer": None, "openrazer.client": None}), \
                 patch("mouse_control.hardware.registry.BACKEND_FACTORIES", (OpenRazerBackend,)):
                assert cli.run_from_config() == 0
        else:
            with patch.object(cli, "get_backend", return_value=backend):
                assert cli.run_from_config() == 0
            backend.set_polling_rate.assert_called_once_with(RAZER, 1000)
        remapper.return_value.run.assert_called_once()
    assert "disconnected" in caplog.text or "OpenRazer" in caplog.text
