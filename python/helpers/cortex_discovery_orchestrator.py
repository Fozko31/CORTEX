"""
CORTEX Discovery Orchestrator -- Phase D, D-8
==============================================

Wires D-2 through D-7 into a single autonomous discovery pipeline for one niche.
Called by the venture_discover tool (D-9) and the scheduler extension (D-10).

Pipeline (always in this order):

  Step 0  gate_0 disqualifier check      free, instant
  Step 1  collect pain signals (D-2)     ~EUR 0.002  (Exa review signals)
  Step 2  gate_1 quick signal check      ~EUR 0.001  (DeepSeek synthesis)
          -> if red: park immediately, skip expensive steps
  Step 3  cluster signals (D-3)          free (keyword) or ~EUR 0.001 (LLM)
  Step 4  influencer monitoring (D-4)    ~EUR 0.01-0.05  (transcript + extract)
          -> skipped if skip_influencers=True or budget exceeded
  Step 5  disruption scan (D-5)          ~EUR 0.017 (5 tools x EUR 0.003 + discovery)
  Step 6  gate_2 CVS pre-score           ~EUR 0.002  (DeepSeek with full context)
          -> uses pain_summary (D-3) + disruption_context (D-5) as input
  Step 7  score opportunity (D-6)        ~EUR 0.001  (DeepSeek)
  Step 8  queue / park / reject

Total: ~EUR 0.05-0.09 per full run (budget-capped at max_cost_eur).

Cost gate: gate_1 red -> park, skip D-4/D-5/D-6 scoring entirely.
"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from python.helpers.cortex_discovery_params import (
    PainSignal,
    VentureCandidate,
    VentureDiscoveryParameters,
    load_signals,
    save_signals,
    add_to_queue,
    park_candidate,
    reject_candidate,
)

# Sub-component imports at module level so they are patchable in tests.
# Each is wrapped in try/except: missing dependencies degrade gracefully at call time.
try:
    from python.helpers.cortex_discovery_gates import gate_0, gate_1, gate_2
except Exception:  # pragma: no cover
    gate_0 = gate_1 = gate_2 = None  # type: ignore[assignment]

try:
    from python.helpers.cortex_signal_ingestion import fetch_review_signals
except Exception:  # pragma: no cover
    fetch_review_signals = None  # type: ignore[assignment]

try:
    from python.helpers.cortex_pain_clustering import cluster_and_store, build_pain_summary
except Exception:  # pragma: no cover
    cluster_and_store = build_pain_summary = None  # type: ignore[assignment]

try:
    from python.helpers.cortex_disruption_scanner import (
        scan_disruption_targets,
        format_disruption_summary,
    )
except Exception:  # pragma: no cover
    scan_disruption_targets = format_disruption_summary = None  # type: ignore[assignment]

try:
    from python.helpers.cortex_opportunity_scorer import score_opportunity, apply_score_to_candidate
except Exception:  # pragma: no cover
    score_opportunity = apply_score_to_candidate = None  # type: ignore[assignment]

try:
    from python.helpers.cortex_influencer_monitor import (
        discover_influencers_for_niche,
        process_influencer,
    )
except Exception:  # pragma: no cover
    discover_influencers_for_niche = process_influencer = None  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────────────
# Result Model
# ─────────────────────────────────────────────────────────────────────────────

OUTCOME_QUEUED   = "queued"
OUTCOME_REJECTED = "rejected"
OUTCOME_PARKED   = "parked"
OUTCOME_ERROR    = "error"

_VALID_OUTCOMES = {OUTCOME_QUEUED, OUTCOME_REJECTED, OUTCOME_PARKED, OUTCOME_ERROR}


@dataclass
class DiscoveryResult:
    niche: str
    market: str
    outcome: str                            # queued | rejected | parked | error
    reason: str                             # human-readable outcome reason

    # Intelligence gathered
    signals: List[PainSignal] = field(default_factory=list)
    clusters: List[Any] = field(default_factory=list)   # List[PainCluster] (typed as Any to avoid circular import)
    disruption_targets: List[Any] = field(default_factory=list)  # List[DisruptionTarget]

    # Gate + scoring output
    candidate: Optional[VentureCandidate] = None
    gate_result: Optional[Any] = None       # AllGatesResult
    final_score: Optional[float] = None
    strategy_type: str = ""
    pain_summary: str = ""
    disruption_summary: str = ""

    # Execution metadata
    cost_estimate_eur: float = 0.0
    steps_completed: List[str] = field(default_factory=list)
    steps_skipped: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "niche": self.niche,
            "market": self.market,
            "outcome": self.outcome,
            "reason": self.reason,
            "signal_count": len(self.signals),
            "cluster_count": len(self.clusters),
            "disruption_target_count": len(self.disruption_targets),
            "candidate_id": self.candidate.id if self.candidate else None,
            "final_score": self.final_score,
            "strategy_type": self.strategy_type,
            "pain_summary": self.pain_summary,
            "disruption_summary": self.disruption_summary,
            "cost_estimate_eur": self.cost_estimate_eur,
            "steps_completed": self.steps_completed,
            "steps_skipped": self.steps_skipped,
            "errors": self.errors,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Cost Tracking
# ─────────────────────────────────────────────────────────────────────────────

# Rough EUR cost estimates per step (used for budget gating, not billing)
_STEP_COSTS = {
    "gate_0":           0.000,
    "signal_ingestion": 0.002,
    "gate_1":           0.001,
    "pain_clustering":  0.001,
    "influencers":      0.030,   # mid estimate (3 influencers x 5 videos)
    "disruption_scan":  0.017,
    "gate_2":           0.002,
    "opportunity_score":0.001,
}


def estimate_cost(steps: List[str]) -> float:
    """Return EUR cost estimate for a list of step names."""
    return round(sum(_STEP_COSTS.get(s, 0) for s in steps), 4)


# ─────────────────────────────────────────────────────────────────────────────
# D-4 Batch Helper (process all influencers for a niche)
# ─────────────────────────────────────────────────────────────────────────────

async def process_niche_influencers(
    niche: str,
    market: str = "global",
    max_influencers: int = 3,
    max_videos_per_influencer: int = 5,
    max_age_days: int = 180,
    agent=None,
) -> List[PainSignal]:
    """
    Find influencers for the niche and extract pain signals from their recent videos.
    Saves new signals to the niche signal store (so D-5 can pick them up).
    Returns all newly extracted signals.
    Cost: ~EUR 0.02-0.05 depending on transcripts found.
    """
    print(f"[CORTEX orchestrator] D-4: discovering influencers for '{niche}'")
    influencers = await discover_influencers_for_niche(
        niche=niche,
        market=market,
        limit=max_influencers,
        agent=agent,
    )
    print(f"[CORTEX orchestrator] D-4: {len(influencers)} influencers found")

    all_new_signals: List[PainSignal] = []
    for inf in influencers:
        try:
            signals = await process_influencer(
                influencer=inf,
                niche=niche,
                market=market,
                max_videos=max_videos_per_influencer,
                max_age_days=max_age_days,
                agent=agent,
            )
            all_new_signals.extend(signals)
            print(
                f"[CORTEX orchestrator] D-4: {inf.handle or inf.channel_url}: "
                f"{len(signals)} signals extracted"
            )
        except Exception as e:
            print(f"[CORTEX orchestrator] D-4: error processing {inf.handle}: {e}")

    # Merge into signal store (deduplicate by extracted_pain text)
    if all_new_signals:
        existing = load_signals(niche)
        existing_pains = {s.extracted_pain for s in existing}
        deduped = [s for s in all_new_signals if s.extracted_pain not in existing_pains]
        if deduped:
            save_signals(niche, existing + deduped)
            print(f"[CORTEX orchestrator] D-4: {len(deduped)} new signals saved to store")

    return all_new_signals


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

async def run_discovery(
    niche: str,
    market: str = "global",
    params: Optional[VentureDiscoveryParameters] = None,
    agent=None,
    skip_influencers: bool = False,
    max_cost_eur: float = 2.0,
    description: str = "",
) -> DiscoveryResult:
    """
    Full autonomous discovery pipeline for one niche.

    Args:
        niche:              The niche to evaluate (e.g. "local SEO for restaurants")
        market:             Geographic market (e.g. "Slovenia", "global")
        params:             Discovery parameters (loaded from file if None)
        agent:              Agent Zero agent (for LLM calls via model router)
        skip_influencers:   Skip D-4 influencer monitoring (faster, cheaper)
        max_cost_eur:       Hard budget cap — stops pipeline before exceeding this
        description:        Optional description of the niche for gate prompts

    Returns:
        DiscoveryResult with outcome, candidate (if queued), and all intelligence gathered.
    """
    result = DiscoveryResult(niche=niche, market=market, outcome=OUTCOME_ERROR, reason="Pipeline did not complete")
    cost_so_far = 0.0

    if params is None:
        try:
            params = VentureDiscoveryParameters.load() or VentureDiscoveryParameters()
        except Exception:
            params = VentureDiscoveryParameters()

    print(f"\n[CORTEX orchestrator] Starting discovery: '{niche}' | {market}")
    print(f"[CORTEX orchestrator] Budget: EUR {max_cost_eur:.2f} | skip_influencers={skip_influencers}")

    # ── Step 0: Gate 0 — instant disqualifier check ───────────────────────────
    try:
        g0 = gate_0(niche, description="", capital_estimate_eur=None, params=params)
        result.steps_completed.append("gate_0")
        print(f"[CORTEX orchestrator] gate_0: {g0.score} | passed={g0.passed}")

        if not g0.passed:
            result.outcome = OUTCOME_PARKED
            result.reason = g0.reason or "Gate 0: disqualified (regulatory, capital, or structural)"
            _finalize(result, cost_so_far)
            return result

    except Exception as e:
        err = f"gate_0 error: {e}"
        result.errors.append(err)
        print(f"[CORTEX orchestrator] {err}")
        # Don't exit — gate_0 errors are non-blocking (permissive fail-open)

    # ── Step 1: Collect pain signals (D-2) ────────────────────────────────────
    cost_so_far += _STEP_COSTS["signal_ingestion"]
    if cost_so_far > max_cost_eur:
        result.steps_skipped.append("signal_ingestion")
    else:
        try:
            signals = await fetch_review_signals(
                niche=niche,
                tool_name=None,
                limit=10,
            )
            # Also load any pre-existing signals from the store
            existing = load_signals(niche)
            all_signals = existing + [s for s in signals if s.extracted_pain not in {x.extracted_pain for x in existing}]
            if signals:
                save_signals(niche, all_signals)
            result.signals = all_signals
            result.steps_completed.append("signal_ingestion")
            print(f"[CORTEX orchestrator] signal_ingestion: {len(result.signals)} signals total")
        except Exception as e:
            err = f"signal_ingestion error: {e}"
            result.errors.append(err)
            result.signals = load_signals(niche)  # use what's already stored
            print(f"[CORTEX orchestrator] {err} (using {len(result.signals)} stored signals)")

    # ── Step 2: Gate 1 — quick signal check ───────────────────────────────────
    cost_so_far += _STEP_COSTS["gate_1"]
    g1_result = None
    try:
        g1_result = await gate_1(niche, market, agent=agent)
        result.steps_completed.append("gate_1")
        print(f"[CORTEX orchestrator] gate_1: {g1_result.score} | passed={g1_result.passed}")

        if not g1_result.passed:
            # Gate 1 red = stop before expensive D-4/D-5
            result.outcome = OUTCOME_PARKED
            result.reason = f"Gate 1 red: {g1_result.reason or 'insufficient signal volume or quality'}"
            result.steps_skipped += ["pain_clustering", "influencers", "disruption_scan", "gate_2", "opportunity_score"]
            _finalize(result, cost_so_far)
            return result

    except Exception as e:
        err = f"gate_1 error: {e}"
        result.errors.append(err)
        print(f"[CORTEX orchestrator] {err} (continuing past gate_1)")
        # Fail-open: continue if gate_1 errors

    # ── Step 3: Cluster signals (D-3) ─────────────────────────────────────────
    cost_so_far += _STEP_COSTS["pain_clustering"]
    if cost_so_far <= max_cost_eur:
        try:
            clusters = await cluster_and_store(
                signals=result.signals or [],
                niche=niche,
                market=market,
                agent=agent,
                use_llm=(agent is not None),
            )
            result.clusters = clusters
            result.pain_summary = build_pain_summary(clusters)
            result.steps_completed.append("pain_clustering")
            print(f"[CORTEX orchestrator] pain_clustering: {len(clusters)} clusters")
        except Exception as e:
            err = f"pain_clustering error: {e}"
            result.errors.append(err)
            print(f"[CORTEX orchestrator] {err}")
    else:
        result.steps_skipped.append("pain_clustering")

    # ── Step 4: Influencer monitoring (D-4) ───────────────────────────────────
    if skip_influencers:
        result.steps_skipped.append("influencers")
        print("[CORTEX orchestrator] D-4: skipped (skip_influencers=True)")
    else:
        cost_so_far += _STEP_COSTS["influencers"]
        if cost_so_far > max_cost_eur:
            result.steps_skipped.append("influencers")
            print("[CORTEX orchestrator] D-4: skipped (budget cap)")
        else:
            try:
                new_signals = await process_niche_influencers(
                    niche=niche,
                    market=market,
                    max_influencers=3,
                    max_videos_per_influencer=5,
                    agent=agent,
                )
                # Refresh signal list with influencer signals
                result.signals = load_signals(niche)
                # Re-cluster with enriched signals
                if new_signals:
                    clusters = await cluster_and_store(
                        signals=result.signals,
                        niche=niche,
                        market=market,
                        agent=agent,
                        use_llm=(agent is not None),
                    )
                    result.clusters = clusters
                    result.pain_summary = build_pain_summary(clusters)
                result.steps_completed.append("influencers")
                print(f"[CORTEX orchestrator] D-4: {len(new_signals)} new signals from influencers")
            except Exception as e:
                err = f"influencer_monitoring error: {e}"
                result.errors.append(err)
                print(f"[CORTEX orchestrator] {err}")

    # ── Step 5: Disruption scan (D-5) ─────────────────────────────────────────
    cost_so_far += _STEP_COSTS["disruption_scan"]
    if cost_so_far <= max_cost_eur:
        try:
            disruption_targets = await scan_disruption_targets(
                niche=niche,
                market=market,
                max_targets=5,
                agent=agent,
            )
            result.disruption_targets = disruption_targets
            result.disruption_summary = format_disruption_summary(disruption_targets, top_n=3)
            result.steps_completed.append("disruption_scan")
            print(f"[CORTEX orchestrator] D-5: {len(disruption_targets)} disruption targets scored")
        except Exception as e:
            err = f"disruption_scan error: {e}"
            result.errors.append(err)
            print(f"[CORTEX orchestrator] {err}")
    else:
        result.steps_skipped.append("disruption_scan")

    # ── Step 6: Gate 2 — CVS pre-score ────────────────────────────────────────
    cost_so_far += _STEP_COSTS["gate_2"]
    g2_result = None
    prescore = 0.0
    strategy = ""
    gate2_details: Dict[str, Any] = {}

    if cost_so_far <= max_cost_eur:
        try:
            # Build enriched context for gate_2 prompt
            enriched_pain = result.pain_summary or (
                f"{len(result.signals)} pain signals collected across multiple sources."
            )
            if result.disruption_summary:
                enriched_pain += f"\n\nDisruption context:\n{result.disruption_summary}"

            g2_result, prescore, strategy = await gate_2(
                niche=niche,
                market=market,
                pain_summary=enriched_pain,
                source="discovery_orchestrator",
                params=params,
                agent=agent,
            )
            result.strategy_type = strategy
            gate2_details = g2_result.details if g2_result else {}
            result.steps_completed.append("gate_2")
            print(
                f"[CORTEX orchestrator] gate_2: score={g2_result.score if g2_result else 'n/a'} "
                f"| prescore={prescore:.1f} | strategy={strategy}"
            )

            if g2_result and not g2_result.passed:
                result.outcome = OUTCOME_REJECTED
                result.reason = f"Gate 2 failed: {g2_result.reason or 'CVS score below threshold'}"
                result.steps_skipped.append("opportunity_score")
                _finalize(result, cost_so_far)
                return result

        except Exception as e:
            err = f"gate_2 error: {e}"
            result.errors.append(err)
            prescore = 30.0  # fallback
            print(f"[CORTEX orchestrator] {err} (using fallback prescore={prescore})")
    else:
        result.steps_skipped.append("gate_2")
        prescore = 30.0

    # ── Step 7: Score opportunity (D-6) ───────────────────────────────────────
    cost_so_far += _STEP_COSTS["opportunity_score"]
    candidate = _make_candidate(niche, market, result.signals, {}, prescore, strategy)

    if cost_so_far <= max_cost_eur:
        try:
            gate2_details.setdefault("switching_friction", "medium")
            gate2_details.setdefault("geographic_bonus", False)
            gate2_details.setdefault("cvs_prescore", prescore)
            gate2_details.setdefault("strategy_type", strategy)

            score = await score_opportunity(candidate, gate2_details, params, agent)
            apply_score_to_candidate(candidate, score, gate2_details)
            result.final_score = score.composite
            result.strategy_type = score.strategy_type or strategy
            candidate.strategy_type = result.strategy_type
            result.steps_completed.append("opportunity_score")
            print(f"[CORTEX orchestrator] opportunity_score: {score.composite:.1f}/100")

        except Exception as e:
            err = f"opportunity_score error: {e}"
            result.errors.append(err)
            candidate.cvs_prescore = prescore
            result.final_score = prescore
            print(f"[CORTEX orchestrator] {err} (using prescore as final score)")
    else:
        result.steps_skipped.append("opportunity_score")
        candidate.cvs_prescore = prescore
        result.final_score = prescore

    result.candidate = candidate

    # ── Step 8: Queue / reject ────────────────────────────────────────────────
    min_score = params.min_cvs_score if params else 40.0
    if (result.final_score or 0) >= min_score:
        add_to_queue(candidate)
        result.outcome = OUTCOME_QUEUED
        result.reason = (
            f"Queued with CVS score {result.final_score:.1f}/100 "
            f"(threshold {min_score:.0f}) | strategy: {result.strategy_type}"
        )
    else:
        result.outcome = OUTCOME_REJECTED
        result.reason = (
            f"Score {result.final_score:.1f}/100 below threshold {min_score:.0f}"
        )

    _finalize(result, cost_so_far)
    print(
        f"[CORTEX orchestrator] COMPLETE: outcome={result.outcome} | "
        f"score={(result.final_score or 0):.1f} | "
        f"cost~EUR{result.cost_estimate_eur:.3f}"
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_candidate(
    niche: str,
    market: str,
    signals: List[PainSignal],
    gate_scores: Dict[str, str],
    prescore: float,
    strategy: str,
) -> VentureCandidate:
    """Build a VentureCandidate from orchestrator data."""
    return VentureCandidate(
        name=f"{niche} — {market}",
        niche=niche,
        market=market,
        source="discovery_orchestrator",
        source_signals=signals[:20],   # cap to avoid bloated JSON
        gate_scores=gate_scores,
        cvs_prescore=prescore,
        strategy_type=strategy,
    )


def _finalize(result: DiscoveryResult, cost_so_far: float) -> None:
    """Set completion metadata on result."""
    result.cost_estimate_eur = round(cost_so_far, 4)
    result.completed_at = datetime.utcnow().isoformat()
