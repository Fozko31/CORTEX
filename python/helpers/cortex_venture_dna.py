"""
CORTEX VentureDNA — Extended Living Knowledge Entity
=====================================================

Ported from omnis_workspace_VERDENT/omnis_ai/venture/dna.py and extended for CORTEX:
  - Extended CVS scoring: 8 dimensions (original 5 weighted + 3 CORTEX Advantage unweighted)
  - Research certainty score (computed from actual research depth)
  - VentureHealthPulse — per-venture computed health summary
  - FailurePattern — dormant schema, activates in Phase G
  - CrossVenturePattern — cross-venture synthesis output
  - Two SurfSense spaces per venture (DNA + ops)
  - Persistence to usr/memory/cortex_main/ventures/
  - Visual score renderer (text-based)
  - CORTEX capability lens scoring
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# CVS Scoring
# ─────────────────────────────────────────────────────────────────────────────

# Original 5 weighted dimensions (sum to 1.0)
_CVS_WEIGHTS: Dict[str, float] = {
    "market_size":         0.25,
    "problem_severity":    0.30,
    "solution_uniqueness": 0.20,
    "implementation_ease": 0.15,
    "distribution_clarity":0.10,
}

_CVS_THRESHOLDS = {"auto": 75.0, "review": 60.0, "discard": 35.0}


@dataclass
class CVSScore:
    """
    Extended CVS scoring — 8 dimensions, each 0-100.
    Composite CVS = weighted sum of the original 5.
    CORTEX Advantage metrics (risk_level, ai_setup_autonomy, ai_run_autonomy) displayed separately.
    """
    # Original 5 (weighted composite)
    market_size: float = 0.0           # TAM + growth rate
    problem_severity: float = 0.0     # Pain depth + frequency
    solution_uniqueness: float = 0.0  # Defensibility + moat
    implementation_ease: float = 0.0  # Time + complexity
    distribution_clarity: float = 0.0 # Go-to-market path

    # CORTEX Advantage metrics (unweighted — display separately)
    risk_level: float = 0.0           # 0 = max risk, 100 = minimal risk (inverse of danger)
    ai_setup_autonomy: float = 0.0    # 0-100: how much CORTEX can build/configure autonomously
    ai_run_autonomy: float = 0.0      # 0-100: how much CORTEX can operate/optimize autonomously

    # Research certainty (computed from actual research depth)
    research_certainty: float = 0.0   # 0-100

    # Scoring metadata
    scored_at: Optional[str] = None
    scoring_notes: str = ""

    def composite_cvs(self) -> float:
        """Weighted sum of original 5 dimensions (0-100)."""
        score = (
            self.market_size         * _CVS_WEIGHTS["market_size"] +
            self.problem_severity    * _CVS_WEIGHTS["problem_severity"] +
            self.solution_uniqueness * _CVS_WEIGHTS["solution_uniqueness"] +
            self.implementation_ease * _CVS_WEIGHTS["implementation_ease"] +
            self.distribution_clarity* _CVS_WEIGHTS["distribution_clarity"]
        )
        return round(score, 1)

    def verdict(self) -> str:
        cvs = self.composite_cvs()
        if cvs >= _CVS_THRESHOLDS["auto"]:
            return "AUTO_PROCEED"
        elif cvs >= _CVS_THRESHOLDS["review"]:
            return "REVIEW"
        elif cvs >= _CVS_THRESHOLDS["discard"]:
            return "CONDITIONAL"
        else:
            return "DISCARD"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_size": self.market_size,
            "problem_severity": self.problem_severity,
            "solution_uniqueness": self.solution_uniqueness,
            "implementation_ease": self.implementation_ease,
            "distribution_clarity": self.distribution_clarity,
            "risk_level": self.risk_level,
            "ai_setup_autonomy": self.ai_setup_autonomy,
            "ai_run_autonomy": self.ai_run_autonomy,
            "research_certainty": self.research_certainty,
            "composite_cvs": self.composite_cvs(),
            "verdict": self.verdict(),
            "scored_at": self.scored_at,
            "scoring_notes": self.scoring_notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CVSScore":
        return cls(
            market_size=d.get("market_size", 0.0),
            problem_severity=d.get("problem_severity", 0.0),
            solution_uniqueness=d.get("solution_uniqueness", 0.0),
            implementation_ease=d.get("implementation_ease", 0.0),
            distribution_clarity=d.get("distribution_clarity", 0.0),
            risk_level=d.get("risk_level", 0.0),
            ai_setup_autonomy=d.get("ai_setup_autonomy", 0.0),
            ai_run_autonomy=d.get("ai_run_autonomy", 0.0),
            research_certainty=d.get("research_certainty", 0.0),
            scored_at=d.get("scored_at"),
            scoring_notes=d.get("scoring_notes", ""),
        )

    def render(self) -> str:
        """ASCII visual of all 8 CVS dimensions."""
        def bar(score: float, width: int = 20) -> str:
            filled = int(round(score / 100.0 * width))
            return "█" * filled + "░" * (width - filled)

        cvs = self.composite_cvs()
        verdict = self.verdict()
        lines = [
            "━━━ CVS SCORE BREAKDOWN ━━━━━━━━━━━━━━━━━━━━━━",
            f"  Market Size         {bar(self.market_size)}  {self.market_size:>5.1f}/100",
            f"  Problem Severity    {bar(self.problem_severity)}  {self.problem_severity:>5.1f}/100",
            f"  Solution Uniqueness {bar(self.solution_uniqueness)}  {self.solution_uniqueness:>5.1f}/100",
            f"  Implementation Ease {bar(self.implementation_ease)}  {self.implementation_ease:>5.1f}/100",
            f"  Distribution Clarity{bar(self.distribution_clarity)}  {self.distribution_clarity:>5.1f}/100",
            f"",
            f"  COMPOSITE CVS       {bar(cvs)}  {cvs:>5.1f}/100  [{verdict}]",
            f"  Research Certainty  {bar(self.research_certainty)}  {self.research_certainty:>5.1f}/100",
            f"",
            f"━━━ CORTEX ADVANTAGE ━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"  Risk Level          {bar(self.risk_level)}  {self.risk_level:>5.1f}/100  (100=low risk)",
            f"  AI Setup Autonomy   {bar(self.ai_setup_autonomy)}  {self.ai_setup_autonomy:>5.1f}/100",
            f"  AI Run Autonomy     {bar(self.ai_run_autonomy)}  {self.ai_run_autonomy:>5.1f}/100",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        return "\n".join(lines)


def compute_research_certainty(
    source_count: int,
    tier_used: int,         # 1 or 2
    gap_count: int,
    contradiction_count: int,
) -> float:
    """Compute research certainty 0-100 from actual research depth."""
    base = min(source_count * 8.0, 50.0)       # up to 50 pts from sources
    tier_bonus = 20.0 if tier_used >= 2 else 0.0
    gap_penalty = min(gap_count * 5.0, 25.0)
    contradiction_penalty = min(contradiction_count * 8.0, 20.0)
    score = base + tier_bonus - gap_penalty - contradiction_penalty
    return round(max(0.0, min(100.0, score)), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Sub-schemas (ported from Omnis source, adapted)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MarketIntelligence:
    market_size_estimate: str = ""
    key_trends: List[str] = field(default_factory=list)
    seasonality_notes: str = ""
    platform_dynamics: str = ""
    information_arbitrage_gaps: List[str] = field(default_factory=list)
    researched_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_size_estimate": self.market_size_estimate,
            "key_trends": self.key_trends,
            "seasonality_notes": self.seasonality_notes,
            "platform_dynamics": self.platform_dynamics,
            "information_arbitrage_gaps": self.information_arbitrage_gaps,
            "researched_at": self.researched_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MarketIntelligence":
        return cls(
            market_size_estimate=d.get("market_size_estimate", ""),
            key_trends=d.get("key_trends", []),
            seasonality_notes=d.get("seasonality_notes", ""),
            platform_dynamics=d.get("platform_dynamics", ""),
            information_arbitrage_gaps=d.get("information_arbitrage_gaps", []),
            researched_at=d.get("researched_at"),
        )


@dataclass
class CompetitorProfile:
    name: str = ""
    url: str = ""
    platform: str = ""
    price_range: str = ""
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    review_count: int = 0
    avg_rating: float = 0.0
    notes: str = ""
    scraped_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "url": self.url, "platform": self.platform,
            "price_range": self.price_range, "strengths": self.strengths,
            "weaknesses": self.weaknesses, "review_count": self.review_count,
            "avg_rating": self.avg_rating, "notes": self.notes,
            "scraped_at": self.scraped_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CompetitorProfile":
        return cls(
            name=d.get("name", ""), url=d.get("url", ""), platform=d.get("platform", ""),
            price_range=d.get("price_range", ""), strengths=d.get("strengths", []),
            weaknesses=d.get("weaknesses", []), review_count=d.get("review_count", 0),
            avg_rating=d.get("avg_rating", 0.0), notes=d.get("notes", ""),
            scraped_at=d.get("scraped_at"),
        )


@dataclass
class ICP:
    primary_segment: str = ""
    demographics: str = ""
    psychographics: str = ""
    pain_points: List[str] = field(default_factory=list)
    desired_outcomes: List[str] = field(default_factory=list)
    buying_triggers: List[str] = field(default_factory=list)
    price_sensitivity: str = ""
    channels: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_segment": self.primary_segment, "demographics": self.demographics,
            "psychographics": self.psychographics, "pain_points": self.pain_points,
            "desired_outcomes": self.desired_outcomes, "buying_triggers": self.buying_triggers,
            "price_sensitivity": self.price_sensitivity, "channels": self.channels,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ICP":
        return cls(
            primary_segment=d.get("primary_segment", ""), demographics=d.get("demographics", ""),
            psychographics=d.get("psychographics", ""), pain_points=d.get("pain_points", []),
            desired_outcomes=d.get("desired_outcomes", []),
            buying_triggers=d.get("buying_triggers", []),
            price_sensitivity=d.get("price_sensitivity", ""), channels=d.get("channels", []),
        )


@dataclass
class WebAsset:
    url: str = ""
    asset_type: str = "website"
    status: str = "unknown"
    traffic_estimate: str = ""
    seo_score: Optional[float] = None
    notes: str = ""
    analyzed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url, "asset_type": self.asset_type, "status": self.status,
            "traffic_estimate": self.traffic_estimate, "seo_score": self.seo_score,
            "notes": self.notes, "analyzed_at": self.analyzed_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WebAsset":
        return cls(
            url=d.get("url", ""), asset_type=d.get("asset_type", "website"),
            status=d.get("status", "unknown"), traffic_estimate=d.get("traffic_estimate", ""),
            seo_score=d.get("seo_score"), notes=d.get("notes", ""),
            analyzed_at=d.get("analyzed_at"),
        )


@dataclass
class IngestedDocument:
    filename: str = ""
    doc_type: str = "pdf"
    source_url: str = ""
    ingested_at: Optional[str] = None
    surfsense_doc_id: Optional[str] = None
    summary: str = ""
    key_extracts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename, "doc_type": self.doc_type,
            "source_url": self.source_url, "ingested_at": self.ingested_at,
            "surfsense_doc_id": self.surfsense_doc_id,
            "summary": self.summary, "key_extracts": self.key_extracts,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IngestedDocument":
        return cls(
            filename=d.get("filename", ""), doc_type=d.get("doc_type", "pdf"),
            source_url=d.get("source_url", ""), ingested_at=d.get("ingested_at"),
            surfsense_doc_id=d.get("surfsense_doc_id"),
            summary=d.get("summary", ""), key_extracts=d.get("key_extracts", []),
        )


@dataclass
class ResearchSnapshot:
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent: str = ""
    findings: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    sources: List[str] = field(default_factory=list)
    tier_used: int = 1
    gap_count: int = 0
    contradiction_count: int = 0
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id, "agent": self.agent,
            "findings": self.findings, "confidence": self.confidence,
            "sources": self.sources, "tier_used": self.tier_used,
            "gap_count": self.gap_count, "contradiction_count": self.contradiction_count,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ResearchSnapshot":
        obj = cls(
            snapshot_id=d.get("snapshot_id", str(uuid.uuid4())[:8]),
            agent=d.get("agent", ""), findings=d.get("findings", {}),
            confidence=d.get("confidence", 0.5), sources=d.get("sources", []),
            tier_used=d.get("tier_used", 1), gap_count=d.get("gap_count", 0),
            contradiction_count=d.get("contradiction_count", 0),
            timestamp=d.get("timestamp"),
        )
        return obj


@dataclass
class RefinementEntry:
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    source: str = ""
    change_summary: str = ""
    detail: str = ""
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id, "source": self.source,
            "change_summary": self.change_summary, "detail": self.detail,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RefinementEntry":
        obj = cls(
            entry_id=d.get("entry_id", str(uuid.uuid4())[:8]),
            source=d.get("source", ""), change_summary=d.get("change_summary", ""),
            detail=d.get("detail", ""), timestamp=d.get("timestamp"),
        )
        return obj


@dataclass
class FinancialModel:
    revenue_streams: List[str] = field(default_factory=list)
    primary_revenue_type: str = ""
    unit_economics: Dict[str, Any] = field(default_factory=dict)
    estimated_monthly_revenue_eur: float = 0.0
    estimated_monthly_cost_eur: float = 0.0
    break_even_units: Optional[int] = None
    pricing_strategy: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "revenue_streams": self.revenue_streams,
            "primary_revenue_type": self.primary_revenue_type,
            "unit_economics": self.unit_economics,
            "estimated_monthly_revenue_eur": self.estimated_monthly_revenue_eur,
            "estimated_monthly_cost_eur": self.estimated_monthly_cost_eur,
            "break_even_units": self.break_even_units,
            "pricing_strategy": self.pricing_strategy,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FinancialModel":
        return cls(
            revenue_streams=d.get("revenue_streams", []),
            primary_revenue_type=d.get("primary_revenue_type", ""),
            unit_economics=d.get("unit_economics", {}),
            estimated_monthly_revenue_eur=d.get("estimated_monthly_revenue_eur", 0.0),
            estimated_monthly_cost_eur=d.get("estimated_monthly_cost_eur", 0.0),
            break_even_units=d.get("break_even_units"),
            pricing_strategy=d.get("pricing_strategy", ""),
        )


@dataclass
class KellyParams:
    edge_estimate: float = 0.0
    win_rate: float = 0.5
    avg_win_eur: float = 0.0
    avg_loss_eur: float = 0.0
    kelly_fraction: float = 0.0
    half_kelly_fraction: float = 0.0
    confidence_in_edge: float = 0.0
    last_computed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_estimate": self.edge_estimate, "win_rate": self.win_rate,
            "avg_win_eur": self.avg_win_eur, "avg_loss_eur": self.avg_loss_eur,
            "kelly_fraction": self.kelly_fraction,
            "half_kelly_fraction": self.half_kelly_fraction,
            "confidence_in_edge": self.confidence_in_edge,
            "last_computed_at": self.last_computed_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KellyParams":
        return cls(
            edge_estimate=d.get("edge_estimate", 0.0), win_rate=d.get("win_rate", 0.5),
            avg_win_eur=d.get("avg_win_eur", 0.0), avg_loss_eur=d.get("avg_loss_eur", 0.0),
            kelly_fraction=d.get("kelly_fraction", 0.0),
            half_kelly_fraction=d.get("half_kelly_fraction", 0.0),
            confidence_in_edge=d.get("confidence_in_edge", 0.0),
            last_computed_at=d.get("last_computed_at"),
        )


@dataclass
class VentureResource:
    """Named credential/integration scoped to this venture. credential_ref is opaque — never the raw token."""
    alias: str = ""
    resource_type: str = "custom"    # gmail | sheets | calendar | api | bank | custom
    display_name: str = ""
    credential_ref: str = ""         # opaque reference — stored locally only
    connected: bool = False
    connected_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alias": self.alias, "resource_type": self.resource_type,
            "display_name": self.display_name,
            # credential_ref intentionally NOT included in SurfSense-pushed docs
            "connected": self.connected, "connected_at": self.connected_at,
            "notes": self.notes,
        }

    def to_dict_full(self) -> Dict[str, Any]:
        """Full dict including credential_ref — for local storage only."""
        d = self.to_dict()
        d["credential_ref"] = self.credential_ref
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VentureResource":
        return cls(
            alias=d.get("alias", ""), resource_type=d.get("resource_type", "custom"),
            display_name=d.get("display_name", ""),
            credential_ref=d.get("credential_ref", ""),
            connected=d.get("connected", False), connected_at=d.get("connected_at"),
            notes=d.get("notes", ""),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Phase G schemas (dormant in Phase C)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FailurePattern:
    """
    DORMANT — activates in Phase G epistemic flywheel.
    Schema defined here so it can be referenced; no data written in Phase C.
    """
    pattern_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    venture_id: str = ""
    pattern_type: str = ""        # market_miss | execution_fail | timing | capital | team
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    frequency: int = 1
    last_seen_at: Optional[str] = None
    prevention_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id, "venture_id": self.venture_id,
            "pattern_type": self.pattern_type, "description": self.description,
            "context": self.context, "frequency": self.frequency,
            "last_seen_at": self.last_seen_at, "prevention_notes": self.prevention_notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FailurePattern":
        return cls(
            pattern_id=d.get("pattern_id", str(uuid.uuid4())[:8]),
            venture_id=d.get("venture_id", ""),
            pattern_type=d.get("pattern_type", ""),
            description=d.get("description", ""),
            context=d.get("context", {}), frequency=d.get("frequency", 1),
            last_seen_at=d.get("last_seen_at"), prevention_notes=d.get("prevention_notes", ""),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Cross-venture synthesis
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CrossVenturePattern:
    """Output of cross-venture synthesis — pushed to cortex_cross_venture SurfSense space."""
    pattern_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    pattern_type: str = ""          # market_overlap | skill_reuse | risk_correlation | opportunity
    description: str = ""
    venture_ids: List[str] = field(default_factory=list)
    venture_names: List[str] = field(default_factory=list)
    confidence: float = 0.5
    action_suggestion: str = ""
    synthesized_at: Optional[str] = None

    def __post_init__(self):
        if self.synthesized_at is None:
            self.synthesized_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id, "pattern_type": self.pattern_type,
            "description": self.description, "venture_ids": self.venture_ids,
            "venture_names": self.venture_names, "confidence": self.confidence,
            "action_suggestion": self.action_suggestion, "synthesized_at": self.synthesized_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CrossVenturePattern":
        return cls(
            pattern_id=d.get("pattern_id", str(uuid.uuid4())[:8]),
            pattern_type=d.get("pattern_type", ""),
            description=d.get("description", ""),
            venture_ids=d.get("venture_ids", []),
            venture_names=d.get("venture_names", []),
            confidence=d.get("confidence", 0.5),
            action_suggestion=d.get("action_suggestion", ""),
            synthesized_at=d.get("synthesized_at"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Venture Health Pulse
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VentureHealthPulse:
    venture_id: str = ""
    venture_name: str = ""
    dna_completeness_pct: float = 0.0        # % of required DNA fields populated
    cvs_composite: float = 0.0
    cvs_verdict: str = ""
    cvs_confidence: float = 0.0              # based on research_certainty
    open_decisions_count: int = 0
    estimated_monthly_revenue_eur: float = 0.0
    outcomes_logged_count: int = 0
    last_activity_at: Optional[str] = None
    next_recommended_action: str = ""
    computed_at: Optional[str] = None

    def __post_init__(self):
        if self.computed_at is None:
            self.computed_at = datetime.now(timezone.utc).isoformat()

    def render(self) -> str:
        lines = [
            f"━━━ VENTURE HEALTH: {self.venture_name.upper()} ━━━━━━━━━━━━━",
            f"  DNA Completeness    {self.dna_completeness_pct:>5.1f}%",
            f"  CVS Score           {self.cvs_composite:>5.1f}/100  [{self.cvs_verdict}]",
            f"  CVS Confidence      {self.cvs_confidence:>5.1f}%",
            f"  Open Decisions      {self.open_decisions_count}",
            f"  Monthly Revenue     €{self.estimated_monthly_revenue_eur:,.2f}",
            f"  Outcomes Logged     {self.outcomes_logged_count}",
            f"  Last Activity       {self.last_activity_at or 'N/A'}",
            f"",
            f"  Next Action: {self.next_recommended_action}",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "venture_id": self.venture_id, "venture_name": self.venture_name,
            "dna_completeness_pct": self.dna_completeness_pct,
            "cvs_composite": self.cvs_composite, "cvs_verdict": self.cvs_verdict,
            "cvs_confidence": self.cvs_confidence,
            "open_decisions_count": self.open_decisions_count,
            "estimated_monthly_revenue_eur": self.estimated_monthly_revenue_eur,
            "outcomes_logged_count": self.outcomes_logged_count,
            "last_activity_at": self.last_activity_at,
            "next_recommended_action": self.next_recommended_action,
            "computed_at": self.computed_at,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Core VentureDNA entity
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VentureDNA:
    """
    CORTEX Living Venture Knowledge Entity.

    Design:
      - confidence_level reflects how deeply CORTEX understands this venture (0→1)
      - user_goals and user_constraints are EXPLICIT — never overridden by inference
      - open_questions are what CORTEX still needs to know to reach 90% confidence
      - research_snapshots and refinement_log are append-only (full history preserved)
      - Two SurfSense spaces: surfsense_dna_space_name + surfsense_ops_space_name
      - autonomy_level is a first-class field (0-4: 0=manual, 4=full auto)
      - cvs_score holds extended 8-dimension scoring
    """

    venture_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""

    # Classification
    venture_type: str = "generic"     # ecommerce | saas | local_services | content | trading | generic
    stage: str = "idea"               # idea | validated | building | launched | scaling | paused | archived
    status: str = "active"            # active | paused | archived
    language: str = "en"
    confidence_level: float = 0.1     # 0.0-1.0: how well CORTEX understands this venture

    # Autonomy (first-class field)
    autonomy_level: int = 0           # 0=manual, 1=assist, 2=semi-auto, 3=auto, 4=full-auto

    # Timestamps
    created_at: Optional[str] = None
    last_refined_at: Optional[str] = None

    # Explicit user intent — NEVER overridden
    user_goals: List[str] = field(default_factory=list)
    user_constraints: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    key_insights: List[str] = field(default_factory=list)

    # Deep market intelligence
    market_intelligence: MarketIntelligence = field(default_factory=MarketIntelligence)
    competitor_profiles: List[CompetitorProfile] = field(default_factory=list)
    ideal_customer_profile: ICP = field(default_factory=ICP)

    # Assets
    websites: List[WebAsset] = field(default_factory=list)
    documents: List[IngestedDocument] = field(default_factory=list)
    compounding_assets: List[str] = field(default_factory=list)

    # Financial + Kelly
    financial_model: FinancialModel = field(default_factory=FinancialModel)
    kelly_params: KellyParams = field(default_factory=KellyParams)

    # Extended CVS scoring (8 dimensions)
    cvs_score: CVSScore = field(default_factory=CVSScore)

    # Research history (append-only)
    research_snapshots: List[ResearchSnapshot] = field(default_factory=list)
    refinement_log: List[RefinementEntry] = field(default_factory=list)

    # SurfSense spaces (two per venture: DNA + ops)
    surfsense_dna_space_name: Optional[str] = None    # cortex_venture_{name}_dna
    surfsense_ops_space_name: Optional[str] = None    # cortex_venture_{name}_ops
    surfsense_dna_space_id: Optional[int] = None
    surfsense_ops_space_id: Optional[int] = None

    # Resources (credentials stored locally only — never pushed to SurfSense)
    resources: List[VentureResource] = field(default_factory=list)

    # Flexible domain-specific data
    domain_specifics: Dict[str, Any] = field(default_factory=dict)

    # Portfolio metadata
    venture_template: str = ""
    last_visited_at: Optional[str] = None
    attention_score: float = 0.0
    active_automation_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.confidence_level = max(0.0, min(1.0, self.confidence_level))
        self.autonomy_level = max(0, min(4, self.autonomy_level))
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if self.last_refined_at is None:
            self.last_refined_at = self.created_at
        # Set default SurfSense space names from venture name
        safe_name = _safe_space_name(self.name)
        if self.surfsense_dna_space_name is None and self.name:
            self.surfsense_dna_space_name = f"cortex_venture_{safe_name}_dna"
        if self.surfsense_ops_space_name is None and self.name:
            self.surfsense_ops_space_name = f"cortex_venture_{safe_name}_ops"

    # ── Mutation helpers ──────────────────────────────────────────────────────

    def add_insight(self, insight: str) -> None:
        if insight and insight not in self.key_insights:
            self.key_insights.append(insight)
            self._touch()

    def add_open_question(self, question: str) -> None:
        if question and question not in self.open_questions:
            self.open_questions.append(question)

    def resolve_question(self, question: str) -> None:
        self.open_questions = [q for q in self.open_questions if q != question]

    def log_refinement(self, source: str, change_summary: str, detail: str = "") -> None:
        entry = RefinementEntry(source=source, change_summary=change_summary, detail=detail)
        self.refinement_log.append(entry)
        self._touch()

    def add_research_snapshot(self, snapshot: ResearchSnapshot) -> None:
        self.research_snapshots.append(snapshot)
        self._touch()

    def set_confidence(self, level: float) -> None:
        self.confidence_level = max(0.0, min(1.0, level))
        self._touch()

    def _touch(self) -> None:
        self.last_refined_at = datetime.now(timezone.utc).isoformat()

    # ── CVS helpers ───────────────────────────────────────────────────────────

    def update_cvs(self, **kwargs: float) -> None:
        """Update CVS dimensions. Pass dimension names as kwargs with 0-100 values."""
        for key, val in kwargs.items():
            if hasattr(self.cvs_score, key):
                setattr(self.cvs_score, key, max(0.0, min(100.0, float(val))))
        self.cvs_score.scored_at = datetime.now(timezone.utc).isoformat()
        self._touch()

    def recompute_research_certainty(self) -> float:
        """Recompute research_certainty from all snapshots."""
        if not self.research_snapshots:
            return 0.0
        latest = self.research_snapshots[-1]
        total_sources = sum(len(s.sources) for s in self.research_snapshots)
        max_tier = max(s.tier_used for s in self.research_snapshots)
        total_gaps = sum(s.gap_count for s in self.research_snapshots)
        total_contradictions = sum(s.contradiction_count for s in self.research_snapshots)
        cert = compute_research_certainty(
            source_count=total_sources,
            tier_used=max_tier,
            gap_count=total_gaps,
            contradiction_count=total_contradictions,
        )
        self.cvs_score.research_certainty = cert
        return cert

    def render_cvs(self) -> str:
        return self.cvs_score.render()

    # ── Health Pulse ──────────────────────────────────────────────────────────

    def compute_health_pulse(self, open_decisions_count: int = 0, outcomes_count: int = 0) -> VentureHealthPulse:
        completeness = self._dna_completeness()
        cvs = self.cvs_score.composite_cvs()
        return VentureHealthPulse(
            venture_id=self.venture_id,
            venture_name=self.name,
            dna_completeness_pct=completeness,
            cvs_composite=cvs,
            cvs_verdict=self.cvs_score.verdict(),
            cvs_confidence=self.cvs_score.research_certainty,
            open_decisions_count=open_decisions_count,
            estimated_monthly_revenue_eur=self.financial_model.estimated_monthly_revenue_eur,
            outcomes_logged_count=outcomes_count,
            last_activity_at=self.last_refined_at,
            next_recommended_action=self._suggest_next_action(completeness, cvs),
        )

    def _dna_completeness(self) -> float:
        """Estimate how complete the DNA is as a percentage."""
        checks = [
            bool(self.user_goals),
            bool(self.market_intelligence.market_size_estimate),
            bool(self.market_intelligence.key_trends),
            bool(self.competitor_profiles),
            bool(self.ideal_customer_profile.primary_segment),
            bool(self.key_insights),
            self.cvs_score.composite_cvs() > 0,
            bool(self.financial_model.revenue_streams),
            not bool(self.open_questions),  # bonus if all questions resolved
        ]
        return round(sum(checks) / len(checks) * 100, 1)

    def _suggest_next_action(self, completeness: float, cvs: float) -> str:
        if completeness < 40:
            return "Complete market intelligence — research market size and competitors"
        if not self.ideal_customer_profile.primary_segment:
            return "Define ideal customer profile — run ICP discovery research"
        if self.open_questions:
            return f"Resolve {len(self.open_questions)} open questions — trigger Tier 2 research"
        if cvs < _CVS_THRESHOLDS["review"]:
            return "CVS below review threshold — reassess solution uniqueness and distribution"
        if cvs >= _CVS_THRESHOLDS["auto"] and not self.financial_model.revenue_streams:
            return "Strong CVS — define revenue model and unit economics"
        return "Venture ready — begin building or activate automation pack"

    # ── Brief summary for system prompt injection ─────────────────────────────

    def brief_summary(self, max_chars: int = 200) -> str:
        """200-char DNA summary for per-turn system prompt injection."""
        cvs = self.cvs_score.composite_cvs()
        verdict = self.cvs_score.verdict()
        goals_str = "; ".join(self.user_goals[:2]) if self.user_goals else "undefined"
        summary = (
            f"Venture: {self.name} | Type: {self.venture_type} | Stage: {self.stage} | "
            f"CVS: {cvs:.0f}/100 [{verdict}] | Goals: {goals_str}"
        )
        return summary[:max_chars]

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "venture_id": self.venture_id,
            "name": self.name,
            "venture_type": self.venture_type,
            "stage": self.stage,
            "status": self.status,
            "language": self.language,
            "confidence_level": self.confidence_level,
            "autonomy_level": self.autonomy_level,
            "created_at": self.created_at,
            "last_refined_at": self.last_refined_at,
            "user_goals": self.user_goals,
            "user_constraints": self.user_constraints,
            "open_questions": self.open_questions,
            "key_insights": self.key_insights,
            "market_intelligence": self.market_intelligence.to_dict(),
            "competitor_profiles": [c.to_dict() for c in self.competitor_profiles],
            "ideal_customer_profile": self.ideal_customer_profile.to_dict(),
            "websites": [w.to_dict() for w in self.websites],
            "documents": [doc.to_dict() for doc in self.documents],
            "compounding_assets": self.compounding_assets,
            "financial_model": self.financial_model.to_dict(),
            "kelly_params": self.kelly_params.to_dict(),
            "cvs_score": self.cvs_score.to_dict(),
            "research_snapshots": [s.to_dict() for s in self.research_snapshots],
            "refinement_log": [r.to_dict() for r in self.refinement_log],
            "surfsense_dna_space_name": self.surfsense_dna_space_name,
            "surfsense_ops_space_name": self.surfsense_ops_space_name,
            "surfsense_dna_space_id": self.surfsense_dna_space_id,
            "surfsense_ops_space_id": self.surfsense_ops_space_id,
            # resources serialized without credential_ref (safe for general use)
            "resources": [r.to_dict() for r in self.resources],
            "domain_specifics": self.domain_specifics,
            "venture_template": self.venture_template,
            "last_visited_at": self.last_visited_at,
            "attention_score": self.attention_score,
            "active_automation_ids": self.active_automation_ids,
        }

    def to_dict_with_credentials(self) -> Dict[str, Any]:
        """Full dict including credential_refs — for local storage only."""
        d = self.to_dict()
        d["resources"] = [r.to_dict_full() for r in self.resources]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict_with_credentials(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VentureDNA":
        obj = cls(
            venture_id=d.get("venture_id", str(uuid.uuid4())[:8]),
            name=d.get("name", ""),
            venture_type=d.get("venture_type", "generic"),
            stage=d.get("stage", "idea"),
            status=d.get("status", "active"),
            language=d.get("language", "en"),
            confidence_level=d.get("confidence_level", 0.1),
            autonomy_level=d.get("autonomy_level", 0),
            created_at=d.get("created_at"),
            last_refined_at=d.get("last_refined_at"),
            user_goals=d.get("user_goals", []),
            user_constraints=d.get("user_constraints", []),
            open_questions=d.get("open_questions", []),
            key_insights=d.get("key_insights", []),
            compounding_assets=d.get("compounding_assets", []),
            domain_specifics=d.get("domain_specifics", {}),
            surfsense_dna_space_name=d.get("surfsense_dna_space_name"),
            surfsense_ops_space_name=d.get("surfsense_ops_space_name"),
            surfsense_dna_space_id=d.get("surfsense_dna_space_id"),
            surfsense_ops_space_id=d.get("surfsense_ops_space_id"),
            venture_template=d.get("venture_template", ""),
            last_visited_at=d.get("last_visited_at"),
            attention_score=d.get("attention_score", 0.0),
            active_automation_ids=d.get("active_automation_ids", []),
        )
        if "market_intelligence" in d and d["market_intelligence"]:
            obj.market_intelligence = MarketIntelligence.from_dict(d["market_intelligence"])
        if "competitor_profiles" in d:
            obj.competitor_profiles = [CompetitorProfile.from_dict(c) for c in d["competitor_profiles"]]
        if "ideal_customer_profile" in d and d["ideal_customer_profile"]:
            obj.ideal_customer_profile = ICP.from_dict(d["ideal_customer_profile"])
        if "websites" in d:
            obj.websites = [WebAsset.from_dict(w) for w in d["websites"]]
        if "documents" in d:
            obj.documents = [IngestedDocument.from_dict(doc) for doc in d["documents"]]
        if "financial_model" in d and d["financial_model"]:
            obj.financial_model = FinancialModel.from_dict(d["financial_model"])
        if "kelly_params" in d and d["kelly_params"]:
            obj.kelly_params = KellyParams.from_dict(d["kelly_params"])
        if "cvs_score" in d and d["cvs_score"]:
            obj.cvs_score = CVSScore.from_dict(d["cvs_score"])
        if "research_snapshots" in d:
            obj.research_snapshots = [ResearchSnapshot.from_dict(s) for s in d["research_snapshots"]]
        if "refinement_log" in d:
            obj.refinement_log = [RefinementEntry.from_dict(r) for r in d["refinement_log"]]
        if "resources" in d:
            obj.resources = [VentureResource.from_dict(r) for r in d["resources"]]
        return obj

    @classmethod
    def from_json(cls, json_str: str) -> "VentureDNA":
        return cls.from_dict(json.loads(json_str))

    def __repr__(self) -> str:
        return (
            f"VentureDNA(id={self.venture_id!r}, name={self.name!r}, "
            f"type={self.venture_type!r}, stage={self.stage!r}, "
            f"confidence={self.confidence_level:.0%}, "
            f"cvs={self.cvs_score.composite_cvs():.1f}, "
            f"questions={len(self.open_questions)})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────────────

def _ventures_dir(agent=None) -> str:
    """Return path to ventures storage directory."""
    if agent is not None:
        try:
            memory_dir = getattr(agent.config, "agent_memory_subdir", "cortex_main") or "cortex_main"
            base = os.path.join("usr", "memory", memory_dir, "ventures")
        except Exception:
            base = os.path.join("usr", "memory", "cortex_main", "ventures")
    else:
        base = os.path.join("usr", "memory", "cortex_main", "ventures")
    os.makedirs(base, exist_ok=True)
    return base


def save_venture(dna: VentureDNA, agent=None) -> str:
    """Save VentureDNA to disk. Returns path."""
    vdir = _ventures_dir(agent)
    safe = _safe_space_name(dna.name) or dna.venture_id
    path = os.path.join(vdir, f"{safe}.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(dna.to_json())
    return path


def load_venture(name_or_id: str, agent=None) -> Optional[VentureDNA]:
    """Load VentureDNA by venture name slug or venture_id."""
    vdir = _ventures_dir(agent)
    # Try by safe name first
    safe = _safe_space_name(name_or_id)
    path = os.path.join(vdir, f"{safe}.json")
    if not os.path.exists(path):
        # Try by venture_id — scan all files
        for fname in os.listdir(vdir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(vdir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("venture_id") == name_or_id or d.get("name") == name_or_id:
                    return VentureDNA.from_dict(d)
            except Exception:
                continue
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return VentureDNA.from_dict(json.load(f))
    except Exception:
        return None


def list_ventures(agent=None) -> List[VentureDNA]:
    """Load all ventures from disk."""
    vdir = _ventures_dir(agent)
    ventures = []
    for fname in os.listdir(vdir):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(vdir, fname), encoding="utf-8") as f:
                ventures.append(VentureDNA.from_dict(json.load(f)))
        except Exception:
            continue
    return sorted(ventures, key=lambda v: v.last_refined_at or "", reverse=True)


def delete_venture(name_or_id: str, agent=None) -> bool:
    """Delete a venture from disk. Returns True if deleted."""
    vdir = _ventures_dir(agent)
    safe = _safe_space_name(name_or_id)
    path = os.path.join(vdir, f"{safe}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Cross-venture synthesis
# ─────────────────────────────────────────────────────────────────────────────

async def synthesize_cross_venture_patterns(ventures: List[VentureDNA], agent=None) -> List[CrossVenturePattern]:
    """
    Synthesize patterns across all ventures using DeepSeek V3.2.
    Called after any venture create/update.
    Returns list of CrossVenturePattern — caller pushes to cortex_cross_venture SurfSense space.
    """
    if len(ventures) < 2:
        return []

    venture_summaries = []
    for v in ventures:
        venture_summaries.append({
            "name": v.name,
            "type": v.venture_type,
            "market": v.market_intelligence.market_size_estimate,
            "trends": v.market_intelligence.key_trends[:3],
            "cvs": v.cvs_score.composite_cvs(),
            "ai_setup": v.cvs_score.ai_setup_autonomy,
            "ai_run": v.cvs_score.ai_run_autonomy,
            "goals": v.user_goals[:2],
            "insights": v.key_insights[:3],
        })

    prompt = (
        "Analyze these ventures and identify cross-venture patterns: "
        "market overlaps, shared skills, risk correlations, or portfolio opportunities.\n"
        "Return a JSON array of pattern objects with keys: "
        "pattern_type, description, venture_names, confidence (0-1), action_suggestion.\n"
        "Limit to top 3 most actionable patterns.\n\n"
        f"Ventures:\n{json.dumps(venture_summaries, ensure_ascii=False)}"
    )

    try:
        from python.helpers.cortex_model_router import CortexModelRouter
        result = await CortexModelRouter.call_routed_model(
            "classification", "You are a cross-venture pattern analyst.", prompt, agent
        )
        from python.cortex.dirty_json import DirtyJson
        raw = DirtyJson.parse_string(result) if isinstance(result, str) else result
        if not isinstance(raw, list):
            raw = raw.get("patterns", []) if isinstance(raw, dict) else []

        patterns = []
        for p in raw[:3]:
            vnames = p.get("venture_names", [])
            vids = [v.venture_id for v in ventures if v.name in vnames]
            patterns.append(CrossVenturePattern(
                pattern_type=p.get("pattern_type", "opportunity"),
                description=p.get("description", ""),
                venture_ids=vids,
                venture_names=vnames,
                confidence=float(p.get("confidence", 0.5)),
                action_suggestion=p.get("action_suggestion", ""),
            ))
        return patterns
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_space_name(name: str) -> str:
    """Convert venture name to safe lowercase alphanumeric slug for space names and filenames."""
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")[:40]
    return s
