"""
CORTEX Discovery Params — Phase D Data Structures + Persistence
================================================================

All dataclasses for the Venture Discovery Engine:
  - VentureDiscoveryParameters: user-defined search criteria
  - PainSignal: a single extracted pain point from any source
  - InfluencerWatch: a tracked influencer account
  - VentureCandidate: a scored opportunity in the queue

Storage layout:
  usr/memory/cortex_main/discovery/
    params.json
    params_history/v{N}__{timestamp}.json
    queue.json          (status: pending_review)
    rejected.json
    parked.json
    accepted.json
    influencers.json
    signals/{niche_slug}.json
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

_DISCOVERY_DIR = os.path.join("usr", "memory", "cortex_main", "discovery")
_PARAMS_FILE = os.path.join(_DISCOVERY_DIR, "params.json")
_PARAMS_HISTORY_DIR = os.path.join(_DISCOVERY_DIR, "params_history")
_QUEUE_FILE = os.path.join(_DISCOVERY_DIR, "queue.json")
_REJECTED_FILE = os.path.join(_DISCOVERY_DIR, "rejected.json")
_PARKED_FILE = os.path.join(_DISCOVERY_DIR, "parked.json")
_ACCEPTED_FILE = os.path.join(_DISCOVERY_DIR, "accepted.json")
_INFLUENCERS_FILE = os.path.join(_DISCOVERY_DIR, "influencers.json")
_SIGNALS_DIR = os.path.join(_DISCOVERY_DIR, "signals")


def _ensure_dirs() -> None:
    for d in [_DISCOVERY_DIR, _PARAMS_HISTORY_DIR, _SIGNALS_DIR]:
        os.makedirs(d, exist_ok=True)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:50]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# VentureDiscoveryParameters
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VentureDiscoveryParameters:
    """
    User-defined criteria that drive all discovery modes.
    Saved to disk and reused across sessions until explicitly updated.
    Each update archives the previous version.
    """
    market_domains: List[str] = field(default_factory=list)
    geography: str = "global"
    min_cvs_score: float = 45.0
    min_ai_run_autonomy: float = 50.0
    max_capital_requirement: Optional[float] = None   # EUR, None = no cap
    languages: List[str] = field(default_factory=lambda: ["en"])
    excluded_domains: List[str] = field(default_factory=list)
    strategy_preferences: List[str] = field(default_factory=list)
    autonomy_weight: float = 70.0                     # 0-100 weight for AI autonomy in ranking
    budget_cap_nightly_eur: float = 3.00              # Hard max for Mode 2 per night
    target_niches: List[str] = field(default_factory=list)  # Specific niches for autonomous loop
    created_at: str = field(default_factory=_now)
    last_updated: str = field(default_factory=_now)
    version: int = 1

    # ── serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_domains": self.market_domains,
            "geography": self.geography,
            "min_cvs_score": self.min_cvs_score,
            "min_ai_run_autonomy": self.min_ai_run_autonomy,
            "max_capital_requirement": self.max_capital_requirement,
            "languages": self.languages,
            "excluded_domains": self.excluded_domains,
            "strategy_preferences": self.strategy_preferences,
            "autonomy_weight": self.autonomy_weight,
            "budget_cap_nightly_eur": self.budget_cap_nightly_eur,
            "target_niches": self.target_niches,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VentureDiscoveryParameters":
        return cls(
            market_domains=d.get("market_domains", []),
            geography=d.get("geography", "global"),
            min_cvs_score=float(d.get("min_cvs_score", 45.0)),
            min_ai_run_autonomy=float(d.get("min_ai_run_autonomy", 50.0)),
            max_capital_requirement=d.get("max_capital_requirement"),
            languages=d.get("languages", ["en"]),
            excluded_domains=d.get("excluded_domains", []),
            strategy_preferences=d.get("strategy_preferences", []),
            autonomy_weight=float(d.get("autonomy_weight", 70.0)),
            budget_cap_nightly_eur=float(d.get("budget_cap_nightly_eur", 3.00)),
            target_niches=d.get("target_niches", []),
            created_at=d.get("created_at", _now()),
            last_updated=d.get("last_updated", _now()),
            version=int(d.get("version", 1)),
        )

    # ── persistence ──────────────────────────────────────────────────────────

    def save(self) -> None:
        _ensure_dirs()
        with open(_PARAMS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def save_and_archive(self) -> None:
        """Archive current version to history, then save new version."""
        _ensure_dirs()
        existing = VentureDiscoveryParameters.load()
        if existing:
            ts = existing.last_updated.replace(":", "-").replace(".", "-")[:19]
            archive_path = os.path.join(
                _PARAMS_HISTORY_DIR, f"v{existing.version}__{ts}.json"
            )
            with open(archive_path, "w", encoding="utf-8") as f:
                json.dump(existing.to_dict(), f, indent=2)
        self.save()

    @classmethod
    def load(cls) -> Optional["VentureDiscoveryParameters"]:
        if not os.path.exists(_PARAMS_FILE):
            return None
        try:
            with open(_PARAMS_FILE, encoding="utf-8") as f:
                return cls.from_dict(json.load(f))
        except Exception:
            return None

    def update(self, **kwargs) -> "VentureDiscoveryParameters":
        """Return a new params object with updated fields, version incremented."""
        data = self.to_dict()
        data.update(kwargs)
        data["version"] = self.version + 1
        data["last_updated"] = _now()
        data["created_at"] = self.created_at   # preserve original
        return VentureDiscoveryParameters.from_dict(data)

    def summary(self) -> str:
        domains = ", ".join(self.market_domains) if self.market_domains else "any"
        strategies = ", ".join(self.strategy_preferences) if self.strategy_preferences else "any"
        cap = f"€{self.max_capital_requirement:.0f}" if self.max_capital_requirement else "no cap"
        return (
            f"Domains: {domains} | Geography: {self.geography} | "
            f"Min CVS: {self.min_cvs_score:.0f} | Min AI autonomy: {self.min_ai_run_autonomy:.0f}% | "
            f"Capital cap: {cap} | Strategies: {strategies} | "
            f"Nightly budget: €{self.budget_cap_nightly_eur:.2f} | v{self.version}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# PainSignal
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PainSignal:
    """
    A single extracted pain point from any signal source.
    Stored per-niche in signals/{slug}.json for cross-source dedup + temporal tracking.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:10])
    source: str = ""        # "reddit", "g2", "capterra", "app_store", "producthunt",
                            # "influencer", "twitter", "manual"
    source_url: str = ""
    raw_text: str = ""
    extracted_pain: str = ""
    tool_mentioned: Optional[str] = None     # Product being complained about
    paying_evidence: bool = False            # Evidence source is currently paying for something
    date: str = field(default_factory=_now)
    strength: int = 1                        # 1=single mention … 5=cross-source recurring

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "source_url": self.source_url,
            "raw_text": self.raw_text,
            "extracted_pain": self.extracted_pain,
            "tool_mentioned": self.tool_mentioned,
            "paying_evidence": self.paying_evidence,
            "date": self.date,
            "strength": self.strength,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PainSignal":
        return cls(
            id=d.get("id", str(uuid.uuid4())[:10]),
            source=d.get("source", ""),
            source_url=d.get("source_url", ""),
            raw_text=d.get("raw_text", ""),
            extracted_pain=d.get("extracted_pain", ""),
            tool_mentioned=d.get("tool_mentioned"),
            paying_evidence=bool(d.get("paying_evidence", False)),
            date=d.get("date", _now()),
            strength=int(d.get("strength", 1)),
        )


def save_signals(niche: str, signals: List[PainSignal]) -> None:
    _ensure_dirs()
    path = os.path.join(_SIGNALS_DIR, f"{_slug(niche)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([s.to_dict() for s in signals], f, indent=2)


def load_signals(niche: str) -> List[PainSignal]:
    path = os.path.join(_SIGNALS_DIR, f"{_slug(niche)}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return [PainSignal.from_dict(d) for d in json.load(f)]
    except Exception:
        return []


def append_signals(niche: str, new_signals: List[PainSignal]) -> List[PainSignal]:
    """Append new signals, dedup by source_url. Return full updated list."""
    existing = load_signals(niche)
    seen_urls = {s.source_url for s in existing if s.source_url}
    added = [s for s in new_signals if s.source_url not in seen_urls]
    merged = existing + added
    save_signals(niche, merged)
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# InfluencerWatch
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InfluencerWatch:
    """A tracked influencer account. Monitored for new content between cycles."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:10])
    platform: str = ""       # "youtube", "twitter", "substack"
    handle: str = ""
    channel_id: Optional[str] = None
    channel_url: str = ""
    niche: str = ""
    last_checked: str = field(default_factory=_now)
    last_video_id: Optional[str] = None      # Dedup for YouTube
    subscriber_count: Optional[int] = None
    active: bool = True
    added_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "handle": self.handle,
            "channel_id": self.channel_id,
            "channel_url": self.channel_url,
            "niche": self.niche,
            "last_checked": self.last_checked,
            "last_video_id": self.last_video_id,
            "subscriber_count": self.subscriber_count,
            "active": self.active,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InfluencerWatch":
        return cls(
            id=d.get("id", str(uuid.uuid4())[:10]),
            platform=d.get("platform", ""),
            handle=d.get("handle", ""),
            channel_id=d.get("channel_id"),
            channel_url=d.get("channel_url", ""),
            niche=d.get("niche", ""),
            last_checked=d.get("last_checked", _now()),
            last_video_id=d.get("last_video_id"),
            subscriber_count=d.get("subscriber_count"),
            active=bool(d.get("active", True)),
            added_at=d.get("added_at", _now()),
        )


def save_influencers(influencers: List[InfluencerWatch]) -> None:
    _ensure_dirs()
    with open(_INFLUENCERS_FILE, "w", encoding="utf-8") as f:
        json.dump([i.to_dict() for i in influencers], f, indent=2)


def load_influencers() -> List[InfluencerWatch]:
    if not os.path.exists(_INFLUENCERS_FILE):
        return []
    try:
        with open(_INFLUENCERS_FILE, encoding="utf-8") as f:
            return [InfluencerWatch.from_dict(d) for d in json.load(f)]
    except Exception:
        return []


def add_influencer(influencer: InfluencerWatch) -> None:
    existing = load_influencers()
    # Dedup by channel_url
    if any(i.channel_url == influencer.channel_url for i in existing):
        return
    save_influencers(existing + [influencer])


# ─────────────────────────────────────────────────────────────────────────────
# VentureCandidate
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VentureCandidate:
    """
    A scored venture opportunity in the discovery queue.
    Moves through: pending_review → accepted / rejected / parked.
    Accepted candidates carry research_context into venture_create.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:10])
    name: str = ""
    source: str = ""        # "autonomous", "pain_mining", "disruption", "influencer",
                            # "geographic", "manual"
    source_signals: List[PainSignal] = field(default_factory=list)
    niche: str = ""
    market: str = "global"
    language: str = "en"
    strategy_type: str = ""  # From strategy taxonomy (e.g., "SaaS Wrapper", "Fast Follower")

    # Gate results
    gate_scores: Dict[str, str] = field(default_factory=dict)
    # e.g., {"gate_0": "pass", "gate_1": "pass", "gate_2": "yellow"}

    # Scoring
    cvs_prescore: float = 0.0
    opportunity_summary: str = ""
    switching_friction_notes: str = ""
    geographic_bonus: bool = False

    # Lifecycle
    status: str = "pending_review"   # "pending_review" | "accepted" | "rejected" | "parked"
    park_reason: Optional[str] = None
    park_revisit_condition: Optional[str] = None
    park_revisit_date: Optional[str] = None          # ISO date string
    rejection_reason: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    # Research context: full Tier 1 output if research already ran — passed to venture_create
    research_context: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "source_signals": [s.to_dict() for s in self.source_signals],
            "niche": self.niche,
            "market": self.market,
            "language": self.language,
            "strategy_type": self.strategy_type,
            "gate_scores": self.gate_scores,
            "cvs_prescore": self.cvs_prescore,
            "opportunity_summary": self.opportunity_summary,
            "switching_friction_notes": self.switching_friction_notes,
            "geographic_bonus": self.geographic_bonus,
            "status": self.status,
            "park_reason": self.park_reason,
            "park_revisit_condition": self.park_revisit_condition,
            "park_revisit_date": self.park_revisit_date,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "research_context": self.research_context,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VentureCandidate":
        return cls(
            id=d.get("id", str(uuid.uuid4())[:10]),
            name=d.get("name", ""),
            source=d.get("source", ""),
            source_signals=[PainSignal.from_dict(s) for s in d.get("source_signals", [])],
            niche=d.get("niche", ""),
            market=d.get("market", "global"),
            language=d.get("language", "en"),
            strategy_type=d.get("strategy_type", ""),
            gate_scores=d.get("gate_scores", {}),
            cvs_prescore=float(d.get("cvs_prescore", 0.0)),
            opportunity_summary=d.get("opportunity_summary", ""),
            switching_friction_notes=d.get("switching_friction_notes", ""),
            geographic_bonus=bool(d.get("geographic_bonus", False)),
            status=d.get("status", "pending_review"),
            park_reason=d.get("park_reason"),
            park_revisit_condition=d.get("park_revisit_condition"),
            park_revisit_date=d.get("park_revisit_date"),
            rejection_reason=d.get("rejection_reason"),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
            research_context=d.get("research_context"),
        )

    def short_summary(self) -> str:
        geo = " 🌍" if self.geographic_bonus else ""
        strat = f" [{self.strategy_type}]" if self.strategy_type else ""
        score = f"{self.cvs_prescore:.0f}"
        return f"[{self.id}] {self.name} — CVS pre: {score}{strat}{geo} | {self.source} | {self.market}"


# ─────────────────────────────────────────────────────────────────────────────
# Queue Persistence (queue / rejected / parked / accepted)
# ─────────────────────────────────────────────────────────────────────────────

def _load_candidates(path: str) -> List[VentureCandidate]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return [VentureCandidate.from_dict(d) for d in json.load(f)]
    except Exception:
        return []


def _save_candidates(path: str, candidates: List[VentureCandidate]) -> None:
    _ensure_dirs()
    with open(path, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in candidates], f, indent=2)


# ── Queue (pending_review) ────────────────────────────────────────────────────

def load_queue() -> List[VentureCandidate]:
    return _load_candidates(_QUEUE_FILE)


def save_queue(candidates: List[VentureCandidate]) -> None:
    _save_candidates(_QUEUE_FILE, candidates)


def add_to_queue(candidate: VentureCandidate) -> None:
    queue = load_queue()
    if any(c.id == candidate.id for c in queue):
        return
    candidate.status = "pending_review"
    candidate.updated_at = _now()
    queue.append(candidate)
    # Keep sorted by cvs_prescore descending
    queue.sort(key=lambda c: c.cvs_prescore, reverse=True)
    save_queue(queue)


def remove_from_queue(candidate_id: str) -> Optional[VentureCandidate]:
    queue = load_queue()
    found = next((c for c in queue if c.id == candidate_id), None)
    if found:
        save_queue([c for c in queue if c.id != candidate_id])
    return found


# ── Rejected ─────────────────────────────────────────────────────────────────

def load_rejected() -> List[VentureCandidate]:
    return _load_candidates(_REJECTED_FILE)


def reject_candidate(candidate_id: str, reason: str = "") -> bool:
    candidate = remove_from_queue(candidate_id)
    if not candidate:
        # Also check parked
        parked = load_parked()
        candidate = next((c for c in parked if c.id == candidate_id), None)
        if candidate:
            _save_candidates(_PARKED_FILE, [c for c in parked if c.id != candidate_id])
    if not candidate:
        return False
    candidate.status = "rejected"
    candidate.rejection_reason = reason
    candidate.updated_at = _now()
    rejected = load_rejected()
    rejected.append(candidate)
    _save_candidates(_REJECTED_FILE, rejected)
    return True


def is_already_rejected(niche: str, market: str) -> bool:
    """Check if a niche+market combo was already rejected — prevents re-surfacing."""
    rejected = load_rejected()
    return any(
        c.niche.lower() == niche.lower() and c.market.lower() == market.lower()
        for c in rejected
    )


# ── Parked ────────────────────────────────────────────────────────────────────

def load_parked() -> List[VentureCandidate]:
    return _load_candidates(_PARKED_FILE)


def park_candidate(
    candidate_id: str,
    reason: str,
    revisit_condition: Optional[str] = None,
    revisit_date: Optional[str] = None,
) -> bool:
    candidate = remove_from_queue(candidate_id)
    if not candidate:
        return False
    candidate.status = "parked"
    candidate.park_reason = reason
    candidate.park_revisit_condition = revisit_condition
    candidate.park_revisit_date = revisit_date
    candidate.updated_at = _now()
    parked = load_parked()
    parked.append(candidate)
    _save_candidates(_PARKED_FILE, parked)
    return True


def unpark_candidate(candidate_id: str) -> bool:
    """Move from parked back to queue for review."""
    parked = load_parked()
    candidate = next((c for c in parked if c.id == candidate_id), None)
    if not candidate:
        return False
    _save_candidates(_PARKED_FILE, [c for c in parked if c.id != candidate_id])
    add_to_queue(candidate)
    return True


def get_parked_due_for_revisit() -> List[VentureCandidate]:
    """Return parked ventures whose revisit_date has passed."""
    today = datetime.now(timezone.utc).date().isoformat()
    return [
        c for c in load_parked()
        if c.park_revisit_date and c.park_revisit_date <= today
    ]


# ── Accepted ──────────────────────────────────────────────────────────────────

def load_accepted() -> List[VentureCandidate]:
    return _load_candidates(_ACCEPTED_FILE)


def accept_candidate(candidate_id: str) -> Optional[VentureCandidate]:
    """Move from queue to accepted. Returns candidate (with research_context) for venture_create."""
    candidate = remove_from_queue(candidate_id)
    if not candidate:
        return None
    candidate.status = "accepted"
    candidate.updated_at = _now()
    accepted = load_accepted()
    accepted.append(candidate)
    _save_candidates(_ACCEPTED_FILE, accepted)
    return candidate
