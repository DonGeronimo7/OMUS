from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import json
from .evidence_graph import EvidenceGraph, EvidenceNode


class ReportCategory(str, Enum):
    SOURCE_STATIC = "source_static"
    SOURCE_REPORTED_HARDWARE = "source_reported_hardware"
    COMMUNITY_OMUS_SUCCESS = "community_omus_success"
    COMMUNITY_OMUS_FAILURE = "community_omus_failure"
    OMUS_REPLAY = "omus_replay"
    OMUS_PHYSICAL_VALIDATION = "omus_physical_validation"


@dataclass(frozen=True)
class CommunityReport:
    category: ReportCategory
    model: str
    vendor_id: int | None
    product_id: int | None
    omus_version: str
    connection: str
    feature: str
    firmware: str
    reference: str

    @property
    def grants_write_authority(self) -> bool: return False


def ingest_report(graph: EvidenceGraph, report: CommunityReport) -> str:
    if not report.model or not report.feature or not report.reference:
        raise ValueError("attributed community report required")
    return graph.add(EvidenceNode("source", json.dumps({"type": "community_report", **asdict_report(report)},
                                                       sort_keys=True), f"community:{report.reference}"))


def asdict_report(report: CommunityReport) -> dict:
    return {"category": report.category.value, "model": report.model, "vendor_id": report.vendor_id,
            "product_id": report.product_id, "omus_version": report.omus_version,
            "connection": report.connection, "feature": report.feature,
            "firmware": report.firmware, "reference": report.reference}
