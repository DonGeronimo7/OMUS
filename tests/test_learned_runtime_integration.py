from __future__ import annotations

import json
from pathlib import Path
import queue
import threading
import time
from types import SimpleNamespace

from mouse_control.discovery import MouseDevice
from mouse_control.discovery_models import DeviceNode, PhysicalDevice
from mouse_control.hardware.discovery_backend import DiscoveryBackend
from mouse_control.hardware.supervisor import HardwareSupervisor
from mouse_control.learned_hid_session import LearnedHidSession
from mouse_control.learned_operations import (
    LearnedOperationState,
    StableDeviceIdentity,
    StableInterfaceIdentity,
    operation_from_grammar,
    promote_operation,
)
from mouse_control.learned_polling import LearnedPollingOperation
from mouse_control.polling_replay import PacketPattern, ReplayStep
from mouse_control.protocol_grammar import SemanticBehavior
from mouse_control.transaction_inference import (
    demonstration_from_trace,
    infer_transaction_grammar,
)


def node(path="/dev/hidraw-test"):
    return DeviceNode(
        path=Path(path),
        sysfs_path=None,
        subsystem="hidraw",
        node_type="hidraw",
        bus=3,
        vendor_id=0x046D,
        product_id=0x4074,
        interface_number=2,
        descriptor_sha256="descriptor",
    )


def physical(path="/dev/hidraw-test"):
    return PhysicalDevice(
        name="G305",
        vendor_id=0x046D,
        product_id=0x4074,
        bus=3,
        parent_path=None,
        hidraw_nodes=[node(path)],
        model_fingerprint="model",
        instance_fingerprint="instance",
    )


def device():
    return MouseDevice(
        "G305",
        "/dev/input/test",
        vendor=0x046D,
        product=0x4074,
        bustype=3,
    )


def dpi_events(value):
    hi, lo = value.to_bytes(2, "big")
    return (
        SimpleNamespace(
            direction="tx",
            data=bytes.fromhex("11 01 1a 3a 00")
            + bytes((hi, lo))
            + bytes(13),
        ),
        SimpleNamespace(
            direction="rx",
            data=bytes.fromhex("11 01 1a 3a") + bytes(16),
        ),
        SimpleNamespace(
            direction="tx",
            data=bytes.fromhex("11 01 1a 2a") + bytes(16),
        ),
        SimpleNamespace(
            direction="rx",
            data=bytes.fromhex("11 01 1a 2a 00")
            + bytes((hi, lo))
            + bytes.fromhex("03 20")
            + bytes(11),
        ),
    )


def dpi_operation():
    values = (800, 1500, 2000, 2500, 3000)
    grammar = infer_transaction_grammar(
        tuple(
            demonstration_from_trace(value, dpi_events(value))
            for value in values
        )
    )
    demonstrated = operation_from_grammar(
        grammar,
        identity=StableDeviceIdentity(
            3, 0x046D, 0x4074, "model", "instance"
        ),
        interface=StableInterfaceIdentity(
            3, 0x046D, 0x4074, 2, "descriptor"
        ),
    )
    return promote_operation(
        demonstrated,
        target_value=1500,
        measured_value=1500,
        deviation_fraction=0.0,
        calibration_confidence="high",
        raw_readback_value=1500,
    )


def packet_pattern(values):
    return PacketPattern(tuple(values))


def polling_operation():
    write = ReplayStep(
        request=packet_pattern((0x10, 0x03, None)),
        response=packet_pattern((0x20, 0x03)),
        request_semantic_offset=2,
    )
    read = ReplayStep(
        request=packet_pattern((0x10, 0x04)),
        response=packet_pattern((0x20, 0x04, None)),
        response_semantic_offset=2,
    )
    return LearnedPollingOperation(
        behavior=SemanticBehavior.REPORT_RATE_HZ,
        state=LearnedOperationState.PROVEN,
        identity=StableDeviceIdentity(
            3, 0x046D, 0x4074, "model", "instance"
        ),
        interface=StableInterfaceIdentity(
            3, 0x046D, 0x4074, 2, "descriptor"
        ),
        demonstrated_rates=(125, 250, 500, 1000),
        raw_to_hz={1: 1000, 2: 500, 4: 250, 8: 125},
        control_query_request=packet_pattern((0x10, 0x01)),
        control_query_response=packet_pattern((0x20, None)),
        control_state_offset=1,
        onboard_state_raw=1,
        host_state_raw=2,
        onboard_steps=(
            ReplayStep(
                request=packet_pattern((0x10, 0x02)),
                response=packet_pattern((0x20, 0x02)),
            ),
            ReplayStep(
                request=packet_pattern((0x10, 0x01)),
                response=packet_pattern((0x20, 0x02)),
            ),
            write,
            read,
        ),
        host_steps=(write, read),
        promotion_evidence={"unit": True},
    )


class StaticStore:
    def __init__(self, item):
        self.item = item

    def find_for_physical(self, _physical, **_kwargs):
        return self.item


def calibrated_profile():
    return {
        "schema_version": 1,
        "profile_kind": "calibrated-read-only",
        "identity": {"vendor_id": 0x046D, "product_id": 0x4074, "bus": 3},
        "fingerprints": {"model": "model", "instance": "instance"},
        "dpi_cycle": {
            "configured_order": [800, 1500, 2000, 2500, 3000],
            "states": [],
            "wrap_confirmed": True,
            "semantic_evidence": "physically-calibrated",
        },
        "action_reports": [],
        "raw_mappings": [
            {
                "report": {
                    "report_type": "input",
                    "bus": 3,
                    "vendor_id": 0x046D,
                    "product_id": 0x4074,
                    "interface_number": 2,
                    "descriptor_sha256": "descriptor",
                    "report_length": 5,
                    "report_id": 0x02,
                },
                "offset": 4,
                "descriptor_roles": ["vendor"],
                "raw_to_configured_dpi": {
                    "0": 800,
                    "1": 1500,
                    "2": 2000,
                    "3": 2500,
                    "4": 3000,
                },
                "raw_to_measured_cpi": {
                    "0": 800,
                    "1": 1500,
                    "2": 2000,
                    "3": 2500,
                    "4": 3000,
                },
                "observations": 5,
                "confidence": "correlated",
                "write_authorized": False,
            }
        ],
        "write_authorized": False,
    }


class CombinedIo:
    def __init__(self, _path):
        self.pending = queue.Queue()
        self.closed = False
        self.dpi = 800
        self.mode = 1
        self.rate_raw = 1
        self.writes = []

    def write(self, data):
        packet = bytes(data)
        self.writes.append(packet)
        if len(packet) == 20 and packet[:4] == bytes.fromhex("11 01 1a 3a"):
            self.dpi = int.from_bytes(packet[5:7], "big")
            stage = {
                800: 0,
                1500: 1,
                2000: 2,
                2500: 3,
                3000: 4,
            }[self.dpi]
            self.pending.put(bytes((0x02, 0, 0, 0, stage)))
            self.pending.put(bytes.fromhex("11 01 1a 3a") + bytes(16))
        elif len(packet) == 20 and packet[:4] == bytes.fromhex("11 01 1a 2a"):
            hi, lo = self.dpi.to_bytes(2, "big")
            self.pending.put(
                bytes.fromhex("11 01 1a 2a 00")
                + bytes((hi, lo))
                + bytes.fromhex("03 20")
                + bytes(11)
            )
        elif packet == b"\x10\x01":
            self.pending.put(bytes((0x20, self.mode)))
        elif packet == b"\x10\x02":
            self.mode = 2
            self.pending.put(b"\x20\x02")
        elif packet[:2] == b"\x10\x03":
            self.rate_raw = packet[2]
            self.pending.put(b"\x20\x03")
        elif packet == b"\x10\x04":
            self.pending.put(bytes((0x20, 0x04, self.rate_raw)))
        else:
            raise AssertionError(f"unexpected request {packet!r}")

    def read(self, timeout):
        try:
            return self.pending.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        if not self.closed:
            self.closed = True
            self.pending.put(b"")


def backend(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "g305.json").write_text(
        json.dumps(calibrated_profile()),
        encoding="utf-8",
    )
    io = CombinedIo(Path("/dev/null"))
    sessions = []

    def session_factory(path):
        session = LearnedHidSession(
            path,
            io_factory=lambda _path: io,
            timeout=0.2,
        )
        sessions.append(session)
        return session

    result = DiscoveryBackend(
        profile_directory=profile_dir,
        learned_operation_store=StaticStore(
            (Path("dpi.json"), dpi_operation())
        ),
        learned_polling_store=StaticStore(
            (Path("polling.json"), polling_operation())
        ),
        topology_builder=lambda _device: physical(),
        protocol_factories=(),
        learned_session_factory=session_factory,
    )
    return result, io, sessions


def test_shared_session_keeps_dpi_event_and_write_on_one_reader(tmp_path):
    backend_obj, _io, sessions = backend(tmp_path)
    mouse = device()
    assert backend_obj.supports_device(mouse)
    assert backend_obj.supports_dpi_events(mouse)

    shutdown = threading.Event()
    ready = threading.Event()
    seen = []
    thread = threading.Thread(
        target=lambda: backend_obj.watch_dpi_events(
            mouse, seen.append, shutdown, ready.set
        ),
        daemon=True,
    )
    thread.start()
    assert ready.wait(0.5)

    state = backend_obj.set_dpi(mouse, 1500)
    assert state is not None
    assert state.display_value == 1500

    deadline = time.monotonic() + 0.5
    while not seen and time.monotonic() < deadline:
        time.sleep(0.005)
    assert [item.display_value for item in seen] == [1500]
    assert len(sessions) == 1

    shutdown.set()
    thread.join(0.5)
    backend_obj.close()


def test_learned_polling_obeys_takeover_policy_and_reuses_session(tmp_path):
    backend_obj, io, sessions = backend(tmp_path)
    mouse = device()
    assert backend_obj.supports_device(mouse)

    assert backend_obj.supports_polling_rate(mouse)
    assert backend_obj.supports_polling_rate_writes(mouse)
    assert not backend_obj.supports_polling_rate_writes_without_takeover(mouse)
    assert backend_obj.get_polling_rate(mouse) is None

    backend_obj.set_polling_rate(mouse, 500)
    assert io.mode == 2
    assert backend_obj.get_polling_rate(mouse) == 500
    assert backend_obj.supports_polling_rate_writes_without_takeover(mouse)

    backend_obj.set_polling_rate(mouse, 250)
    assert backend_obj.get_polling_rate(mouse) == 250
    assert len(sessions) == 1
    backend_obj.close()


def test_learned_runtime_is_a_preferred_supervisor_binding(tmp_path):
    backend_obj, _io, _sessions = backend(tmp_path)
    mouse = device()
    assert backend_obj.supports_device(mouse)
    supervisor = HardwareSupervisor(
        backend_obj,
        mouse,
        lambda _selected: backend_obj,
        discovery_pending=True,
    )
    try:
        assert supervisor.discovery_pending is False
    finally:
        supervisor.close()

def test_learned_cycle_trigger_can_reenter_shared_session_without_deadlock(tmp_path):
    from mouse_control.learned_actions import LearnedActionTrigger
    from mouse_control.notifications import DpiEventMonitor
    from mouse_control.remapper import DpiCycler

    profile_dir = tmp_path / "trigger-profiles"
    profile_dir.mkdir()
    (profile_dir / "g305.json").write_text(
        json.dumps(calibrated_profile()),
        encoding="utf-8",
    )

    io = CombinedIo(Path("/dev/null"))
    sessions = []

    def session_factory(path):
        session = LearnedHidSession(
            path,
            io_factory=lambda _path: io,
            timeout=0.2,
        )
        sessions.append(session)
        return session

    trigger = LearnedActionTrigger(
        behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        identity=StableDeviceIdentity(
            3, 0x046D, 0x4074, "model", "instance"
        ),
        interface=StableInterfaceIdentity(
            3, 0x046D, 0x4074, 2, "descriptor"
        ),
        press_pattern=packet_pattern(
            tuple(bytes.fromhex("02 20 00 00 00 00 00 00 00"))
        ),
        release_pattern=packet_pattern(
            tuple(bytes.fromhex("02 00 00 00 00 00 00 00 00"))
        ),
        observation_count=8,
    )

    backend_obj = DiscoveryBackend(
        profile_directory=profile_dir,
        learned_operation_store=StaticStore(
            (Path("dpi.json"), dpi_operation())
        ),
        learned_polling_store=StaticStore(
            (Path("polling.json"), polling_operation())
        ),
        learned_action_store=StaticStore(
            (Path("trigger.json"), trigger)
        ),
        topology_builder=lambda _device: physical(),
        protocol_factories=(),
        learned_session_factory=session_factory,
    )
    mouse = device()
    assert backend_obj.supports_device(mouse)
    assert backend_obj.supports_dpi_cycle_trigger(mouse)
    assert backend_obj.supports_dpi_events(mouse)

    shutdown = threading.Event()
    ready = threading.Event()
    cycler = DpiCycler(
        backend_obj,
        mouse,
        [800, 1500],
        800,
        notifications_enabled=False,
    )
    monitor = DpiEventMonitor(
        backend_obj,
        mouse,
        [800, 1500],
        800,
        shutdown_event=shutdown,
        dpi_cycler=cycler,
    )
    watcher = threading.Thread(
        target=lambda: backend_obj.watch_dpi_events(
            mouse,
            monitor.handle_state,
            shutdown,
            ready.set,
        ),
        daemon=True,
    )
    watcher.start()
    assert ready.wait(0.5)

    io.pending.put(bytes.fromhex("02 20 00 00 00 00 00 00 00"))

    deadline = time.monotonic() + 1.0
    while cycler.current_dpi != 1500 and time.monotonic() < deadline:
        time.sleep(0.005)

    assert cycler.current_dpi == 1500
    assert io.dpi == 1500
    assert backend_obj.get_dpi(mouse) == 1500
    assert len(sessions) == 1

    io.pending.put(bytes.fromhex("02 00 00 00 00 00 00 00 00"))
    shutdown.set()
    watcher.join(0.5)
    backend_obj.close()
