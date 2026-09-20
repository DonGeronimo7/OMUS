"""Operation-count and safety acceptance for reusable native protocol proof."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from mouse_control.device_profiles import DeviceProfileStore, result_to_profile
from mouse_control.discovery import MouseDevice
from mouse_control.discovery_engine import DiscoveryEngine
from mouse_control.discovery_models import DeviceNode, PhysicalDevice
from mouse_control.hardware.base import HardwareError
from mouse_control.hardware.native_hid import NativeHidBackend
from mouse_control.hidpp import HidppFeature
from mouse_control.hidpp_driver import Hidpp20Driver
from mouse_control.proof_state import CapabilityStage
from mouse_control.protocol_discovery import Hidpp20Detector, hidpp_capability_proof, hidpp_match
from test_native_hid import FakeSession


@pytest.fixture
def binding():
    session = FakeSession()
    session.path = Path('/dev/hidraw42')
    session.closed = False
    session.close = lambda: setattr(session, 'closed', True)
    driver = Hidpp20Driver(session, 1)
    node = DeviceNode(session.path, None, 'hidraw', 'hidraw', 3, 0x046D, 0x4074,
                      2, descriptor_sha256='descriptor')
    physical = PhysicalDevice('G305', 0x046D, 0x4074, 3, None,
                              hidraw_nodes=[node], model_fingerprint='model')
    mouse = MouseDevice('G305', '/dev/input/event4', vendor=0x046D,
                        product=0x4074, bustype=3)
    return session, driver, node, physical, mouse


def fail(*args, **kwargs):
    raise AssertionError('unexpected discovery, I/O or filesystem access')


def test_bound_exact_proof_never_rediscovers_or_reads_disk(binding):
    session, driver, node, physical, mouse = binding
    backend = NativeHidBackend(discovery=fail, session_factory=fail)
    backend._bound[mouse] = (session, driver)
    backend._bound_descriptors[mouse] = physical.hidraw_nodes[0].descriptor_sha256
    session.calls.clear()
    engine = DiscoveryEngine(
        topology_builder=lambda _: physical, detectors=(SimpleNamespace(detect=fail),),
        probe_factory=fail, profile_store=SimpleNamespace(restore_result=fail, save=fail),
        bound_protocol=lambda p: backend.discovery_protocol(mouse, p))
    result = engine.discover(mouse)
    assert result.capabilities['dpi'].writable
    assert result.protocol.metadata['proof_path'] == 'exact'
    assert not result.capabilities['report_rate'].writable  # live ownership is separate
    assert session.calls == []
    assert not session.closed


def test_cold_native_discovery_skips_raw_probe_and_never_writes(binding, tmp_path):
    session, _, node, physical, mouse = binding
    session.calls.clear()
    detector = Hidpp20Detector(session_factory=lambda _: session,
                              connector=lambda s: Hidpp20Driver(s, 1))
    engine = DiscoveryEngine(topology_builder=lambda _: physical, detectors=(detector,),
                             probe_factory=fail, profile_store=DeviceProfileStore(tmp_path),
                             save_profiles=False)
    result = engine.discover(mouse)
    assert result.capabilities['dpi'].writable
    assert not any(feature == 0x19 and function == 3
                   for _, feature, function, _ in session.calls)
    assert session.closed


@pytest.mark.parametrize('revision, allowed', [(0, True), (1, True), (2, False), (255, False)])
def test_family_reuses_commands_but_checks_feature_revision(binding, revision, allowed):
    session, driver, node, physical, _ = binding
    physical.product_id = 0x9999
    node = replace(node, product_id=physical.product_id)
    physical.hidraw_nodes = [node]
    driver.features[0x2201] = HidppFeature(0x2201, 0x19, 0, revision)
    session.calls.clear()
    match = hidpp_match(physical, node, driver)
    assert match.metadata['proof_path'] == 'family'
    assert match.metadata['capabilities']['dpi'].writable is allowed
    assert session.calls == []


def test_shared_fields_never_promote_and_persistence_is_independent(binding):
    _, driver, node, physical, _ = binding
    cap = hidpp_match(physical, node, driver).metadata['capabilities']['dpi']
    proof = hidpp_capability_proof(driver, cap, routing_unambiguous=True)
    assert proof.stage is CapabilityStage.WRITE_VERIFIED
    assert not proof.persistent_authorized
    unsafe = replace(proof, shared_state_safe=False)
    assert not unsafe.write_authorized
    assert 'shared_state_safe' in unsafe.blockers
    assert not replace(proof, persistence_facts=('save_commit',)).persistent_authorized
    assert not replace(proof, persistence_facts=(
        'save_commit', 'profile_bank', 'power_cycle', 'flash_behavior',
        'persistence_mode', 'wear_limits', 'safe_recovery')).persistent_authorized


@pytest.mark.parametrize('predicate', [
    'capability_identified', 'semantics_known', 'values_bounded', 'packet_known',
    'shared_state_safe', 'confirmation_known', 'failure_known', 'routing_unambiguous',
    'compatible', 'read_proven', 'volatile_operation', 'runtime_policy_satisfied',
])
def test_every_predicate_is_required(binding, predicate):
    _, driver, node, physical, _ = binding
    cap = hidpp_match(physical, node, driver).metadata['capabilities']['dpi']
    proof = hidpp_capability_proof(driver, cap, routing_unambiguous=True)
    assert not replace(proof, **{predicate: False}).write_authorized


def test_cache_is_knowledge_only_and_restart_reads_live_dpi(binding, tmp_path):
    session, driver, node, physical, mouse = binding
    engine = DiscoveryEngine(topology_builder=lambda _: physical,
                             bound_protocol=lambda p: hidpp_match(p, node, driver))
    result = engine.discover(mouse)
    store = DeviceProfileStore(tmp_path)
    store.save(result)
    cached = store.restore_result(physical)[1]
    assert cached.capabilities['dpi'].values == result.capabilities['dpi'].values
    assert not cached.capabilities['dpi'].writable
    session.dpi = 2000  # hardware changed while OMUS was stopped
    backend = NativeHidBackend(discovery=fail)
    backend._bound[mouse] = (session, driver)
    backend._bound_descriptors[mouse] = physical.hidraw_nodes[0].descriptor_sha256
    session.calls.clear()
    assert backend.discovery_protocol(mouse, physical).metadata['capabilities']['dpi'].writable
    assert session.calls == []
    assert backend.get_dpi(mouse) == 2000
    assert len(session.calls) == 1
    payload = result_to_profile(result)
    assert 'current_dpi' not in str(payload)
    assert 'device_index' not in str(payload)


@pytest.mark.parametrize('change', ['protocol', 'descriptor', 'feature', 'identity', 'routing'])
def test_changed_structure_cannot_reuse_disk_authority(binding, tmp_path, change):
    session, driver, node, physical, mouse = binding
    store = DeviceProfileStore(tmp_path)
    engine = DiscoveryEngine(topology_builder=lambda _: physical,
                             bound_protocol=lambda p: hidpp_match(p, node, driver))
    store.save(engine.discover(mouse))
    if change == 'protocol':
        driver.protocol_version = (9, 9)
    elif change == 'feature':
        driver.features[0x2201] = HidppFeature(0x2201, 0x19, 0, 77)
    elif change == 'descriptor':
        physical.hidraw_nodes = [replace(node, descriptor_sha256='changed')]
    elif change == 'identity':
        physical.vendor_id = None
    else:
        physical.ambiguous = True
    cached = store.restore_result(physical)
    assert cached is None or not cached[1].writable
    if change in ('protocol', 'feature', 'identity', 'routing'):
        assert not hidpp_match(physical, node, driver).metadata['capabilities']['dpi'].writable


def test_readback_failure_revokes_receipt_without_extra_transactions(binding):
    session, driver, _, physical, mouse = binding
    backend = NativeHidBackend(discovery=fail)
    backend._bound[mouse] = (session, driver)
    backend._bound_descriptors[mouse] = physical.hidraw_nodes[0].descriptor_sha256
    session.calls.clear()
    assert backend.set_dpi(mouse, 1500).confirmed
    assert len(session.calls) == 2
    session.mismatch = True
    session.calls.clear()
    with pytest.raises(HardwareError, match='verification'):
        backend.set_dpi(mouse, 2000)
    assert len(session.calls) == 2
    match = backend.discovery_protocol(mouse, physical)
    assert not match.metadata['capabilities']['dpi'].writable
    proof = match.metadata['capabilities']['dpi'].evidence[-1].details
    assert 'confirmation_known' in proof['blockers']


@pytest.mark.parametrize('condition', ['closed', 'duplicate', 'ambiguous', 'unbound', 'layout'])
def test_owner_rejects_stale_or_ambiguous_route(binding, condition):
    session, driver, node, physical, mouse = binding
    backend = NativeHidBackend(discovery=fail)
    backend._bound[mouse] = (session, driver)
    backend._bound_descriptors[mouse] = physical.hidraw_nodes[0].descriptor_sha256
    if condition == 'closed': session.closed = True
    elif condition == 'duplicate': physical.hidraw_nodes.append(node)
    elif condition == 'ambiguous': physical.ambiguous = True
    elif condition == 'layout': physical.hidraw_nodes = [replace(node, descriptor_sha256='changed')]
    else: backend._bound.clear()
    session.calls.clear()
    assert backend.discovery_protocol(mouse, physical) is None
    assert session.calls == []


def test_guided_inspection_can_lazily_obtain_known_device_descriptors(binding, tmp_path):
    _, driver, node, physical, mouse = binding
    probes = []
    descriptor = bytes.fromhex('05 09 09 01 15 00 25 01 75 01 95 01 81 02')
    def probe(candidate):
        probes.append(candidate)
        return SimpleNamespace(read_descriptor=lambda: descriptor)
    engine = DiscoveryEngine(topology_builder=lambda _: physical, probe_factory=probe,
                             profile_store=DeviceProfileStore(tmp_path),
                             bound_protocol=lambda p: hidpp_match(p, node, driver))
    assert engine.discover(mouse).writable
    assert probes == []
    assert engine.descriptors[node].reports
    assert engine.descriptors[node].reports
    assert probes == [node]


def test_razer_owner_reuses_exact_command_knowledge_without_storage_promotion(tmp_path):
    from mouse_control.hardware.native_razer import NativeRazerBackend
    from test_native_razer import StatefulSession, hid, viper_v3_pro_wireless
    device = viper_v3_pro_wireless()
    backend = NativeRazerBackend(discovery=lambda _: [hid('/dev/hidraw7')],
                                 session_factory=StatefulSession)
    assert backend.supports_device(device)
    session, _ = backend._bound[device]
    session.query = fail
    session.path = Path('/dev/hidraw7')
    node = DeviceNode(session.path, None, 'hidraw', 'hidraw', 3, device.vendor,
                      device.product, 2, descriptor_sha256=backend._bound_descriptors[device])
    physical = PhysicalDevice(device.name, device.vendor, device.product, 3, None,
                              hidraw_nodes=[node], model_fingerprint='razer-model')
    engine = DiscoveryEngine(topology_builder=lambda _: physical, probe_factory=fail,
        bound_protocol=lambda p: backend.discovery_protocol(device, p),
        profile_store=DeviceProfileStore(tmp_path))
    result = engine.discover(device)
    assert result.protocol.name == 'razer-rpc90'
    cap = result.capabilities['dpi']
    assert cap.readable and not cap.writable
    assert cap.evidence[-1].details['blockers'] == ['volatile_operation']
    assert not cap.evidence[-1].details['persistent_authorized']
    session.closed = True
    assert backend.discovery_protocol(device, physical) is None


def test_supervisor_and_discovery_share_the_existing_owner(binding, tmp_path):
    from mouse_control.hardware.discovery_backend import DiscoveryBackend
    from mouse_control.hardware.supervisor import HardwareSupervisor
    session, driver, node, physical, mouse = binding
    native = NativeHidBackend(discovery=fail)
    native._bound[mouse] = (session, driver)
    native._bound_descriptors[mouse] = node.descriptor_sha256
    discovery = DiscoveryBackend(profile_directory=tmp_path, protocol_factories=())
    discovery._protocol_backend = native
    supervisor = HardwareSupervisor(discovery, mouse, fail)
    session.calls.clear()
    engine = DiscoveryEngine(topology_builder=lambda _: physical,
        bound_protocol=lambda p: supervisor.discovery_protocol(mouse, p), probe_factory=fail)
    assert engine.discover(mouse).capabilities['dpi'].writable
    assert session.calls == []
    supervisor.close()
    with pytest.raises(HardwareError, match='closed'):
        supervisor.discovery_protocol(mouse, physical)


def test_driver_read_only_capability_is_not_promoted(binding):
    _, driver, node, physical, _ = binding
    driver._dpi_capabilities = replace(driver._dpi_capabilities, writable=False)
    cap = hidpp_match(physical, node, driver).metadata['capabilities']['dpi']
    assert cap.readable and not cap.writable
    assert 'runtime_policy_satisfied' in cap.evidence[-1].details['blockers']


def test_refused_owner_never_opens_competing_reader(binding):
    _, _, _, physical, mouse = binding
    engine = DiscoveryEngine(topology_builder=lambda _: physical,
        bound_protocol=lambda _: None, detectors=(SimpleNamespace(detect=fail),),
        probe_factory=fail, profile_store=SimpleNamespace(restore_result=fail, save=fail))
    result = engine.discover(mouse, force=True)
    assert not result.writable and not engine.bound_protocol_used
    assert result.observations[-1].code == 'owner-proof-unavailable'


def test_automatic_setup_reuses_owner_without_backend_reselection(binding, tmp_path):
    from mouse_control.guided_discovery import run_automatic_discovery
    from test_setup_tui import controller
    session, driver, node, physical, mouse = binding
    backend = NativeHidBackend(discovery=fail)
    backend._bound[mouse] = (session, driver)
    backend._bound_descriptors[mouse] = node.descriptor_sha256
    session.calls.clear()
    outcome = run_automatic_discovery(mouse, protocol_owner=backend,
        engine_factory=lambda **kwargs: DiscoveryEngine(
            topology_builder=lambda _: physical, profile_store=DeviceProfileStore(tmp_path),
            probe_factory=fail, **kwargs))
    assert outcome.bound_protocol_used
    assert session.calls == []
    app, _ = controller()
    current_owner = app.backend
    current_owner.close = fail
    app._backend_factory = fail
    app._refresh_observed_profile = lambda: None
    app.apply_automatic_discovery(outcome)
    assert app.backend is current_owner
