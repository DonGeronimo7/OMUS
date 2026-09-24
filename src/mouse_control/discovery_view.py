# SPDX-License-Identifier: AGPL-3.0-or-later
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


def view_from_automatic_outcome(outcome: object) -> DiscoveryView:
    """Adapt the production Automatic Discovery outcome without duplicating it."""
    result = getattr(outcome, "result", outcome)
    protocol = getattr(result, "protocol", None)
    family = getattr(protocol, "name", None) or "unknown protocol"
    capabilities = getattr(result, "capabilities", {})
    proven, inferred = [], []
    if isinstance(capabilities, dict):
        for name, capability in sorted(capabilities.items()):
            mode = str(getattr(capability, "mode", getattr(capability, "status", "unknown")))
            if any(word in mode.lower() for word in ("proven", "verified", "read_write")):
                proven.append(str(name))
            else:
                inferred.append(f"{name}: {mode}")
    cached = bool(getattr(outcome, "cached_profile_used", False))
    plan = getattr(outcome, "research_plan", None)
    missing = tuple(getattr(plan, "blockers", ()) or ())
    if getattr(plan, "deeper_learning_recommended", False):
        human = "complete the guided physical observation requested by Discovery"
    elif missing:
        human = str(missing[0])
    else:
        human = None
    overview = (
        f"Protocol family: {family} [{'PROVEN PATH' if cached else 'RECOGNIZED / UNVERIFIED'}]",
        "Proven capabilities: " + (", ".join(proven) or "none"),
        "Inferred or unresolved: " + (", ".join(inferred) or "none reported"),
        f"Known-device fast path: {'reused' if cached else 'not used'}",
    )
    decisions = (
        "identity: production topology binding retained",
        f"protocol: {family}",
        "authority: corpus, inference, and community evidence do not grant writes",
    )
    return DiscoveryView("known_fast_path" if cached else "automatic_discovery",
                         overview, decisions, human)
