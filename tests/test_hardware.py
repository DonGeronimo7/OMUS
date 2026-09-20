"""Hardware tests use no daemon, input device, or real writes."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from mouse_control import cli
from mouse_control.discovery import MouseDevice
from mouse_control.hardware import HardwareBackend, HardwareError, get_backend
from mouse_control.hardware.capabilities import (HardwareCapabilities,
                                                 ReportRateCapabilities)
from mouse_control.hardware.discovery_backend import DiscoveryBackend
from mouse_control.hardware.generic import GenericBackend
from mouse_control.hardware.native_hid import NativeHidBackend

G305 = MouseDevice("G305", "/dev/input/test", vendor=0x046d, product=0x4074,
                   bustype=3)
RAZER = MouseDevice("Razer", "/dev/input/test", vendor=0x1532, product=0x00C1)


def test_registry_always_returns_discovery_and_binds_first_proven_adapter():
    native, later = Mock(spec=HardwareBackend), Mock()
    native.supports_device.return_value = True
    backend = get_backend(G305, [lambda: native, later])
    assert isinstance(backend, DiscoveryBackend)
    assert backend._protocol_backend is native
    later.assert_not_called()

    unknown = MouseDevice("unknown", "/test", vendor=1, product=2)
    fallback = get_backend(unknown, [NativeHidBackend])
    assert isinstance(fallback, DiscoveryBackend)
    assert fallback._protocol_backend is None


def test_transient_adapter_enumeration_failure_falls_back_without_retry_log_spam(caplog):
    backend = Mock(spec=HardwareBackend)
    backend.supports_device.side_effect = OSError("hidraw not ready")
    assert isinstance(get_backend(G305, [lambda: backend]), DiscoveryBackend)
    assert caplog.text.count("Hardware protocol adapter discovery failed") == 1
    caplog.clear()
    assert isinstance(get_backend(G305, [lambda: backend], log_failures=False), DiscoveryBackend)
    assert "Hardware protocol adapter discovery failed" not in caplog.text


def test_discovery_closes_rejected_and_failed_protocol_adapters():
    rejected = Mock(spec=HardwareBackend)
    rejected.supports_device.return_value = False
    failed = Mock(spec=HardwareBackend)
    failed.supports_device.side_effect = HardwareError("probe failed")
    assert isinstance(get_backend(G305, [lambda: rejected, lambda: failed]), DiscoveryBackend)
    rejected.close.assert_called_once()
    failed.close.assert_called_once()


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


def test_native_hid_exposes_report_rate_read_and_validated_transition():
    driver, _state = polling_driver(mode=1)
    backend = native_backend_with_driver(driver)
    assert backend.supports_polling_rate(G305)
    assert backend.supports_polling_rate_writes(G305)
    assert backend.get_polling_rates(G305) == [1000, 500, 250, 125]
    assert backend.get_polling_rate(G305) == 500
    backend.set_polling_rate(G305, 500)
    driver.set_control_mode.assert_called_once_with(2)
    driver.set_report_rate.assert_called_once_with(500)


def native_backend_with_driver(driver):
    return NativeHidBackend(
        discovery=lambda _device: [SimpleNamespace(path="/dev/fake")],
        session_factory=lambda _path: SimpleNamespace(closed=False, close=lambda: None),
        connectors=(lambda _session: driver,))


def polling_driver(*, mode=1):
    state = {"mode": mode}
    caps = HardwareCapabilities(report_rate=ReportRateCapabilities(
        readable=True, writable=True, values=(1000, 500, 250, 125)))
    driver = SimpleNamespace(name="G305", capabilities=caps,
                             get_report_rate=Mock(return_value=500),
                             set_report_rate=Mock())
    driver.get_control_mode = Mock(side_effect=lambda: state["mode"])
    driver.set_control_mode = Mock(side_effect=lambda value: state.update(mode=value))
    return driver, state


def test_polling_transaction_already_host_does_not_change_mode():
    driver, _state = polling_driver(mode=2)
    native_backend_with_driver(driver).set_polling_rate(G305, 250)
    driver.set_control_mode.assert_not_called()
    driver.set_report_rate.assert_called_once_with(250)


def test_polling_transaction_refuses_unknown_mouse_onboard_transition():
    unknown = MouseDevice("Other Logitech", "/dev/input/test", vendor=0x046d,
                          product=0x4080, bustype=3)
    driver, _state = polling_driver(mode=1)
    backend = native_backend_with_driver(driver)
    assert not backend.supports_polling_rate_writes(unknown)
    with pytest.raises(HardwareError, match="not validated"):
        backend.set_polling_rate(unknown, 500)
    driver.set_control_mode.assert_not_called()
    driver.set_report_rate.assert_not_called()


def test_unknown_mouse_already_in_host_mode_may_use_report_rate():
    unknown = MouseDevice("Other Logitech", "/dev/input/test", vendor=0x046d,
                          product=0x4080, bustype=3)
    driver, _state = polling_driver(mode=2)
    backend = native_backend_with_driver(driver)
    assert backend.supports_polling_rate_writes(unknown)
    backend.set_polling_rate(unknown, 500)
    driver.set_control_mode.assert_not_called()
    driver.set_report_rate.assert_called_once_with(500)


def test_polling_transaction_rejects_unadvertised_rate_before_mode_change():
    driver, _state = polling_driver(mode=1)
    with pytest.raises(HardwareError, match="unsupported polling rate"):
        native_backend_with_driver(driver).set_polling_rate(G305, 2000)
    driver.get_control_mode.assert_not_called()
    driver.set_control_mode.assert_not_called()


@pytest.mark.parametrize("rate_failure", [HardwareError("write failed"),
                                           RuntimeError("write failed")])
def test_polling_transaction_rolls_back_mode_after_rate_failure(rate_failure):
    driver, state = polling_driver(mode=1)
    driver.set_report_rate.side_effect = rate_failure
    with pytest.raises((HardwareError, RuntimeError), match="write failed"):
        native_backend_with_driver(driver).set_polling_rate(G305, 500)
    assert state["mode"] == 1
    assert [call.args[0] for call in driver.set_control_mode.call_args_list] == [2, 1]


def test_polling_transaction_reports_rollback_failure():
    driver, state = polling_driver(mode=1)
    driver.set_report_rate.side_effect = HardwareError("write failed")
    def set_mode(value):
        if value == 1:
            raise HardwareError("rollback failed")
        state["mode"] = value
    driver.set_control_mode.side_effect = set_mode
    with pytest.raises(HardwareError, match="additionally failed.*rollback failed"):
        native_backend_with_driver(driver).set_polling_rate(G305, 500)


def test_polling_transaction_attempts_rollback_after_mode_set_failure():
    driver, state = polling_driver(mode=1)
    calls = []
    def set_mode(value):
        calls.append(value)
        if value == 2:
            raise HardwareError("mode set failed")
        state["mode"] = value
    driver.set_control_mode.side_effect = set_mode
    with pytest.raises(HardwareError, match="mode set failed"):
        native_backend_with_driver(driver).set_polling_rate(G305, 500)
    assert calls == [2, 1]
    assert state["mode"] == 1


def test_polling_transaction_rolls_back_mode_on_host_readback_mismatch():
    driver, state = polling_driver(mode=1)
    readings = iter((1, 1, 1))
    driver.get_control_mode.side_effect = lambda: next(readings)
    with pytest.raises(HardwareError, match="Host mode verification failed"):
        native_backend_with_driver(driver).set_polling_rate(G305, 500)
    assert [call.args[0] for call in driver.set_control_mode.call_args_list] == [2, 1]
    assert state["mode"] == 1


def test_successful_polling_transaction_remains_in_host_mode():
    driver, state = polling_driver(mode=1)
    native_backend_with_driver(driver).set_polling_rate(G305, 125)
    assert state["mode"] == 2
    assert [call.args[0] for call in driver.set_control_mode.call_args_list] == [2]


def test_hardware_apply_skips_nonwritable_report_rate():
    backend = Mock(spec=HardwareBackend)
    backend.supports_dpi.return_value = False
    backend.supports_polling_rate_writes.return_value = False
    cli._apply_hardware(backend, G305, [], 0, 1000)
    backend.set_polling_rate.assert_not_called()


def test_runtime_device_resolution_rejects_reused_path_and_ambiguity():
    configured = MouseDevice("G305", "/dev/input/event5", vendor=0x046d,
                             product=0x4074, bustype=3)
    wrong = MouseDevice("Other", configured.path, vendor=0x1234,
                        product=0x5678, bustype=3)
    one = MouseDevice("G305", "/dev/input/event8", vendor=0x046d,
                      product=0x4074, bustype=3)
    two = MouseDevice("G305", "/dev/input/event9", vendor=0x046d,
                      product=0x4074, bustype=3)
    with patch.object(cli, "get_mouse_devices", return_value=[wrong, one]):
        assert cli._resolve_runtime_device(configured) == one
    with patch.object(cli, "get_mouse_devices", return_value=[wrong, one, two]):
        assert cli._resolve_runtime_device(configured) == configured


def test_generic_compatibility_alias_is_discovery():
    backend = GenericBackend()
    assert isinstance(backend, DiscoveryBackend)
    assert not backend.supports_dpi(G305)
    assert not backend.supports_dpi_stages(G305)
    assert not backend.supports_dpi_monitoring(G305)
    assert backend.get_dpi_values(G305) == []
    assert backend.get_capabilities(G305).dpi.values is None
    with pytest.raises(HardwareError):
        backend.set_dpi(G305, 800)


def test_startup_remaps_despite_hardware_failure(caplog):
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
        with patch.object(cli, "get_backend", return_value=backend):
            assert cli.run_from_config() == 0
        backend.set_polling_rate.assert_called_once_with(RAZER, 1000)
        remapper.return_value.run.assert_called_once()
    backend.set_dpi.assert_not_called()
    assert "Could not reconcile Test polling state" in caplog.text
