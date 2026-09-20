"""Known-protocol detectors used by automatic hardware discovery.

Protocol detection is deliberately conservative.  A detector may only probe a
vendor/device family for which its handshake is already understood.  Generic
unknown hardware never receives speculative protocol requests from this module.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from .proof_state import CapabilityProof, OperationProof, ProofState
from .protocol_repertoire import HIDPP_SENSOR_DPI, HIDPP_REPORT_RATE

from .discovery_models import (
    DeviceNode,
    DiscoveredCapability,
    DiscoveryEvidence,
    EvidenceLevel,
    PhysicalDevice,
    ProtocolMatch,
)
from .hid_session import HidSession
from .hidpp import HidppError, LOGITECH_VENDOR_ID


class ProtocolDetectionError(RuntimeError):
    """Known protocol probing failed in a way discovery should report."""


class ProtocolAmbiguityError(ProtocolDetectionError):
    """More than one interface or device claimed the same writable protocol."""


class ProtocolDetector(Protocol):
    name: str

    def detect(self, device: PhysicalDevice) -> ProtocolMatch | None:
        ...


def _dpi_capability(driver: Any) -> DiscoveredCapability | None:
    caps = driver.capabilities.dpi
    if not (caps.readable or caps.writable or caps.values or caps.ranges):
        return None
    values = tuple(caps.values or ()) or None
    minimum = maximum = step = None
    if caps.ranges:
        # Current protocol-neutral model represents one simple range.  Preserve
        # all explicit values and only publish min/max/step when the driver has
        # exactly one range rather than flattening disjoint ranges incorrectly.
        if len(caps.ranges) == 1:
            item = caps.ranges[0]
            minimum, maximum, step = item.minimum, item.maximum, item.step
    evidence = [
        DiscoveryEvidence(
            EvidenceLevel.PROVEN,
            "hidpp-adjustable-dpi",
            "HID++ ROOT dynamically exposed a validated adjustable-DPI feature",
            source="hidpp_driver",
            details={"readback_on_write": bool(caps.writable)},
        )
    ]
    return DiscoveredCapability(
        name="dpi",
        readable=caps.readable,
        writable=caps.writable,
        values=values,
        minimum=minimum,
        maximum=maximum,
        step=step,
        evidence=evidence,
    )


def _report_rate_capability(driver: Any) -> DiscoveredCapability | None:
    caps = driver.capabilities.report_rate
    if not (caps.readable or caps.writable or caps.values):
        return None
    return DiscoveredCapability(
        name="report_rate",
        readable=caps.readable,
        writable=caps.writable,
        values=tuple(caps.values or ()) or None,
        evidence=[
            DiscoveryEvidence(
                EvidenceLevel.PROVEN,
                "hidpp-report-rate",
                "HID++ ROOT dynamically exposed the validated report-rate feature",
                source="hidpp_driver",
                details={
                    "runtime_policy_required": True,
                    "readback_on_write": bool(caps.writable),
                },
            )
        ],
    )


def _battery_capability(driver: Any) -> DiscoveredCapability | None:
    caps = driver.capabilities.battery
    if not caps.readable:
        return None
    return DiscoveredCapability(
        name="battery",
        readable=True,
        writable=False,
        evidence=[
            DiscoveryEvidence(
                EvidenceLevel.PROVEN,
                "hidpp-battery",
                "HID++ ROOT exposed a battery feature with a validated decoder",
                source="hidpp_driver",
            )
        ],
    )


def hidpp_capability_proof(driver: Any, capability: DiscoveredCapability,
                           *, routing_unambiguous: bool) -> CapabilityProof:
    """Project the existing 0x2201 implementation, never vendor recognition.

    Revisions zero and one use the existing isolated sensor command (the
    latter is exercised by the native driver regression fixtures).
    HID++ 2.0 and the G305's 4.2 envelope are the existing tested envelopes.
    Other revisions require review; ROOT presence alone does not prove semantics.
    Report rate additionally needs live control ownership and stays backend-only.
    """
    recipe = {"dpi": HIDPP_SENSOR_DPI, "report_rate": HIDPP_REPORT_RATE}.get(capability.name)
    feature = driver.features.get(recipe.page) if recipe is not None else None
    compatible = (tuple(driver.protocol_version) in ((2, 0), (4, 2))
                  and getattr(feature, "version", None) in (0, 1))
    caps = driver.capabilities.dpi
    bounded = bool(caps.values or caps.ranges) and all(
        isinstance(value, int) and value > 0 for value in (caps.values or ())
    ) and all(item.minimum > 0 and item.maximum >= item.minimum and item.step > 0
              for item in (caps.ranges or ()))
    implemented = recipe is not None and feature is not None
    bounded = bounded if capability.name == "dpi" else bool(capability.values) and all(
        isinstance(value, int) and value > 0 for value in capability.values)
    failed = capability.name in getattr(driver, "discovery_proof_failures", ())
    return CapabilityProof(
        OperationProof(
            capability.name, ProofState.PROVEN if implemented else ProofState.UNKNOWN,
            (recipe.vendor_evidence,)
            if implemented else (),
        ),
        read_proven=capability.readable,
        capability_identified=implemented, semantics_known=implemented,
        values_bounded=bounded,
        packet_known=implemented, shared_state_safe=implemented,
        confirmation_known=implemented and not failed,
        failure_known=implemented, routing_unambiguous=routing_unambiguous,
        compatible=compatible, volatile_operation=implemented,
        runtime_policy_satisfied=capability.name == "dpi" and capability.writable,
    )


def capabilities_from_hidpp(driver: Any, *, routing_unambiguous: bool = False
                            ) -> dict[str, DiscoveredCapability]:
    """Convert independent capabilities with explainable operation predicates."""
    capabilities: dict[str, DiscoveredCapability] = {}
    for converter in (_dpi_capability, _report_rate_capability, _battery_capability):
        capability = converter(driver)
        if capability is not None:
            proof = hidpp_capability_proof(
                driver, capability, routing_unambiguous=routing_unambiguous)
            capability.writable = capability.writable and proof.write_authorized
            capability.evidence.append(DiscoveryEvidence(
                EvidenceLevel.PROVEN if proof.write_authorized else EvidenceLevel.VALIDATED,
                "capability-proof", "Current binding capability predicates",
                source="protocol_discovery", details=proof.explain(),
            ))
            capabilities[capability.name] = capability.normalized()
    return capabilities


def hidpp_match(device: PhysicalDevice, interface: DeviceNode, driver: Any) -> ProtocolMatch:
    """Receipt from an already verified, uniquely routed owner; no I/O."""
    unambiguous = (not device.ambiguous and interface in device.hidraw_nodes
                   and sum(node.path == interface.path for node in device.hidraw_nodes) == 1
                   and device.bus is not None and device.vendor_id == LOGITECH_VENDOR_ID
                   and device.product_id is not None
                   and (interface.bus, interface.vendor_id, interface.product_id)
                   == (device.bus, device.vendor_id, device.product_id))
    capabilities = capabilities_from_hidpp(driver, routing_unambiguous=unambiguous)
    # Only immutable structure, never current DPI/battery/rate or saved authority.
    signature = {
        "recipe": "hidpp-2201-v0-1",
        "protocol": list(driver.protocol_version),
        "features": [[fid, getattr(f, "index", None), getattr(f, "version", None),
                      getattr(f, "feature_type", None)]
                     for fid, f in sorted(driver.features.items())],
        "interface": interface.interface_number,
        "descriptor": interface.descriptor_sha256,
        "identity": [device.bus, device.vendor_id, device.product_id],
    }
    return ProtocolMatch(
        name="hidpp2", version=".".join(map(str, driver.protocol_version)),
        responder=interface,
        evidence=[DiscoveryEvidence(
            EvidenceLevel.PROVEN, "hidpp2-single-responder",
            "One current owner completed dynamic ROOT discovery",
            source="protocol_discovery", details={"proof_signature": signature},
        )],
        metadata={"capabilities": capabilities, "feature_ids": tuple(sorted(driver.features)),
                  "device_index": driver.device_index, "device_name": driver.name,
                  "proof_path": "exact" if (device.bus, device.vendor_id, device.product_id)
                  == (3, 0x046D, 0x4074) else "family"},
    )


class Hidpp20Detector:
    """Detect one unambiguous Logitech HID++ 2 responder.

    The detector reuses the project's already-validated ROOT discovery.  It
    never hard-codes feature indexes, and every unsuccessful session is closed.

    The HID++ driver import is intentionally lazy.  ``hidpp_driver`` imports
    protocol-neutral types from ``mouse_control.hardware``; importing it while
    this discovery module itself is being imported would otherwise re-enter the
    hardware registry through ``hardware.__init__`` and create a package import
    cycle in installed console-script startup.
    """

    name = "hidpp2"

    def __init__(self, *, session_factory=HidSession, connector=None) -> None:
        self._session_factory = session_factory
        self._connector = connector

    def _connect(self, session):
        connector = self._connector
        if connector is None:
            # Delay this import until hardware package initialization has
            # completed.  Tests may inject a connector without importing the
            # concrete HID++ driver at all.
            from .hidpp_driver import connect_hidpp20

            connector = connect_hidpp20
        return connector(session)

    def detect(self, device: PhysicalDevice) -> ProtocolMatch | None:
        if device.ambiguous:
            raise ProtocolAmbiguityError(
                "physical device identity is ambiguous; refusing protocol binding"
            )
        if device.vendor_id != LOGITECH_VENDOR_ID:
            return None

        matches: list[tuple[DeviceNode, Any]] = []
        for interface in device.hidraw_nodes:
            session = None
            try:
                session = self._session_factory(interface.path)
                driver = self._connect(session)
                matches.append((interface, driver))
            except (OSError, PermissionError, HidppError):
                continue
            finally:
                if session is not None:
                    session.close()

        if not matches:
            return None
        if len(matches) != 1:
            raise ProtocolAmbiguityError(
                f"{len(matches)} hidraw interfaces claimed HID++ 2; refusing ambiguous binding"
            )

        responder, driver = matches[0]
        return hidpp_match(device, responder, driver)


def detect_known_protocol(
    device: PhysicalDevice,
    detectors: Iterable[ProtocolDetector] | None = None,
) -> ProtocolMatch | None:
    """Run detectors in order and return at most one claimed protocol."""

    detector_list = tuple(detectors) if detectors is not None else (Hidpp20Detector(),)
    claims: list[ProtocolMatch] = []
    for detector in detector_list:
        match = detector.detect(device)
        if match is not None:
            claims.append(match)
    if not claims:
        return None
    if len(claims) > 1:
        names = ", ".join(match.name for match in claims)
        raise ProtocolAmbiguityError(
            f"multiple known protocol detectors claimed the device: {names}"
        )
    return claims[0]
