"""
CORTEX Opportunity Scorer — Phase D
=====================================

Takes a candidate that passed all three gates and produces:
  - Final composite queue score (0-100)
  - Switching friction assessment
  - Formatted opportunity summary for queue display

The 9 scoring filters map to weights. Geographic bonus adds +5.
Strategy type is assigned by Gate 2 but confirmed/refined here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from python.helpers.cortex_discovery_params import (
    VentureCandidate,
    VentureDiscoveryParameters,
)


# ─────────────────────────────────────────────────────────────────────────────
# Scoring Weights (must sum to 1.0)
# ─────────────────────────────────────────────────────────────────────────────

_WEIGHTS = {
    "pain_paid_for":        0.18,
    "complaint_specific":   0.14,
    "switching_intent":     0.14,
    "stack_fit":            0.16,
    "cee_opportunity":      0.07,
    "cortex_buildability":  0.16,
    "capital_requirement":  0.08,
    "time_to_revenue":      0.04,
    "strategy_match":       0.03,
}

assert abs(sum(_WEIGHTS.values()) - 1.0) < 0.001, "Weights must sum to 1.0"


@dataclass
class OpportunityScore:
    composite: float                          # 0-100
    dimension_scores: Dict[str, float]        # each 0-100
    geographic_bonus: bool
    switching_friction: str                   # "high" | "medium" | "low"
    strategy_type: str
    summary: str                              # 2-3 sentence queue display text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composite": self.composite,
            "dimension_scores": self.dimension_scores,
            "geographic_bonus": self.geographic_bonus,
            "switching_friction": self.switching_friction,
            "strategy_type": self.strategy_type,
            "summary": self.summary,
        }


async def score_opportunity(
    candidate: VentureCandidate,
    gate2_details: Dict[str, Any],
    params: Optional[VentureDiscoveryParameters] = None,
    agent=None,
) -> OpportunityScore:
    """
    Score a gate-passing candidate on all 9 dimensions.
    gate2_details: the raw dict from Gate 2's DeepSeek assessment.
    """
    from python.helpers.cortex_model_router import CortexModelRouter
    from python.cortex.dirty_json import DirtyJson

    signals = candidate.source_signals
    pain_texts = " | ".join(s.extracted_pain for s in signals[:5]) if signals else ""
    paying_count = sum(1 for s in signals if s.paying_evidence)
    signal_strength = max((s.strength for s in signals), default=1) if signals else 1
    geo = bool(gate2_details.get("geographic_bonus", candidate.geographic_bonus))
    switching_friction = gate2_details.get("switching_friction", "medium")
    strategy = candidate.strategy_type or gate2_details.get("strategy_type", "")

    # Determine preferred strategies for this user
    preferred = params.strategy_preferences if params else []

    prompt = (
        f"Niche: '{candidate.niche}' | Market: {candidate.market}\n"
        f"Source: {candidate.source} | Strategy: {strategy}\n"
        f"Pain signals ({len(signals)} signals, {paying_count} with paying evidence):\n"
        f"{pain_texts[:500]}\n\n"
        f"Gate 2 assessment: {gate2_details.get('summary', '')}\n"
        f"Buildability: {gate2_details.get('buildability_notes', '')}\n"
        f"Capital estimate: €{gate2_details.get('capital_requirement_eur', '?')}\n"
        f"Weeks to revenue: {gate2_details.get('weeks_to_first_revenue', '?')}\n"
        f"Switching friction: {switching_friction}\n"
        f"Geographic bonus (CEE/EU): {geo}\n"
        f"Preferred strategies: {', '.join(preferred) if preferred else 'any'}\n\n"
        "Score each dimension 0-100. JSON only:\n"
        "{\n"
        '  "pain_paid_for": 0-100,\n'
        '  "complaint_specific": 0-100,\n'
        '  "switching_intent": 0-100,\n'
        '  "stack_fit": 0-100,\n'
        '  "cee_opportunity": 0-100,\n'
        '  "cortex_buildability": 0-100,\n'
        '  "capital_requirement": 0-100,\n'
        '  "time_to_revenue": 0-100,\n'
        '  "strategy_match": 0-100,\n'
        '  "switching_friction_assessment": "brief 1-sentence note on lock-in/friction",\n'
        '  "opportunity_summary": "2-3 sentences for queue display"\n'
        "}"
    )

    try:
        raw = await CortexModelRouter.call_routed_model(
            "classification",
            "You are a venture opportunity analyst. Score conservatively. JSON only.",
            prompt,
            agent,
        )
        dims = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw

        dimension_scores = {k: float(dims.get(k, 50)) for k in _WEIGHTS}
        composite = sum(dimension_scores[k] * _WEIGHTS[k] for k in _WEIGHTS)
        if geo:
            composite = min(100.0, composite + 5.0)

        return OpportunityScore(
            composite=round(composite, 1),
            dimension_scores=dimension_scores,
            geographic_bonus=geo,
            switching_friction=switching_friction,
            strategy_type=strategy,
            summary=dims.get("opportunity_summary", "No summary generated."),
        )

    except Exception as e:
        # Fallback: use Gate 2 prescore as composite
        prescore = candidate.cvs_prescore or float(gate2_details.get("cvs_prescore", 0))
        return OpportunityScore(
            composite=prescore,
            dimension_scores={k: prescore for k in _WEIGHTS},
            geographic_bonus=geo,
            switching_friction=switching_friction,
            strategy_type=strategy,
            summary=gate2_details.get("summary", f"Scoring error: {type(e).__name__}"),
        )


def apply_score_to_candidate(
    candidate: VentureCandidate,
    score: OpportunityScore,
    gate2_details: Dict[str, Any],
) -> VentureCandidate:
    """Update candidate in-place with scoring results. Returns the candidate."""
    candidate.cvs_prescore = score.composite
    candidate.strategy_type = score.strategy_type
    candidate.geographic_bonus = score.geographic_bonus
    candidate.switching_friction_notes = (
        gate2_details.get("switching_friction_assessment", "") or
        f"Friction level: {score.switching_friction}"
    )
    candidate.opportunity_summary = score.summary
    return candidate


def format_queue_entry(candidate: VentureCandidate, rank: int) -> str:
    """One-line queue display for a candidate."""
    geo = " [CEE+]" if candidate.geographic_bonus else ""
    strat = f" [{candidate.strategy_type}]" if candidate.strategy_type else ""
    gates = "/".join(
        v for v in candidate.gate_scores.values()
    ) if candidate.gate_scores else "?"
    signals = len(candidate.source_signals)
    paying = sum(1 for s in candidate.source_signals if s.paying_evidence)

    return (
        f"#{rank} [{candidate.id}] {candidate.name}\n"
        f"   Score: {candidate.cvs_prescore:.0f}/100{strat}{geo} | "
        f"Source: {candidate.source} | Gates: {gates}\n"
        f"   Signals: {signals} ({paying} paying evidence) | Market: {candidate.market}\n"
        f"   {candidate.opportunity_summary[:150]}"
    )


def format_full_candidate(candidate: VentureCandidate) -> str:
    """Full detail view for `review <id>` action."""
    lines = [
        f"## Candidate: {candidate.name}",
        f"**ID:** {candidate.id} | **Source:** {candidate.source} | **Status:** {candidate.status}",
        f"**Niche:** {candidate.niche} | **Market:** {candidate.market}",
        f"**Strategy:** {candidate.strategy_type or '—'}",
        f"**CVS Pre-score:** {candidate.cvs_prescore:.0f}/100",
        "",
        f"**Opportunity:** {candidate.opportunity_summary}",
        "",
        f"**Switching friction:** {candidate.switching_friction_notes or '—'}",
        f"**Geographic bonus:** {'Yes (CEE/EU opportunity)' if candidate.geographic_bonus else 'No'}",
        "",
        "**Gate results:**",
    ]
    for gate, score in (candidate.gate_scores or {}).items():
        lines.append(f"  - {gate}: {score}")

    if candidate.source_signals:
        lines.append(f"\n**Pain signals ({len(candidate.source_signals)}):**")
        for s in candidate.source_signals[:5]:
            paying = " ✓ paying" if s.paying_evidence else ""
            lines.append(f"  [{s.source}]{paying} {s.extracted_pain[:120]}")

    if candidate.research_context:
        lines.append(f"\n**Research context:** Available — will be passed to venture_create on accept")

    lines += [
        "",
        f"**Actions:** `accept {candidate.id}` | `reject {candidate.id} [reason]` | `park {candidate.id} [reason]`",
    ]
    return "\n".join(lines)
