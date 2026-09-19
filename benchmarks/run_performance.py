#!/usr/bin/env python3
"""Small repeatable performance suite for Mouse Control's representative paths."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import gc
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

from mouse_control.config import load_config
from mouse_control.device_profiles import DeviceProfileStore
from mouse_control.device_topology import build_device_graph
from mouse_control.discovery import MouseDevice
from mouse_control.discovery_engine import DiscoveryEngine
from mouse_control.discovery_models import DeviceNode, DiscoveryResult, PhysicalDevice
from mouse_control.hardware import DesiredHardwareState, HardwareBackend, HardwareSupervisor
from mouse_control.hardware.capabilities import DpiState
from mouse_control.hid_descriptor import parse_report_descriptor
from mouse_control.hid_report import decode_input_report
from mouse_control.performance import PerformanceRecorder
from mouse_control.setup_flow import SetupChoices
from mouse_control.setup_tui import SetupController


ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = bytes.fromhex(
    "05 01 09 02 a1 01 09 01 a1 00 05 09 19 01 29 05 15 00 25 01 "
    "95 05 75 01 81 02 95 01 75 03 81 01 05 01 09 30 09 31 15 81 "
    "25 7f 75 08 95 02 81 06 c0 c0"
)
REPORT = bytes((0b00001, 4, 252))


@dataclass(frozen=True, slots=True)
class Benchmark:
    name: str
    rounds: int
    median_ns: int
    minimum_ns: int
    p95_ns: int
    maximum_ns: int


@dataclass(frozen=True, slots=True)
class MemoryStability:
    name: str
    cycles: int
    retained_bytes: int
    peak_growth_bytes: int


def _measure(name: str, operation, rounds: int, warmups: int = 5) -> Benchmark:
    for _ in range(warmups):
        operation()
    values = []
    gc.disable()
    try:
        for _ in range(rounds):
            started = time.perf_counter_ns()
            operation()
            values.append(time.perf_counter_ns() - started)
    finally:
        gc.enable()
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, max(0, (95 * len(ordered) + 99) // 100 - 1))
    return Benchmark(
        name, rounds, int(statistics.median(values)), min(values),
        ordered[p95_index], max(values),
    )


def _measure_memory(name: str, operation, cycles: int, warmups: int = 25) -> MemoryStability:
    for _ in range(warmups):
        operation()
    gc.collect()
    tracemalloc.start()
    before, _ = tracemalloc.get_traced_memory()
    for _ in range(cycles):
        operation()
    gc.collect()
    after, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return MemoryStability(name, cycles, after - before, max(0, peak - before))


def _subprocess(command: str) -> None:
    subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _node(path: str, node_type: str, interface: int) -> DeviceNode:
    return DeviceNode(
        Path(path), Path(f"/sys/fake/{interface}"), node_type, node_type,
        3, 0x046D, 0x4074, interface, "G305", "usb-bench", "instance",
        f"descriptor-{interface}", "physical",
    )


class _Probe:
    def read_descriptor(self) -> bytes:
        return DESCRIPTOR

    def snapshot_feature_reports(self, _reports):
        return {}


class _Backend(HardwareBackend):
    name = "Benchmark backend"

    def __init__(self) -> None:
        self.dpi = 800
        self.closed = False

    def supports_device(self, _device) -> bool:
        return True

    def supports_dpi(self, _device) -> bool:
        return True

    def get_dpi(self, _device):
        return self.dpi

    def set_dpi(self, _device, dpi: int):
        self.dpi = dpi
        return DpiState(dpi, confirmed=True)

    def close(self) -> None:
        self.closed = True


class _SetupBackend(_Backend):
    protocol_adapter_name = "Benchmark"
    has_proven_learned_adapter = False

    def get_dpi_values(self, _device):
        return [800, 1600]

    def supports_polling_rate(self, _device) -> bool:
        return False

    def supports_polling_rate_writes(self, _device) -> bool:
        return False

    def supports_dpi_events(self, _device) -> bool:
        return False


def _choices(_existing) -> SetupChoices:
    return SetupChoices(stages=[800, 1600], active_dpi=800)


def run(rounds: int) -> dict[str, object]:
    evdev = _node("/dev/input/event1", "evdev", 0)
    hidraw = [_node(f"/dev/hidraw{index}", "hidraw", index) for index in range(3)]
    physical = PhysicalDevice(
        "G305", 0x046D, 0x4074, 3, None, [evdev], hidraw,
        "benchmark-model", "benchmark-instance",
    )
    mouse = MouseDevice(
        "G305", str(evdev.path), "usb-bench", 0x046D, 0x4074, 3
    )
    descriptor = parse_report_descriptor(DESCRIPTOR)

    with tempfile.TemporaryDirectory(prefix="mouse-control-benchmark-") as directory:
        temp = Path(directory)
        config_path = temp / "config.toml"
        config_path.write_text(
            "[device]\nevent_path='/dev/input/event1'\n"
            "[dpi]\nactive=800\nstages=[800,1600]\n",
            encoding="utf-8",
        )
        store = DeviceProfileStore(temp / "profiles")
        store.save(DiscoveryResult(physical, None, {}))
        known = DiscoveryEngine(
            topology_builder=lambda _mouse: physical,
            detectors=(),
            probe_factory=lambda _node: _Probe(),
            profile_store=store,
            save_profiles=False,
        )
        rediscover = DiscoveryEngine(
            topology_builder=lambda _mouse: physical,
            detectors=(),
            probe_factory=lambda _node: _Probe(),
            profile_store=store,
            save_profiles=False,
        )
        setup = SetupController(
            [mouse], {}, choices_factory=_choices,
            backend_factory=lambda _device: _SetupBackend(),
            known_device_loader=lambda _device: None,
        )

        benchmarks = [
            _measure("process_start", lambda: _subprocess("pass"), max(5, rounds // 20), 1),
            _measure(
                "import_completion",
                lambda: _subprocess("import mouse_control.app"),
                max(5, rounds // 20), 1,
            ),
            _measure("config_load", lambda: load_config(config_path), rounds),
            _measure(
                "topology_construction",
                lambda: build_device_graph(mouse, evdev_nodes=[evdev], hidraw_nodes=hidraw),
                rounds,
            ),
            _measure("persisted_evidence_lookup", lambda: store.restore_result(physical), rounds),
            _measure("known_device_startup", lambda: known.restore_known_device(mouse), rounds),
            _measure(
                "explicit_rediscover",
                lambda: rediscover.discover(mouse, force=True),
                max(10, rounds // 5),
                2,
            ),
            _measure("descriptor_parsing", lambda: parse_report_descriptor(DESCRIPTOR), rounds),
            _measure("single_hid_decode", lambda: decode_input_report(descriptor, REPORT), rounds),
            _measure(
                "bulk_hid_decode_1000",
                lambda: [decode_input_report(descriptor, REPORT) for _ in range(1000)],
                max(10, rounds // 10),
                1,
            ),
            _measure("tui_first_frame_preparation", setup.detail_rows, rounds),
        ]

        backend = _Backend()
        def reconnect() -> None:
            nonlocal backend
            replacement = _Backend()
            supervisor = HardwareSupervisor(
                backend, mouse, lambda _device: replacement,
                DesiredHardwareState(active_dpi=800),
            )
            supervisor.rebind(0)
            backend = replacement

        benchmarks.append(_measure("reconnect_recovery", reconnect, rounds))

        def setup_enter_exit() -> None:
            controller = SetupController(
                [mouse], {}, choices_factory=_choices,
                backend_factory=lambda _device: _SetupBackend(),
                known_device_loader=lambda _device: None,
            )
            controller.restore_temporary_state()
            controller.backend.close()

        stability_cycles = max(200, rounds)
        memory_stability = [
            _measure_memory("reconnect_recovery", reconnect, stability_cycles),
            _measure_memory(
                "explicit_rediscover",
                lambda: rediscover.discover(mouse, force=True),
                stability_cycles,
            ),
            _measure_memory("setup_enter_exit", setup_enter_exit, stability_cycles),
        ]

        trace = PerformanceRecorder()
        with trace.activate():
            known.restore_known_device(mouse)
        known_milestones = {
            item.name: item.median_ns for item in trace.summaries()
        }
        trace = PerformanceRecorder()
        with trace.activate():
            rediscover.discover(mouse, force=True)
        rediscover_milestones = {
            item.name: item.median_ns for item in trace.summaries()
        }

    return {
        "python": sys.version.split()[0],
        "rounds": rounds,
        "benchmarks": [asdict(item) for item in benchmarks],
        "memory_stability": [asdict(item) for item in memory_stability],
        "known_device_milestones_ns": known_milestones,
        "rediscover_milestones_ns": rediscover_milestones,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.rounds < 10:
        parser.error("--rounds must be at least 10")
    result = run(args.rounds)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for item in result["benchmarks"]:
            print(f"{item['name']:<30} {item['median_ns'] / 1_000_000:>10.3f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
