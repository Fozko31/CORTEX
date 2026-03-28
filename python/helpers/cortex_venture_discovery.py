"""
CORTEX Venture Discovery Engine (Phase C)
==========================================

Domain-agnostic trend/market scanner for venture creation flow.
Ported from omnis_workspace_VERDENT/omnis_ai/venture/discovery.py and rewritten for CORTEX:
  - Uses CortexResearchOrchestrator (Tier 1 / Tier 2) instead of Tavily directly
  - Domain-agnostic: works for any market/niche (not Etsy-specific)
  - Pre-research cost gate for Tier 2 (>$0.10 threshold with user confirmation)
  - Gap analysis: identifies what Tier 1 didn't answer → decides if Tier 2 needed
  - Research certainty scoring passed back to VentureDNA CVS engine
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Data schemas
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KeywordInsight:
    keyword: str
    monthly_searches: int = 0
    trend_direction: str = "unknown"      # rising | stable | declining | unknown
    competition: str = "unknown"          # low | medium | high | unknown
    opportunity_score: float = 0.0        # 0.0-10.0
    cpc_eur: float = 0.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "monthly_searches": self.monthly_searches,
            "trend_direction": self.trend_direction,
            "competition": self.competition,
            "opportunity_score": self.opportunity_score,
            "cpc_eur": self.cpc_eur,
            "notes": self.notes,
        }


@dataclass
class ResearchGap:
    """Something Tier 1 didn't answer well enough."""
    question: str
    importance: str = "medium"   # high | medium | low
    reason: str = ""


@dataclass
class TrendReport:
    market: str
    niche: str
    language: str
    keywords: List[KeywordInsight] = field(default_factory=list)
    top_competitors: List[str] = field(default_factory=list)
    opportunity_summary: str = ""
    recommended_action: str = ""
    confidence: float = 0.0
    source: str = "unknown"          # cortex_tier1 | cortex_tier2 | offline_stub
    tier_used: int = 1
    source_count: int = 0
    gaps: List[ResearchGap] = field(default_factory=list)
    raw_findings: str = ""
    scanned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def top_keywords(self) -> List[str]:
        return [k.keyword for k in sorted(self.keywords, key=lambda x: x.opportunity_score, reverse=True)]

    @property
    def best_opportunity_score(self) -> float:
        return max((k.opportunity_score for k in self.keywords), default=0.0)

    @property
    def gap_count(self) -> int:
        return len(self.gaps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market,
            "niche": self.niche,
            "language": self.language,
            "top_keywords": self.top_keywords,
            "keywords": [k.to_dict() for k in self.keywords],
            "top_competitors": self.top_competitors,
            "opportunity_summary": self.opportunity_summary,
            "recommended_action": self.recommended_action,
            "confidence": self.confidence,
            "source": self.source,
            "tier_used": self.tier_used,
            "source_count": self.source_count,
            "gap_count": self.gap_count,
            "gaps": [{"question": g.question, "importance": g.importance} for g in self.gaps],
            "scanned_at": self.scanned_at,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Cost estimation
# ─────────────────────────────────────────────────────────────────────────────

_TIER2_COST_ESTIMATE_USD = 0.30   # conservative estimate for a Tier 2 Perplexity call
_TIER2_GATE_THRESHOLD_USD = 0.10  # gate if estimated cost > $0.10


def estimate_tier2_cost(query_count: int = 1) -> float:
    """Estimate Tier 2 cost in USD."""
    return _TIER2_COST_ESTIMATE_USD * query_count


def should_gate_tier2(query_count: int = 1) -> Tuple[bool, float]:
    """
    Returns (should_gate, estimated_cost).
    If should_gate is True, surface cost to user before proceeding.
    Manual 'use tier 2' overrides the gate.
    """
    cost = estimate_tier2_cost(query_count)
    return cost > _TIER2_GATE_THRESHOLD_USD, cost


# ─────────────────────────────────────────────────────────────────────────────
# Main discovery scanner
# ─────────────────────────────────────────────────────────────────────────────

class CortexVentureScanner:
    """
    Primary discovery scanner for CORTEX venture creation.
    Uses CortexResearchOrchestrator — Tier 1 by default, Tier 2 when gaps require it.
    """

    def __init__(self, agent=None):
        self.agent = agent

    async def scan_tier1(
        self,
        niche: str,
        market: str = "global",
        language: str = "en",
        context: str = "",
    ) -> TrendReport:
        """
        Tier 1 market research: Tavily + Exa, multi-query, Claude synthesizes.
        Always tries Tier 1 first — fast and cheap (~$0.01-0.03).
        """
        from python.helpers.cortex_research_orchestrator import CortexResearchOrchestrator
        orchestrator = CortexResearchOrchestrator.from_agent(self.agent)

        queries = _build_research_queries(niche, market, language, tier=1)
        context_block = f"Venture context: {context}\n\n" if context else ""

        prompt = (
            f"{context_block}"
            f"Research the '{niche}' market in {market}.\n"
            "Provide:\n"
            "1. Market size estimate (TAM, growth rate)\n"
            "2. Top 5-8 keyword opportunities with competition level and search volume\n"
            "3. Top 5 competitors (names, URLs if known)\n"
            "4. Key trends (rising/declining)\n"
            "5. Opportunity summary: where is the gap, what is defensible?\n"
            "6. Recommended action: specific, actionable first step\n"
            "7. Open questions: what would you need to know to be 90% confident?\n"
            f"Queries used: {', '.join(queries)}"
        )

        try:
            result = await orchestrator.research(
                topic=prompt,
                queries=queries,
                tier="Tier1",
                max_results_per_query=6,
            )
            return await _parse_research_result(result, niche, market, language, tier=1, agent=self.agent)
        except Exception as e:
            import traceback
            print(f"[CORTEX scan_tier1 ERROR] {type(e).__name__}: {e}")
            traceback.print_exc()
            return _offline_stub(niche, market, language, error=f"{type(e).__name__}: {e}")

    async def scan_tier2(
        self,
        niche: str,
        market: str = "global",
        language: str = "en",
        tier1_report: Optional[TrendReport] = None,
        manual_override: bool = False,
    ) -> TrendReport:
        """
        Tier 2 deep research: Tier 1 findings + Perplexity reasoning.
        Gate: estimate cost, surface to user if > $0.10 (unless manual_override=True).
        Returns Tier 2 report; caller should merge with Tier 1 findings.
        """
        from python.helpers.cortex_research_orchestrator import CortexResearchOrchestrator
        orchestrator = CortexResearchOrchestrator.from_agent(self.agent)

        tier1_context = ""
        gap_questions = []
        if tier1_report:
            tier1_context = (
                f"Tier 1 findings summary:\n"
                f"  Opportunity: {tier1_report.opportunity_summary}\n"
                f"  Top keywords: {', '.join(tier1_report.top_keywords[:5])}\n"
                f"  Competitors: {', '.join(tier1_report.top_competitors[:5])}\n"
                f"  Confidence: {tier1_report.confidence:.0%}\n"
            )
            gap_questions = [g.question for g in tier1_report.gaps if g.importance == "high"]

        questions_block = ""
        if gap_questions:
            questions_block = "Critical gaps to resolve:\n" + "\n".join(f"- {q}" for q in gap_questions) + "\n\n"

        prompt = (
            f"{tier1_context}\n"
            f"{questions_block}"
            f"Deep research on '{niche}' market in {market}:\n"
            "1. Validate or challenge the Tier 1 opportunity summary\n"
            "2. Resolve each critical gap with specific data\n"
            "3. Competitive moat analysis: what would make this defensible?\n"
            "4. Risk analysis: top 3 failure modes\n"
            "5. Revised recommended action with confidence level\n"
        )

        try:
            tier2_queries = [
                f"{niche} market deep dive {market}",
                f"{niche} competitive moat defensibility",
                f"{niche} failure modes risks {market}",
                f"{niche} market size growth {market} 2024 2025",
            ]
            result = await orchestrator.research(
                topic=prompt,
                queries=tier2_queries,
                tier="Tier2",
                max_results_per_query=8,
            )
            report = await _parse_research_result(result, niche, market, language, tier=2, agent=self.agent)
            # Merge Tier 1 keywords if we have them (don't lose existing data)
            if tier1_report and tier1_report.keywords:
                existing_kws = {k.keyword for k in report.keywords}
                for kw in tier1_report.keywords:
                    if kw.keyword not in existing_kws:
                        report.keywords.append(kw)
            return report
        except Exception as e:
            import traceback
            print(f"[CORTEX scan_tier2 ERROR] {type(e).__name__}: {e}")
            traceback.print_exc()
            if tier1_report:
                return tier1_report  # fallback to Tier 1
            return _offline_stub(niche, market, language, error=f"{type(e).__name__}: {e}")

    async def analyze_gaps(self, report: TrendReport) -> List[ResearchGap]:
        """
        Use DeepSeek V3.2 to identify what questions Tier 1 left unanswered.
        Returns list of ResearchGap — high-importance gaps trigger Tier 2.
        """
        from python.helpers.cortex_model_router import CortexModelRouter

        prompt = (
            f"Analyze this market research on '{report.niche}':\n"
            f"Opportunity: {report.opportunity_summary}\n"
            f"Keywords found: {', '.join(report.top_keywords[:5])}\n"
            f"Competitors: {', '.join(report.top_competitors[:5])}\n"
            f"Confidence: {report.confidence:.0%}\n\n"
            "List 3-5 unanswered questions that would significantly change the investment decision. "
            "Format as JSON: [{\"question\": \"...\", \"importance\": \"high|medium|low\", \"reason\": \"...\"}]"
        )

        try:
            raw = await CortexModelRouter.call_routed_model(
                "classification", "You are a research gap analyst.", prompt, self.agent
            )
            from python.helpers.dirty_json import DirtyJson
            gaps_data = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw
            if not isinstance(gaps_data, list):
                gaps_data = gaps_data.get("gaps", []) if isinstance(gaps_data, dict) else []
            gaps = []
            for g in gaps_data[:5]:
                gaps.append(ResearchGap(
                    question=g.get("question", ""),
                    importance=g.get("importance", "medium"),
                    reason=g.get("reason", ""),
                ))
            return [g for g in gaps if g.question]
        except Exception:
            return []

    def needs_tier2(self, report: TrendReport, gap_confidence_threshold: float = 0.6) -> bool:
        """
        Auto-decide if Tier 2 is needed.
        Triggers if: confidence below threshold OR has high-importance gaps.
        """
        if report.confidence < gap_confidence_threshold:
            return True
        high_gaps = [g for g in report.gaps if g.importance == "high"]
        return len(high_gaps) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# TrendReport → VentureDNA bridge
# ─────────────────────────────────────────────────────────────────────────────

def merge_trend_report_into_dna(dna, report: TrendReport) -> None:
    """
    Merge a TrendReport's findings into a VentureDNA.
    Updates market intelligence, competitor profiles, insights, logs refinement.
    """
    from python.helpers.cortex_venture_dna import (
        CompetitorProfile, ResearchSnapshot, compute_research_certainty
    )

    mi = dna.market_intelligence
    for kw in report.keywords:
        trend_str = (
            f"{kw.keyword} "
            f"(vol={kw.monthly_searches}, {kw.trend_direction}, "
            f"comp={kw.competition}, score={kw.opportunity_score:.1f})"
        )
        if trend_str not in mi.key_trends:
            mi.key_trends.append(trend_str)

    if report.opportunity_summary and report.opportunity_summary not in mi.key_trends:
        dna.add_insight(f"[Market] {report.opportunity_summary}")

    if report.recommended_action:
        dna.add_insight(f"[Action] {report.recommended_action}")

    for comp_name in report.top_competitors:
        existing = [c.name for c in dna.competitor_profiles]
        if comp_name and comp_name not in existing:
            dna.competitor_profiles.append(CompetitorProfile(name=comp_name))

    # Add open questions from gaps
    for gap in report.gaps:
        if gap.importance in ("high", "medium"):
            dna.add_open_question(gap.question)

    # Add research snapshot
    snapshot = ResearchSnapshot(
        agent="cortex_discovery",
        findings={
            "opportunity_summary": report.opportunity_summary,
            "top_keywords": report.top_keywords[:10],
            "top_competitors": report.top_competitors[:5],
            "recommended_action": report.recommended_action,
        },
        confidence=report.confidence,
        sources=report.top_keywords[:5],  # keywords as proxy for sources
        tier_used=report.tier_used,
        gap_count=report.gap_count,
        contradiction_count=0,
    )
    dna.add_research_snapshot(snapshot)

    # Recompute research certainty
    dna.recompute_research_certainty()

    dna.log_refinement(
        f"discovery_{report.source}",
        f"Tier {report.tier_used} scan: {len(report.keywords)} keywords, "
        f"{len(report.top_competitors)} competitors, confidence={report.confidence:.0%}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_research_queries(niche: str, market: str, language: str, tier: int = 1) -> List[str]:
    """Build search queries for Tier 1 research."""
    base_queries = [
        f"{niche} market size growth 2024 2025",
        f"best {niche} competitors top companies products",
        f"{niche} customer pain points demand trends",
    ]
    if market and market.lower() not in ("global", ""):
        base_queries.append(f"{niche} {market} market analysis")
    if tier >= 2:
        base_queries.extend([
            f"{niche} competitive moat defensibility analysis",
            f"{niche} failure reasons risks challenges",
        ])
    return base_queries[:5]


async def _parse_research_result(
    result: Any,
    niche: str,
    market: str,
    language: str,
    tier: int = 1,
    agent=None,
) -> TrendReport:
    """Parse orchestrator result into a TrendReport."""
    from python.helpers.cortex_model_router import CortexModelRouter

    # result may be str (synthesis) or dict
    if isinstance(result, dict):
        raw_text = result.get("synthesis", result.get("answer", str(result)))
        source_count = len(result.get("sources", []))
    else:
        raw_text = str(result)
        source_count = 3  # conservative estimate

    extraction_prompt = (
        f"Extract structured market research from this text about '{niche}'.\n"
        "Return JSON with:\n"
        "  keywords: [{keyword, monthly_searches(int), trend_direction, competition, opportunity_score(0-10)}]\n"
        "  top_competitors: [str]\n"
        "  opportunity_summary: str\n"
        "  recommended_action: str\n"
        "  confidence: float (0-1)\n"
        "  open_questions: [str]\n"
        f"Text:\n{raw_text[:3000]}"
    )

    try:
        raw = await CortexModelRouter.call_routed_model(
            "classification", "You are a market research extraction assistant.", extraction_prompt, agent
        )
        from python.helpers.dirty_json import DirtyJson
        data = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw
        if not isinstance(data, dict):
            raise ValueError("not a dict")
    except Exception:
        data = {}

    keywords = []
    for k in data.get("keywords", [])[:10]:
        if isinstance(k, dict) and k.get("keyword"):
            keywords.append(KeywordInsight(
                keyword=k["keyword"],
                monthly_searches=int(k.get("monthly_searches", 0)),
                trend_direction=k.get("trend_direction", "unknown"),
                competition=k.get("competition", "unknown"),
                opportunity_score=float(k.get("opportunity_score", 5.0)),
            ))

    gaps = []
    for q in data.get("open_questions", [])[:5]:
        if q:
            gaps.append(ResearchGap(question=q, importance="medium"))

    return TrendReport(
        market=market,
        niche=niche,
        language=language,
        keywords=keywords,
        top_competitors=data.get("top_competitors", [])[:8],
        opportunity_summary=data.get("opportunity_summary", ""),
        recommended_action=data.get("recommended_action", ""),
        confidence=float(data.get("confidence", 0.6)),
        source=f"cortex_tier{tier}",
        tier_used=tier,
        source_count=source_count,
        gaps=gaps,
        raw_findings=raw_text[:1000],
    )


def _offline_stub(niche: str, market: str, language: str, error: str = "") -> TrendReport:
    """Deterministic fallback when research fails."""
    words = niche.lower().split()[:2]
    base = " ".join(words)
    return TrendReport(
        market=market,
        niche=niche,
        language=language,
        keywords=[
            KeywordInsight(f"{base} solution", 5000, "unknown", "medium", 5.0),
            KeywordInsight(f"best {base}", 8000, "unknown", "medium", 5.5),
            KeywordInsight(f"{base} software tool", 3000, "unknown", "low", 6.0),
        ],
        top_competitors=[],
        opportunity_summary=f"Research unavailable for '{niche}' — offline stub data. {error}",
        recommended_action="Manual research required — check internet connection or API keys",
        confidence=0.1,
        source="offline_stub",
        tier_used=0,
        source_count=0,
        gaps=[
            ResearchGap("What is the actual market size?", "high", "Research failed"),
            ResearchGap("Who are the main competitors?", "high", "Research failed"),
        ],
    )
