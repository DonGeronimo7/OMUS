# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import os
import subprocess
import sys
from types import SimpleNamespace

from mouse_control.config import load_config
from mouse_control.device_profiles import DeviceProfileStore
from mouse_control.discovery import MouseDevice
from mouse_control.discovery_engine import DiscoveryEngine
from mouse_control.discovery_models import DeviceNode, DiscoveryResult, PhysicalDevice
from mouse_control.performance import PerformanceRecorder, measure, milestone


def _node(path: str) -> DeviceNode:
    return DeviceNode(
        Path(path), Path("/sys/fake"), "hidraw", "hidraw", 3, 1, 2, 0,
        descriptor_sha256="descriptor", parent_key="physical",
    )


def _physical(node: DeviceNode | None = None) -> PhysicalDevice:
    return PhysicalDevice(
        "Mouse", 1, 2, 3, None, [], [] if node is None else [node],
        "model", "instance",
    )


def test_recorder_is_opt_in_and_reports_repeatable_phase_statistics():
    ticks = iter((0, 10, 25, 40, 70, 90))
    recorder = PerformanceRecorder(clock=lambda: next(ticks))

    with measure("inactive"):
        pass
    with recorder.activate():
        with measure("phase"):
            pass
        with measure("phase"):
            pass
        milestone("ready")

    assert recorder.samples("inactive") == ()
    assert recorder.samples("phase") == (15, 30)
    assert recorder.samples("ready") == (90,)
    phase = next(item for item in recorder.summaries() if item.name == "phase")
    assert (phase.count, phase.minimum_ns, phase.median_ns, phase.maximum_ns) == (
        2, 15, 22, 30,
    )


def test_known_device_and_rediscover_emit_distinct_performance_phases(tmp_path):
    node = _node("/dev/hidraw1")
    physical = _physical(node)
    store = DeviceProfileStore(tmp_path)
    store.save(DiscoveryResult(physical, None, {}))
    probe = SimpleNamespace(
        read_descriptor=lambda: bytes.fromhex(
            "05 09 09 01 15 00 25 01 75 01 95 01 81 02"
        )
    )
    engine = DiscoveryEngine(
        topology_builder=lambda _mouse: physical,
        detectors=(),
        probe_factory=lambda _node: probe,
        profile_store=store,
        save_profiles=False,
    )
    mouse = MouseDevice("Mouse", "/dev/input/event1", vendor=1, product=2, bustype=3)

    known = PerformanceRecorder()
    with known.activate():
        assert engine.restore_known_device(mouse) is not None
    assert known.samples("topology_construction")
    assert known.samples("persisted_evidence_lookup")
    assert known.samples("runtime_ready")
    assert not known.samples("descriptor_acquisition")

    rediscover = PerformanceRecorder()
    with rediscover.activate():
        result = engine.discover(mouse, force=True)
    assert result is not None
    for phase in (
        "topology_construction",
        "descriptor_acquisition",
        "descriptor_parsing",
        "protocol_binding",
        "hardware_validation",
        "runtime_ready",
    ):
        assert rediscover.samples(phase), phase
    assert not rediscover.samples("persisted_evidence_lookup")


def test_config_load_reports_only_when_instrumentation_is_active(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[device]\nevent_path = '/dev/input/event1'\n", encoding="utf-8")
    recorder = PerformanceRecorder()
    with recorder.activate():
        assert load_config(path)["device"]["event_path"] == "/dev/input/event1"
    assert len(recorder.samples("config_load")) == 1


def test_cold_help_does_not_import_runtime_research_or_updater_subsystems():
    script = """
import contextlib
import io
import sys
from mouse_control import app
try:
    with contextlib.redirect_stdout(io.StringIO()):
        app.main([\"--help\"])
except SystemExit as exc:
    assert exc.code == 0
for name in (
    \"mouse_control.hardware.discovery_backend\",
    \"mouse_control.sensor_calibration\",
    \"mouse_control.updater\",
    \"mouse_control.calibrated_discovery\",
):
    assert name not in sys.modules, name
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
