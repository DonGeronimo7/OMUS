"""Canonical presentation model for Lab/TUI Discovery views."""
from __future__ import annotations
from dataclasses import dataclass
from .discovery_pipeline import DiscoveryResult


@dataclass(frozen=True)
class DiscoveryView:
    phase: str
    overview: tuple[str, ...]
    decisions: tuple[str, ...]
    human_action: str | None


def build_discovery_view(result: DiscoveryResult) -> DiscoveryView:
    phase = result.trace[-1].phase if result.trace else "not_started"
    overview = (
        f"Interface {result.admission.interface.number}: "
        f"{'admitted' if result.admission.admitted else 'quarantined'}",
        f"Protocol Genome records: {len(result.genome_ids)}",
        f"Advice candidates: {len(result.advice)}",
        f"Grammar alternatives: {len(result.grammars)}",
    )
    decisions = tuple(
        f"{item.phase}: {item.decision}" +
        (f" — {'; '.join(item.reasons)}" if item.reasons else "")
        for item in result.trace
    )
    return DiscoveryView(phase, overview, decisions, result.human_action)
