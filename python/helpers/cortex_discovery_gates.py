"""
CORTEX Discovery Gates — Phase D Three-Gate Filtering
======================================================

Gate 0: Instant disqualifiers (free, seconds) — structural impossibilities
Gate 1: Quick signal check (~€0.002, one Exa query) — market viability signals
Gate 2: CVS pre-score (~€0.003, DeepSeek) — buildability + capital + strategy

All three gates must pass before a candidate enters the queue.
Failed candidates return a GateResult explaining why, for parking lot storage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Gate Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GateResult:
    gate: str               # "gate_0" | "gate_1" | "gate_2"
    passed: bool
    score: str              # "pass" | "yellow" | "red" | "fail"
    reason: str             # Human-readable explanation
    park_condition: Optional[str] = None   # What would make this viable later
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate,
            "passed": self.passed,
            "score": self.score,
            "reason": self.reason,
            "park_condition": self.park_condition,
            "details": self.details,
        }


@dataclass
class AllGatesResult:
    passed: bool
    gate_scores: Dict[str, str]          # {"gate_0": "pass", "gate_1": "pass", "gate_2": "yellow"}
    first_failure: Optional[GateResult]  # First gate that failed (or None if all passed)
    all_results: List[GateResult] = field(default_factory=list)

    def park_reason(self) -> str:
        if self.first_failure:
            return self.first_failure.reason
        return ""

    def park_condition(self) -> Optional[str]:
        if self.first_failure:
            return self.first_failure.park_condition
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Gate 0 — Instant Disqualifiers
# ─────────────────────────────────────────────────────────────────────────────

# Keywords that suggest structural problems — checked against niche + description
_REGULATORY_KEYWORDS = [
    "financial advice", "investment advice", "legal advice", "medical diagnosis",
    "pharmaceutical", "insurance underwriting", "crypto exchange", "money transmission",
    "clinical trial", "drug", "prescription", "securities",
]

_HARDWARE_KEYWORDS = [
    "hardware device", "physical product", "iot device", "sensor", "3d print",
    "manufacturing", "assembly", "wearable device", "drone hardware", "robot hardware",
]

_BREAKTHROUGH_KEYWORDS = [
    "quantum computing", "fusion energy", "general agi", "brain-computer interface",
    "molecular assembly",
]


def gate_0(
    niche: str,
    description: str = "",
    capital_estimate_eur: Optional[float] = None,
    params=None,          # VentureDiscoveryParameters — for max_capital_requirement
) -> GateResult:
    """
    Instant disqualifiers. No API calls. Pure heuristics + keyword matching.
    Returns GateResult(passed=False) on first hit, GateResult(passed=True) if all clear.
    """
    text = (niche + " " + description).lower()

    # Check regulatory
    for kw in _REGULATORY_KEYWORDS:
        if kw in text:
            return GateResult(
                gate="gate_0",
                passed=False,
                score="fail",
                reason=f"Regulatory barrier detected: '{kw}' — requires approval before launch",
                park_condition="Park permanently unless regulatory path is clearly defined",
            )

    # Check hardware-first
    for kw in _HARDWARE_KEYWORDS:
        if kw in text:
            return GateResult(
                gate="gate_0",
                passed=False,
                score="fail",
                reason=f"Hardware dependency detected: '{kw}' — hardware must not gate software validation",
                park_condition="Viable if software-only MVP can be defined and hardware is phase 2+",
            )

    # Check breakthrough tech
    for kw in _BREAKTHROUGH_KEYWORDS:
        if kw in text:
            return GateResult(
                gate="gate_0",
                passed=False,
                score="fail",
                reason=f"Breakthrough tech dependency: '{kw}' — core technology does not yet exist",
                park_condition="Park until technology reaches production-ready maturity",
            )

    # Check capital cap
    max_cap = params.max_capital_requirement if params else None
    if max_cap and capital_estimate_eur and capital_estimate_eur > max_cap:
        return GateResult(
            gate="gate_0",
            passed=False,
            score="red",
            reason=f"Capital requirement €{capital_estimate_eur:.0f} exceeds current cap €{max_cap:.0f}",
            park_condition=f"Viable when capital available exceeds €{capital_estimate_eur:.0f}",
        )

    return GateResult(
        gate="gate_0",
        passed=True,
        score="pass",
        reason="No instant disqualifiers detected",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1 — Quick Signal Check
# ─────────────────────────────────────────────────────────────────────────────

async def gate_1(
    niche: str,
    market: str = "global",
    agent=None,
) -> GateResult:
    """
    Quick market viability check. One Exa query + lightweight LLM assessment.
    Cost: ~€0.002. Checks: trend direction, switching intent, solo-operability.
    """
    from python.helpers.cortex_exa_client import CortexExaClient
    from python.helpers.cortex_model_router import CortexModelRouter

    try:
        exa = CortexExaClient.from_agent_config(agent) if agent else CortexExaClient(
            api_key=__import__("os").getenv("EXA_API_KEY", "")
        )

        # Single quick query: alternative search + market health
        results = await exa.search(
            f"{niche} {market} alternative trend growth 2024 2025",
            num_results=5,
            use_autoprompt=True,
        )

        snippets = "\n".join(
            f"- {r.title}: {r.content[:200]}"
            for r in results[:5]
        ) if results else "No results found."

        prompt = (
            f"Niche: '{niche}' | Market: {market}\n\n"
            f"Search snippets:\n{snippets}\n\n"
            "Assess quickly (JSON only, no prose):\n"
            "{\n"
            '  "market_trend": "growing" | "stable" | "declining",\n'
            '  "switching_intent": "high" | "medium" | "low" | "none",\n'
            '  "solo_operable": true | false,\n'
            '  "enterprise_sales_cycle": true | false,\n'
            '  "red_flags": ["list any serious red flags"],\n'
            '  "summary": "1 sentence"\n'
            "}"
        )

        raw = await CortexModelRouter.call_routed_model(
            "classification",
            "You are a market viability analyst. Respond with valid JSON only.",
            prompt,
            agent,
        )

        from python.helpers.dirty_json import DirtyJson
        assessment = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw

        trend = assessment.get("market_trend", "stable")
        switching = assessment.get("switching_intent", "medium")
        solo = assessment.get("solo_operable", True)
        enterprise = assessment.get("enterprise_sales_cycle", False)
        red_flags = assessment.get("red_flags", [])
        summary = assessment.get("summary", "")

        # Determine pass/fail
        if trend == "declining":
            return GateResult(
                gate="gate_1",
                passed=False,
                score="red",
                reason=f"Market declining: {summary}",
                park_condition="Revisit if market reverses — check again in 6 months",
                details=assessment,
            )

        if enterprise:
            return GateResult(
                gate="gate_1",
                passed=False,
                score="red",
                reason="Enterprise B2B sales cycle detected — 6+ months to revenue, not viable at current phase",
                park_condition="Viable at Phase G when capital and team are available",
                details=assessment,
            )

        if not solo:
            return GateResult(
                gate="gate_1",
                passed=False,
                score="red",
                reason="Requires team to operate — solo + CORTEX cannot run this venture",
                park_condition="Viable when CORTEX autonomy is sufficient to replace team members",
                details=assessment,
            )

        score = "pass" if switching in ("high", "medium") and not red_flags else "yellow"
        return GateResult(
            gate="gate_1",
            passed=True,
            score=score,
            reason=summary or f"Market {trend}, switching intent {switching}",
            details=assessment,
        )

    except Exception as e:
        # Gate 1 failure should not block — return yellow (proceed with caution)
        return GateResult(
            gate="gate_1",
            passed=True,
            score="yellow",
            reason=f"Gate 1 check failed (API error) — proceeding with caution: {type(e).__name__}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Gate 2 — CVS Pre-Score
# ─────────────────────────────────────────────────────────────────────────────

async def gate_2(
    niche: str,
    market: str = "global",
    pain_summary: str = "",
    source: str = "",
    params=None,
    agent=None,
) -> Tuple[GateResult, float, str]:
    """
    Lightweight CVS pre-score + strategy type assignment.
    Cost: ~€0.003 (DeepSeek classification).
    Returns: (GateResult, cvs_prescore, strategy_type)
    """
    from python.helpers.cortex_model_router import CortexModelRouter
    from python.helpers.dirty_json import DirtyJson

    min_cvs = params.min_cvs_score if params else 45.0
    min_autonomy = params.min_ai_run_autonomy if params else 50.0

    strategy_list = (
        "Fast Follower, Disruption, Jobs to Be Done, Blue Ocean, "
        "Niche Domination, Picks and Shovels, SaaS Wrapper, Unbundling, "
        "Product-Led Growth, Community-Led Growth, Geographic Rollout"
    )

    prompt = (
        f"Niche: '{niche}' | Market: {market} | Source: {source}\n"
        f"Pain summary: {pain_summary or 'Not provided'}\n\n"
        "Estimate (JSON only, no prose):\n"
        "{\n"
        '  "cvs_prescore": 0-100,\n'
        '  "ai_run_autonomy_estimate": 0-100,\n'
        '  "capital_requirement_eur": estimated initial capital in EUR,\n'
        '  "weeks_to_first_revenue": estimated weeks,\n'
        f'  "strategy_type": one of [{strategy_list}],\n'
        '  "buildability_notes": "1-2 sentences on CORTEX buildability",\n'
        '  "switching_friction": "high" | "medium" | "low",\n'
        '  "geographic_bonus": true if strong CEE/EU opportunity exists vs global,\n'
        '  "summary": "2 sentences on opportunity"\n'
        "}"
    )

    try:
        raw = await CortexModelRouter.call_routed_model(
            "classification",
            "You are a venture pre-screening analyst. Score conservatively. Respond with valid JSON only.",
            prompt,
            agent,
        )

        assessment = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw

        prescore = float(assessment.get("cvs_prescore", 0))
        autonomy = float(assessment.get("ai_run_autonomy_estimate", 0))
        capital = float(assessment.get("capital_requirement_eur", 0))
        weeks = float(assessment.get("weeks_to_first_revenue", 99))
        strategy = assessment.get("strategy_type", "")
        summary = assessment.get("summary", "")
        geo_bonus = bool(assessment.get("geographic_bonus", False))

        # Count red flags
        reds = 0
        red_notes = []

        if autonomy < min_autonomy:
            reds += 1
            red_notes.append(f"AI run autonomy {autonomy:.0f}% < minimum {min_autonomy:.0f}%")

        max_cap = params.max_capital_requirement if params else None
        if max_cap and capital > max_cap:
            reds += 1
            red_notes.append(f"Capital €{capital:.0f} > cap €{max_cap:.0f}")
        elif capital > 2000:
            reds += 1
            red_notes.append(f"Capital €{capital:.0f} > current phase limit €2000")

        if weeks > 16:
            reds += 1
            red_notes.append(f"Time-to-revenue {weeks:.0f} weeks > 16 weeks")

        if prescore < min_cvs:
            reds += 1
            red_notes.append(f"CVS pre-score {prescore:.0f} < minimum {min_cvs:.0f}")

        # 2+ reds → park
        if reds >= 2:
            park_cond = " | ".join(red_notes)
            return (
                GateResult(
                    gate="gate_2",
                    passed=False,
                    score="red",
                    reason=f"2+ red flags: {'; '.join(red_notes[:2])}",
                    park_condition=f"Revisit when: {park_cond}",
                    details=assessment,
                ),
                prescore,
                strategy,
            )

        score = "yellow" if reds == 1 else "pass"
        return (
            GateResult(
                gate="gate_2",
                passed=True,
                score=score,
                reason=summary,
                details=dict(assessment, geographic_bonus=geo_bonus),
            ),
            prescore,
            strategy,
        )

    except Exception as e:
        # Gate 2 failure — let through with yellow, don't block
        return (
            GateResult(
                gate="gate_2",
                passed=True,
                score="yellow",
                reason=f"Gate 2 scoring failed ({type(e).__name__}) — proceeding with caution",
            ),
            0.0,
            "",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Run All Gates
# ─────────────────────────────────────────────────────────────────────────────

async def run_all_gates(
    niche: str,
    market: str = "global",
    description: str = "",
    pain_summary: str = "",
    source: str = "",
    capital_estimate_eur: Optional[float] = None,
    params=None,
    agent=None,
) -> Tuple[AllGatesResult, float, str, bool]:
    """
    Run Gate 0 → Gate 1 → Gate 2 in sequence. Short-circuits on failure.
    Returns: (AllGatesResult, cvs_prescore, strategy_type, geographic_bonus)
    """
    gate_scores: Dict[str, str] = {}
    results: List[GateResult] = []

    # Gate 0
    g0 = gate_0(niche, description, capital_estimate_eur, params)
    gate_scores["gate_0"] = g0.score
    results.append(g0)
    if not g0.passed:
        return (
            AllGatesResult(passed=False, gate_scores=gate_scores, first_failure=g0, all_results=results),
            0.0, "", False,
        )

    # Gate 1
    g1 = await gate_1(niche, market, agent)
    gate_scores["gate_1"] = g1.score
    results.append(g1)
    if not g1.passed:
        return (
            AllGatesResult(passed=False, gate_scores=gate_scores, first_failure=g1, all_results=results),
            0.0, "", False,
        )

    # Gate 2
    g2, prescore, strategy = await gate_2(
        niche, market, pain_summary, source, params, agent
    )
    gate_scores["gate_2"] = g2.score
    results.append(g2)
    geo_bonus = bool(g2.details.get("geographic_bonus", False))

    if not g2.passed:
        return (
            AllGatesResult(passed=False, gate_scores=gate_scores, first_failure=g2, all_results=results),
            prescore, strategy, geo_bonus,
        )

    return (
        AllGatesResult(passed=True, gate_scores=gate_scores, first_failure=None, all_results=results),
        prescore, strategy, geo_bonus,
    )
