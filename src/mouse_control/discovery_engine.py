"""Automatic, safety-first physical mouse discovery orchestration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .device_profiles import DeviceProfileStore
from .device_topology import TopologyError, build_device_graph
from .discovery import MouseDevice
from .discovery_models import (
    DeviceNode,
    DiscoveredCapability,
    DiscoveryEvidence,
    DiscoveryPhase,
    DiscoveryResult,
    EvidenceLevel,
    PhysicalDevice,
    ProtocolMatch,
)
from .hid_descriptor import (
    HidDescriptorError,
    ParsedHidDescriptor,
    parse_report_descriptor,
    vendor_defined_reports,
)
from .hid_probe import ReadOnlyHidProbe
from .learned_operations import (
    LearnedOperationError,
    LearnedOperationStore,
    matching_interface_node,
)
from .learned_polling import LearnedPollingOperationStore
from .protocol_grammar import SemanticBehavior
from .protocol_discovery import (
    ProtocolAmbiguityError,
    ProtocolDetectionError,
    ProtocolDetector,
    detect_known_protocol,
)
from .protocol_repertoire import FamilyCandidate, match_repertoire


class DiscoveryEngine:
    """Discover one selected mouse without speculative writes.

    Known protocol detectors may use their validated read/query handshake.
    Unknown devices are inspected through :class:`ReadOnlyHidProbe` only and
    matched against the protocol repertoire for read-only family hypotheses.
    """

    def __init__(
        self,
        *,
        topology_builder: Callable[[MouseDevice], PhysicalDevice] = build_device_graph,
        detectors: Iterable[ProtocolDetector] | None = None,
        probe_factory: Callable[[DeviceNode], ReadOnlyHidProbe] | None = None,
        profile_store: DeviceProfileStore | None = None,
        learned_operation_store: LearnedOperationStore | None = None,
        learned_polling_store: LearnedPollingOperationStore | None = None,
        save_profiles: bool = True,
    ) -> None:
        self._topology_builder = topology_builder
        self._detectors = tuple(detectors) if detectors is not None else None
        self._probe_factory = probe_factory or (
            lambda node: ReadOnlyHidProbe(node.path, sysfs_path=node.sysfs_path)
        )
        self._profile_store = profile_store or DeviceProfileStore()
        self._learned_operation_store = learned_operation_store or LearnedOperationStore()
        self._learned_polling_store = (
            learned_polling_store or LearnedPollingOperationStore()
        )
        self._save_profiles = save_profiles
        self._descriptors: dict[DeviceNode, ParsedHidDescriptor] = {}
        self._feature_snapshots: dict[DeviceNode, dict[int, bytes]] = {}
        self._repertoire_candidates: tuple[FamilyCandidate, ...] = ()
        self._observations: list[DiscoveryEvidence] = []
        self._phases: list[DiscoveryPhase] = []
        self._profile_path: Path | None = None

    @property
    def descriptors(self) -> dict[DeviceNode, ParsedHidDescriptor]:
        return dict(self._descriptors)

    @property
    def feature_snapshots(self) -> dict[DeviceNode, dict[int, bytes]]:
        return {node: dict(snapshot) for node, snapshot in self._feature_snapshots.items()}

    @property
    def repertoire_candidates(self) -> tuple[FamilyCandidate, ...]:
        return self._repertoire_candidates

    @property
    def profile_path(self) -> Path | None:
        """Path written by the most recent successful discovery, if any."""

        return self._profile_path

    def _phase(self, phase: DiscoveryPhase) -> None:
        if not self._phases or self._phases[-1] is not phase:
            self._phases.append(phase)

    def discover(self, mouse: MouseDevice) -> DiscoveryResult:
        """Run automatic discovery for one already-selected evdev mouse."""

        self._descriptors.clear()
        self._feature_snapshots.clear()
        self._repertoire_candidates = ()
        self._observations.clear()
        self._phases.clear()
        self._profile_path = None

        self._phase(DiscoveryPhase.ENUMERATE)
        physical = self.build_topology(mouse)
        self._phase(DiscoveryPhase.CORRELATE)

        self._phase(DiscoveryPhase.DESCRIPTORS)
        self.inspect_descriptors(physical)

        self._phase(DiscoveryPhase.PROTOCOL)
        protocol = self.detect_protocol(physical)

        if protocol is not None:
            capabilities = self.query_known_protocol(protocol)
        else:
            self._phase(DiscoveryPhase.OBSERVE)
            capabilities = self.observe_unknown_device(physical)

        self._phase(DiscoveryPhase.VALIDATE)
        result = self.validate(physical, protocol, capabilities)
        self._phase(DiscoveryPhase.COMPLETE)
        result.phases = list(self._phases)

        if self._save_profiles and not physical.ambiguous:
            self._profile_path = self.save_profile(result)
        return result

    def build_topology(self, mouse: MouseDevice) -> PhysicalDevice:
        physical = self._topology_builder(mouse)
        self._observations.extend(physical.evidence)
        self._observations.append(
            DiscoveryEvidence(
                EvidenceLevel.VALIDATED if not physical.ambiguous else EvidenceLevel.OBSERVED,
                "physical-device-graph",
                (
                    f"Correlated {len(physical.evdev_nodes)} evdev and "
                    f"{len(physical.hidraw_nodes)} hidraw interfaces"
                ),
                source="discovery_engine",
                details={"ambiguous": physical.ambiguous},
            )
        )
        return physical

    def inspect_descriptors(
        self, physical: PhysicalDevice
    ) -> dict[DeviceNode, ParsedHidDescriptor]:
        for node in physical.hidraw_nodes:
            probe = self._probe_factory(node)
            try:
                raw = probe.read_descriptor()
                descriptor = parse_report_descriptor(raw)
            except (OSError, PermissionError, HidDescriptorError, ValueError) as exc:
                self._observations.append(
                    DiscoveryEvidence(
                        EvidenceLevel.OBSERVED,
                        "descriptor-unavailable",
                        f"Could not inspect one HID descriptor: {exc}",
                        source="hid_descriptor",
                        details={"interface_number": node.interface_number},
                    )
                )
                continue
            self._descriptors[node] = descriptor
            self._observations.append(
                DiscoveryEvidence(
                    EvidenceLevel.VALIDATED,
                    "descriptor-parsed",
                    f"Parsed {len(descriptor.reports)} reports from a HID interface",
                    source="hid_descriptor",
                    details={
                        "interface_number": node.interface_number,
                        "descriptor_sha256": node.descriptor_sha256,
                    },
                )
            )
        return dict(self._descriptors)

    def detect_protocol(self, physical: PhysicalDevice) -> ProtocolMatch | None:
        try:
            return detect_known_protocol(physical, self._detectors)
        except ProtocolAmbiguityError as exc:
            physical.ambiguous = True
            self._observations.append(
                DiscoveryEvidence(
                    EvidenceLevel.VALIDATED,
                    "protocol-ambiguous",
                    str(exc),
                    source="protocol_discovery",
                )
            )
            return None
        except ProtocolDetectionError as exc:
            self._observations.append(
                DiscoveryEvidence(
                    EvidenceLevel.OBSERVED,
                    "protocol-probe-failed",
                    str(exc),
                    source="protocol_discovery",
                )
            )
            return None

    def query_known_protocol(
        self, protocol: ProtocolMatch
    ) -> dict[str, DiscoveredCapability]:
        raw = protocol.metadata.get("capabilities", {})
        if not isinstance(raw, dict):
            return {}
        result: dict[str, DiscoveredCapability] = {}
        for name, capability in raw.items():
            if isinstance(capability, DiscoveredCapability):
                result[str(name)] = capability.normalized()
        return result

    def observe_unknown_device(
        self, physical: PhysicalDevice
    ) -> dict[str, DiscoveredCapability]:
        """Take a safe baseline snapshot and classify structure without writes."""

        for node, descriptor in self._descriptors.items():
            vendor_reports = vendor_defined_reports(descriptor)
            if vendor_reports:
                self._observations.append(
                    DiscoveryEvidence(
                        EvidenceLevel.OBSERVED,
                        "vendor-defined-reports",
                        f"Observed {len(vendor_reports)} vendor-defined HID reports",
                        source="hid_descriptor",
                        details={
                            "interface_number": node.interface_number,
                            "reports": tuple(
                                (report.report_type, report.report_id, report.byte_length)
                                for report in vendor_reports
                            ),
                        },
                    )
                )

            feature_reports = descriptor.feature_reports
            if not feature_reports:
                continue
            probe = self._probe_factory(node)
            try:
                snapshot = probe.snapshot_feature_reports(feature_reports)
            except (OSError, PermissionError) as exc:
                self._observations.append(
                    DiscoveryEvidence(
                        EvidenceLevel.OBSERVED,
                        "feature-snapshot-unavailable",
                        f"Feature reports could not be read: {exc}",
                        source="hid_probe",
                        details={"interface_number": node.interface_number},
                    )
                )
                continue
            if snapshot:
                self._feature_snapshots[node] = snapshot
                self._observations.append(
                    DiscoveryEvidence(
                        EvidenceLevel.OBSERVED,
                        "feature-baseline",
                        f"Captured {len(snapshot)} read-only Feature-report baselines",
                        source="hid_probe",
                        details={
                            "interface_number": node.interface_number,
                            "report_ids": tuple(sorted(snapshot)),
                        },
                    )
                )

        self._repertoire_candidates = match_repertoire(physical, self._descriptors)
        for candidate in self._repertoire_candidates:
            family = candidate.family
            self._observations.append(
                DiscoveryEvidence(
                    EvidenceLevel.CORRELATED,
                    "protocol-family-candidate",
                    (
                        f"HID structure is compatible with {family.name}/{family.revision} "
                        f"(score {candidate.score}); classification does not authorize writes"
                    ),
                    source="protocol_repertoire",
                    details={
                        "family": family.name,
                        "revision": family.revision,
                        "score": candidate.score,
                        "matched": candidate.matched,
                        "missing": candidate.missing,
                        "strongest_source_trust": family.strongest_trust.value,
                        "exact_identity": candidate.exact_identity,
                        "write_authorized": candidate.write_authorized,
                    },
                )
            )

        # Separately persisted learned operations authorize generic writes
        # only after explicit exact-model promotion. Calibrated/read-side
        # evidence remains permanently non-writable.
        capabilities: dict[str, DiscoveredCapability] = {}

        learned = self._learned_operation_store.find_for_physical(
            physical,
            behavior=SemanticBehavior.DPI_VALUE,
            proven_only=True,
        )
        if learned is not None:
            _path, operation = learned
            try:
                node = matching_interface_node(operation, physical)
            except LearnedOperationError as exc:
                self._observations.append(
                    DiscoveryEvidence(
                        EvidenceLevel.VALIDATED,
                        "learned-operation-interface-mismatch",
                        str(exc),
                        source="learned_operations",
                    )
                )
            else:
                evidence = DiscoveryEvidence(
                    EvidenceLevel.PROVEN,
                    "learned-operation-proven",
                    (
                        "Exact-model learned DPI transaction was independently "
                        "promoted by raw readback plus physical CPI verification"
                    ),
                    source="learned_operations",
                    details={
                        "behavior": operation.behavior.value,
                        "demonstrated_values": operation.demonstrated_values,
                        "interface_number": node.interface_number,
                        "descriptor_sha256": node.descriptor_sha256,
                        "write_scope": operation.write_scope.value,
                    },
                )
                self._observations.append(evidence)
                capabilities["dpi"] = DiscoveredCapability(
                    name="dpi",
                    readable=True,
                    writable=True,
                    values=operation.demonstrated_values,
                    evidence=[evidence],
                ).normalized()

        learned_polling = self._learned_polling_store.find_for_physical(
            physical,
            proven_only=True,
        )
        if learned_polling is not None:
            _path, operation = learned_polling
            try:
                node = matching_interface_node(operation, physical)
            except LearnedOperationError as exc:
                self._observations.append(
                    DiscoveryEvidence(
                        EvidenceLevel.VALIDATED,
                        "learned-polling-interface-mismatch",
                        str(exc),
                        source="learned_polling",
                    )
                )
            else:
                evidence = DiscoveryEvidence(
                    EvidenceLevel.PROVEN,
                    "learned-polling-operation-proven",
                    (
                        "Exact-model learned report-rate state machine was "
                        "independently promoted by generic readback, physical "
                        "timing, persistent-session proof, and exact rollback"
                    ),
                    source="learned_polling",
                    details={
                        "behavior": operation.behavior.value,
                        "demonstrated_rates": operation.demonstrated_rates,
                        "interface_number": node.interface_number,
                        "descriptor_sha256": node.descriptor_sha256,
                        "write_scope": operation.write_scope.value,
                    },
                )
                self._observations.append(evidence)
                capabilities["report_rate"] = DiscoveredCapability(
                    name="report_rate",
                    readable=True,
                    writable=True,
                    values=operation.demonstrated_rates,
                    evidence=[evidence],
                ).normalized()

        # Descriptor structure, family resemblance, feature snapshots and
        # changing bytes remain evidence, not semantics. DEMONSTRATED learned
        # operations are intentionally inert until promotion.
        return capabilities

    def validate(
        self,
        physical: PhysicalDevice,
        protocol: ProtocolMatch | None,
        capabilities: dict[str, DiscoveredCapability],
    ) -> DiscoveryResult:
        normalized: dict[str, DiscoveredCapability] = {}
        for name, capability in capabilities.items():
            item = capability.normalized()
            if physical.ambiguous and item.writable:
                item = DiscoveredCapability(
                    name=item.name,
                    readable=item.readable,
                    writable=False,
                    values=item.values,
                    minimum=item.minimum,
                    maximum=item.maximum,
                    step=item.step,
                    evidence=[
                        *item.evidence,
                        DiscoveryEvidence(
                            EvidenceLevel.VALIDATED,
                            "write-demoted-ambiguity",
                            "Writable capability disabled because physical identity is ambiguous",
                            source="discovery_engine",
                        ),
                    ],
                )
            normalized[name] = item

        if protocol is None:
            # Generic writes remain forbidden unless that specific capability
            # carries the corresponding exact-model PROVEN promotion evidence.
            proven_codes = {
                "dpi": "learned-operation-proven",
                "report_rate": "learned-polling-operation-proven",
            }
            for name, item in tuple(normalized.items()):
                expected_code = proven_codes.get(name)
                learned_proven = expected_code is not None and any(
                    evidence.level is EvidenceLevel.PROVEN
                    and evidence.code == expected_code
                    for evidence in item.evidence
                )
                if item.writable and not learned_proven:
                    normalized[name] = DiscoveredCapability(
                        name=item.name,
                        readable=item.readable,
                        writable=False,
                        values=item.values,
                        minimum=item.minimum,
                        maximum=item.maximum,
                        step=item.step,
                        evidence=list(item.evidence),
                    )

        return DiscoveryResult(
            device=physical,
            protocol=protocol,
            capabilities=normalized,
            observations=list(self._observations),
            phases=list(self._phases),
        )

    def save_profile(self, result: DiscoveryResult) -> Path | None:
        try:
            path = self._profile_store.save(result)
        except Exception as exc:
            # Profile caching must never turn successful hardware discovery into
            # a runtime failure.
            result.observations.append(
                DiscoveryEvidence(
                    EvidenceLevel.OBSERVED,
                    "profile-save-failed",
                    f"Discovery succeeded but its cache profile could not be saved: {exc}",
                    source="device_profiles",
                )
            )
            return None
        return path
