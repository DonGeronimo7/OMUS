from mouse_control.discovery_engine import DiscoveryEngine
from mouse_control.discovery_models import (
    DiscoveredCapability,
    DiscoveryEvidence,
    EvidenceLevel,
    PhysicalDevice,
)


def _physical(*, ambiguous=False):
    return PhysicalDevice(
        "Unknown mouse",
        0x1234,
        0x5678,
        3,
        None,
        [],
        [],
        "model-fingerprint",
        None,
        ambiguous=ambiguous,
    )


def _capability(name, code):
    evidence = DiscoveryEvidence(
        EvidenceLevel.PROVEN,
        code,
        "exact-model promotion proof",
        source="test",
    )
    return DiscoveredCapability(
        name=name,
        readable=True,
        writable=True,
        values=(125, 250, 500, 1000) if name == "report_rate" else (800, 1500),
        evidence=[evidence],
    )


def test_unknown_protocol_preserves_proven_learned_dpi_write_authority():
    engine = DiscoveryEngine(save_profiles=False)
    result = engine.validate(
        _physical(),
        None,
        {"dpi": _capability("dpi", "learned-operation-proven")},
    )
    assert result.capabilities["dpi"].writable is True


def test_unknown_protocol_preserves_proven_learned_polling_write_authority():
    engine = DiscoveryEngine(save_profiles=False)
    result = engine.validate(
        _physical(),
        None,
        {
            "report_rate": _capability(
                "report_rate", "learned-polling-operation-proven"
            )
        },
    )
    assert result.capabilities["report_rate"].writable is True


def test_wrong_proof_code_cannot_authorize_a_different_capability():
    engine = DiscoveryEngine(save_profiles=False)
    result = engine.validate(
        _physical(),
        None,
        {"report_rate": _capability("report_rate", "learned-operation-proven")},
    )
    assert result.capabilities["report_rate"].writable is False


def test_ambiguous_identity_demotes_even_proven_learned_polling():
    engine = DiscoveryEngine(save_profiles=False)
    result = engine.validate(
        _physical(ambiguous=True),
        None,
        {
            "report_rate": _capability(
                "report_rate", "learned-polling-operation-proven"
            )
        },
    )
    assert result.capabilities["report_rate"].writable is False
