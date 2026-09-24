"""Safety-gated HID-BPF observation vocabulary for Discovery.

The kernel/BPF loader is intentionally outside this module.  These types define
what OMUS accepts from such an instrument and how it becomes provenance-rich
EvidenceGraph observations.  Source IDs distinguish kernel-originated traffic
from userspace/hidraw traffic; no observation creates write authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json

from .evidence_graph import EvidenceGraph, EvidenceNode


class HidBpfObservationError(ValueError):
    pass


class HidBpfHook(str, Enum):
    INPUT_REPORT = "input_report"
    HW_REQUEST = "hw_request"
    OUTPUT_REPORT = "output_report"


class HidBpfStage(str, Enum):
    BEFORE = "before"
    AFTER = "after"


@dataclass(frozen=True)
class HidBpfAdmission:
    before_hook_supported: bool
    request_source_supported: bool
    descriptor_metadata_supported: bool
    self_test_passed: bool
    known_safe_kernel: bool

    @property
    def admitted(self) -> bool:
        return all((
            self.before_hook_supported,
            self.request_source_supported,
            self.descriptor_metadata_supported,
            self.self_test_passed,
            self.known_safe_kernel,
        ))

    @property
    def blockers(self) -> tuple[str, ...]:
        checks = (
            (self.before_hook_supported, "before-hook-unavailable"),
            (self.request_source_supported, "request-source-unavailable"),
            (self.descriptor_metadata_supported, "descriptor-metadata-unavailable"),
            (self.self_test_passed, "synthetic-self-test-failed"),
            (self.known_safe_kernel, "kernel-safety-not-admitted"),
        )
        return tuple(reason for ok, reason in checks if not ok)


@dataclass(frozen=True)
class HidBpfObservation:
    timestamp_ns: int
    generation: int
    bus: int
    vendor_id: int
    product_id: int
    interface_number: int
    descriptor_sha256: str
    hook: HidBpfHook
    stage: HidBpfStage
    source_id: int
    report_type: int | None
    report_id: int | None
    payload: bytes
    request_type: int | None = None

    def __post_init__(self) -> None:
        if self.timestamp_ns < 0 or self.generation < 0 or self.interface_number < 0:
            raise HidBpfObservationError("HID-BPF time/generation/interface must be non-negative")
        if self.bus not in (3, 5):
            raise HidBpfObservationError("HID-BPF observation must be USB or Bluetooth HID")
        if any(type(value) is not int or not 0 <= value <= 0xFFFF
               for value in (self.vendor_id, self.product_id)):
            raise HidBpfObservationError("HID-BPF VID/PID must fit u16")
        if len(self.descriptor_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.descriptor_sha256
        ):
            raise HidBpfObservationError("HID-BPF observation requires exact descriptor SHA-256")
        if self.source_id < 0:
            raise HidBpfObservationError("HID-BPF source ID must be non-negative")
        if self.report_id is not None and not 0 <= self.report_id <= 0xFF:
            raise HidBpfObservationError("report ID must fit u8")
        if self.report_type is not None and not 0 <= self.report_type <= 0xFF:
            raise HidBpfObservationError("report type must fit u8")
        if self.request_type is not None and not 0 <= self.request_type <= 0xFF:
            raise HidBpfObservationError("request type must fit u8")
        if len(self.payload) > 4096:
            raise HidBpfObservationError("HID-BPF payload exceeds observation bound")

    @property
    def source_kind(self) -> str:
        return "kernel" if self.source_id == 0 else "userspace_hidraw"

    @property
    def binding_key(self) -> tuple[object, ...]:
        return (
            self.bus, self.vendor_id, self.product_id, self.interface_number,
            self.descriptor_sha256, self.generation,
        )


def require_hid_bpf_admission(admission: HidBpfAdmission) -> None:
    if not admission.admitted:
        raise HidBpfObservationError(
            "HID-BPF instrumentation is not admitted: " + ", ".join(admission.blockers)
        )


def emit_hid_bpf_evidence(
    graph: EvidenceGraph,
    observation: HidBpfObservation,
    *,
    parents: tuple[str, ...] = (),
    source: str = "hid-bpf-observer",
) -> tuple[str, str]:
    """Emit exact interface provenance plus one frame/transaction observation."""

    interface_claim = json.dumps({
        "bus": observation.bus,
        "vendor_id": observation.vendor_id,
        "product_id": observation.product_id,
        "interface_number": observation.interface_number,
        "descriptor_sha256": observation.descriptor_sha256,
        "generation": observation.generation,
    }, sort_keys=True, separators=(",", ":"))
    interface_id = graph.add(EvidenceNode("interface", interface_claim, source, parents))
    claim = json.dumps({
        "timestamp_ns": observation.timestamp_ns,
        "hook": observation.hook.value,
        "stage": observation.stage.value,
        "source_id": observation.source_id,
        "source_kind": observation.source_kind,
        "report_type": observation.report_type,
        "report_id": observation.report_id,
        "request_type": observation.request_type,
        "payload_hex": observation.payload.hex(),
    }, sort_keys=True, separators=(",", ":"))
    kind = "transaction" if observation.hook in {HidBpfHook.HW_REQUEST, HidBpfHook.OUTPUT_REPORT} else "frame"
    observation_id = graph.add(EvidenceNode(kind, claim, source, (interface_id,)))
    return interface_id, observation_id
