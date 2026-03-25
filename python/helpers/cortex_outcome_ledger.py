"""
CORTEX Outcome Ledger (Phase C)
================================

SQLite-backed ledger for all venture outcomes, decisions, and capital signals.
Ported from omnis_workspace_VERDENT/omnis_ai/venture/outcome_ledger.py.

Changes from source:
  - Removed Omnis-specific SurfSense sync (CORTEX uses cortex_surfsense_client)
  - Added DecisionEvent — captures venture creation confirmations and key decisions
  - CORTEX-native DB path (usr/memory/cortex_main/cortex_ledger.db)
  - Agent-aware singleton: ledger path derived from agent config
  - Kelly math kept inline (no separate module needed at this stage)
  - record_venture_creation() convenience method for creation flow
"""

from __future__ import annotations

import math
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

EventType = str   # revenue | cost | conversion | impression | click
HITLDecision = str  # approve | modify | reject


@dataclass
class OutcomeEvent:
    venture_id: str
    event_type: EventType
    amount_eur: float = 0.0
    run_id: str = ""
    stage: str = ""
    listing_id: Optional[str] = None
    platform: str = ""
    notes: str = ""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "venture_id": self.venture_id,
            "run_id": self.run_id,
            "stage": self.stage,
            "event_type": self.event_type,
            "amount_eur": self.amount_eur,
            "listing_id": self.listing_id,
            "platform": self.platform,
            "notes": self.notes,
            "occurred_at": self.occurred_at,
        }


@dataclass
class HITLLogEntry:
    venture_id: str
    decision: HITLDecision
    item_summary: str = ""
    reason: str = ""
    run_id: str = ""
    stage: str = ""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decided_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "venture_id": self.venture_id,
            "run_id": self.run_id,
            "stage": self.stage,
            "decision": self.decision,
            "item_summary": self.item_summary,
            "reason": self.reason,
            "decided_at": self.decided_at,
        }


@dataclass
class DecisionEvent:
    """
    Captures key venture decisions (creation confirmation, pivots, resource allocation).
    Distinct from OutcomeEvent (which is financial) and HITLLogEntry (which is AI→user approval).
    DecisionEvents are user-driven strategic choices.
    """
    venture_id: str
    decision_type: str          # venture_created | pivot | resource_allocated | goal_updated | archived
    summary: str = ""
    detail: str = ""
    cvs_at_decision: float = 0.0
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decided_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "venture_id": self.venture_id,
            "decision_type": self.decision_type,
            "summary": self.summary,
            "detail": self.detail,
            "cvs_at_decision": self.cvs_at_decision,
            "decided_at": self.decided_at,
        }


@dataclass
class KellySignal:
    venture_id: str
    total_revenue_eur: float
    total_cost_eur: float
    conversions: int
    impressions: int
    roi: float
    win_rate: float
    suggested_kelly_fraction: float
    half_kelly_fraction: float = 0.0
    expected_value: float = 0.0
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def net_profit_eur(self) -> float:
        return self.total_revenue_eur - self.total_cost_eur

    def to_dict(self) -> Dict[str, Any]:
        return {
            "venture_id": self.venture_id,
            "total_revenue_eur": self.total_revenue_eur,
            "total_cost_eur": self.total_cost_eur,
            "net_profit_eur": self.net_profit_eur,
            "conversions": self.conversions,
            "impressions": self.impressions,
            "roi": self.roi,
            "win_rate": self.win_rate,
            "suggested_kelly_fraction": self.suggested_kelly_fraction,
            "half_kelly_fraction": self.half_kelly_fraction,
            "expected_value": self.expected_value,
            "computed_at": self.computed_at,
        }

    def render(self) -> str:
        verdict = "STRONG_APPROVE" if self.suggested_kelly_fraction >= 0.15 else \
                  "CONDITIONAL" if self.suggested_kelly_fraction >= 0.05 else \
                  "REJECT"
        lines = [
            f"━━━ KELLY SIGNAL: {self.venture_id} ━━━━━━━━━━━━━━━━━━",
            f"  Revenue          €{self.total_revenue_eur:,.2f}",
            f"  Cost             €{self.total_cost_eur:,.2f}",
            f"  Net Profit       €{self.net_profit_eur:,.2f}",
            f"  ROI              {self.roi:.1%}",
            f"  Win Rate         {self.win_rate:.1%}",
            f"  Expected Value   €{self.expected_value:,.2f}",
            f"  Kelly Fraction   {self.suggested_kelly_fraction:.3f}  (half: {self.half_kelly_fraction:.3f})",
            f"  Verdict          {verdict}",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Kelly math (ported from omnis_v12_JARVIS/omnis_ai/modules/kelly_mathematical_framework.py)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_expected_value(
    probability_success: float,
    revenue_success: float,
    revenue_failure: float,
    cost: float,
) -> float:
    """EV = p × (Rₛ - C) + (1-p) × (Rᶠ - C)"""
    p = max(0.0, min(1.0, probability_success))
    return p * (revenue_success - cost) + (1 - p) * (revenue_failure - cost)


def calculate_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    fractional: float = 0.5,
    cap: float = 0.25,
) -> float:
    """
    Kelly fraction = (p × b - q) / b  where b = avg_win / avg_loss
    fractional: apply fractional Kelly (default 0.5 = half-Kelly for safety)
    cap: hard cap at 25% of budget
    """
    if avg_loss <= 0 or avg_win <= 0:
        return 0.0
    b = avg_win / avg_loss
    q = 1 - win_rate
    raw = (win_rate * b - q) / b
    full_kelly = max(0.0, min(raw, cap))
    return round(full_kelly * fractional, 4)


def calculate_variance(
    probability_success: float,
    gain_success: float,
    gain_failure: float,
    expected_value: float,
) -> float:
    """σ² = p × (Gₛ - EV)² + q × (Gᶠ - EV)²"""
    p = max(0.0, min(1.0, probability_success))
    q = 1 - p
    return p * (gain_success - expected_value) ** 2 + q * (gain_failure - expected_value) ** 2


def calculate_std_dev(variance: float) -> float:
    return math.sqrt(max(0.0, variance))


# ─────────────────────────────────────────────────────────────────────────────
# SQLite schema
# ─────────────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS outcome_events (
    event_id     TEXT PRIMARY KEY,
    venture_id   TEXT NOT NULL,
    run_id       TEXT NOT NULL DEFAULT '',
    stage        TEXT NOT NULL DEFAULT '',
    event_type   TEXT NOT NULL,
    amount_eur   REAL NOT NULL DEFAULT 0.0,
    listing_id   TEXT,
    platform     TEXT NOT NULL DEFAULT '',
    notes        TEXT NOT NULL DEFAULT '',
    occurred_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hitl_log (
    entry_id     TEXT PRIMARY KEY,
    venture_id   TEXT NOT NULL,
    run_id       TEXT NOT NULL DEFAULT '',
    stage        TEXT NOT NULL DEFAULT '',
    decision     TEXT NOT NULL,
    item_summary TEXT NOT NULL DEFAULT '',
    reason       TEXT NOT NULL DEFAULT '',
    decided_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_events (
    decision_id      TEXT PRIMARY KEY,
    venture_id       TEXT NOT NULL,
    decision_type    TEXT NOT NULL,
    summary          TEXT NOT NULL DEFAULT '',
    detail           TEXT NOT NULL DEFAULT '',
    cvs_at_decision  REAL NOT NULL DEFAULT 0.0,
    decided_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kelly_signals (
    venture_id               TEXT PRIMARY KEY,
    total_revenue_eur        REAL NOT NULL DEFAULT 0.0,
    total_cost_eur           REAL NOT NULL DEFAULT 0.0,
    conversions              INTEGER NOT NULL DEFAULT 0,
    impressions              INTEGER NOT NULL DEFAULT 0,
    roi                      REAL NOT NULL DEFAULT 0.0,
    win_rate                 REAL NOT NULL DEFAULT 0.0,
    suggested_kelly_fraction REAL NOT NULL DEFAULT 0.0,
    half_kelly_fraction      REAL NOT NULL DEFAULT 0.0,
    expected_value           REAL NOT NULL DEFAULT 0.0,
    computed_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_outcome_venture ON outcome_events(venture_id);
CREATE INDEX IF NOT EXISTS idx_hitl_venture ON hitl_log(venture_id);
CREATE INDEX IF NOT EXISTS idx_decision_venture ON decision_events(venture_id);
"""


# ─────────────────────────────────────────────────────────────────────────────
# OutcomeLedger
# ─────────────────────────────────────────────────────────────────────────────

class OutcomeLedger:
    """
    Thread-safe SQLite-backed outcome ledger for CORTEX.

    Usage:
        ledger = OutcomeLedger.get(agent)       # agent-aware singleton
        ledger = OutcomeLedger(":memory:")      # in-memory for tests
        ledger.record_event(OutcomeEvent(...))
        ledger.record_decision(DecisionEvent(...))
        signal = ledger.compute_kelly_signal("my_venture")
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_DDL)
            self._conn.commit()

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Connection, None, None]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # ── Write ─────────────────────────────────────────────────────────────────

    def record_event(self, event: OutcomeEvent) -> None:
        sql = """
        INSERT OR REPLACE INTO outcome_events
            (event_id, venture_id, run_id, stage, event_type,
             amount_eur, listing_id, platform, notes, occurred_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """
        with self._tx() as conn:
            conn.execute(sql, (
                event.event_id, event.venture_id, event.run_id, event.stage,
                event.event_type, event.amount_eur, event.listing_id,
                event.platform, event.notes, event.occurred_at,
            ))

    def record_hitl(self, entry: HITLLogEntry) -> None:
        sql = """
        INSERT OR REPLACE INTO hitl_log
            (entry_id, venture_id, run_id, stage, decision,
             item_summary, reason, decided_at)
        VALUES (?,?,?,?,?,?,?,?)
        """
        with self._tx() as conn:
            conn.execute(sql, (
                entry.entry_id, entry.venture_id, entry.run_id, entry.stage,
                entry.decision, entry.item_summary, entry.reason, entry.decided_at,
            ))

    def record_decision(self, decision: DecisionEvent) -> None:
        sql = """
        INSERT OR REPLACE INTO decision_events
            (decision_id, venture_id, decision_type, summary, detail, cvs_at_decision, decided_at)
        VALUES (?,?,?,?,?,?,?)
        """
        with self._tx() as conn:
            conn.execute(sql, (
                decision.decision_id, decision.venture_id, decision.decision_type,
                decision.summary, decision.detail, decision.cvs_at_decision, decision.decided_at,
            ))

    def record_venture_creation(self, dna) -> DecisionEvent:
        """
        Convenience method: record a venture creation confirmation to the ledger.
        Call this at the CONFIRMATION step of the creation flow.
        dna: VentureDNA instance
        """
        decision = DecisionEvent(
            venture_id=dna.venture_id,
            decision_type="venture_created",
            summary=f"Venture '{dna.name}' created — type={dna.venture_type}, stage={dna.stage}",
            detail=(
                f"Goals: {'; '.join(dna.user_goals[:3])} | "
                f"CVS: {dna.cvs_score.composite_cvs():.1f} [{dna.cvs_score.verdict()}] | "
                f"Confidence: {dna.confidence_level:.0%}"
            ),
            cvs_at_decision=dna.cvs_score.composite_cvs(),
        )
        self.record_decision(decision)
        return decision

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_events(
        self,
        venture_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if venture_id and event_type:
            rows = self._conn.execute(
                "SELECT * FROM outcome_events WHERE venture_id=? AND event_type=? "
                "ORDER BY occurred_at DESC LIMIT ?",
                (venture_id, event_type, limit),
            ).fetchall()
        elif venture_id:
            rows = self._conn.execute(
                "SELECT * FROM outcome_events WHERE venture_id=? ORDER BY occurred_at DESC LIMIT ?",
                (venture_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM outcome_events ORDER BY occurred_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_decisions(self, venture_id: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM decision_events WHERE venture_id=? ORDER BY decided_at DESC",
            (venture_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_hitl_log(self, venture_id: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM hitl_log WHERE venture_id=? ORDER BY decided_at DESC",
            (venture_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def total_revenue(self, venture_id: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_eur), 0) FROM outcome_events "
            "WHERE venture_id=? AND event_type='revenue'",
            (venture_id,),
        ).fetchone()
        return float(row[0])

    def total_cost(self, venture_id: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_eur), 0) FROM outcome_events "
            "WHERE venture_id=? AND event_type='cost'",
            (venture_id,),
        ).fetchone()
        return float(row[0])

    def open_decisions_count(self, venture_id: str) -> int:
        """Count HITL entries that were not 'approve' — i.e. still need resolution."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM hitl_log WHERE venture_id=? AND decision != 'approve'",
            (venture_id,),
        ).fetchone()
        return int(row[0])

    def outcomes_count(self, venture_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM outcome_events WHERE venture_id=?",
            (venture_id,),
        ).fetchone()
        return int(row[0])

    # ── Kelly signal ──────────────────────────────────────────────────────────

    def compute_kelly_signal(self, venture_id: str) -> KellySignal:
        """
        Compute and persist Kelly allocation signal for a venture.
        Uses half-Kelly by default (fractional=0.5) for safety.
        Capped at 0.25 (25% of budget).
        """
        revenue = self.total_revenue(venture_id)
        cost = self.total_cost(venture_id)

        conversions = self._conn.execute(
            "SELECT COUNT(*) FROM outcome_events WHERE venture_id=? AND event_type='conversion'",
            (venture_id,),
        ).fetchone()[0]

        impressions = self._conn.execute(
            "SELECT COUNT(*) FROM outcome_events WHERE venture_id=? AND event_type='impression'",
            (venture_id,),
        ).fetchone()[0]

        win_rate = conversions / max(impressions, 1)
        roi = (revenue - cost) / max(cost, 0.01)

        avg_win = revenue / max(conversions, 1)
        avg_loss = cost / max(impressions - conversions, 1)

        # Full Kelly (capped at 25%)
        full_kelly = calculate_kelly_fraction(win_rate, avg_win, avg_loss, fractional=1.0, cap=0.25)
        # Half Kelly for actual recommendation
        half_kelly = calculate_kelly_fraction(win_rate, avg_win, avg_loss, fractional=0.5, cap=0.25)

        # Expected value
        ev = calculate_expected_value(
            probability_success=win_rate,
            revenue_success=avg_win,
            revenue_failure=0.0,
            cost=avg_loss,
        )

        signal = KellySignal(
            venture_id=venture_id,
            total_revenue_eur=revenue,
            total_cost_eur=cost,
            conversions=conversions,
            impressions=impressions,
            roi=roi,
            win_rate=win_rate,
            suggested_kelly_fraction=full_kelly,
            half_kelly_fraction=half_kelly,
            expected_value=ev,
        )

        upsert_sql = """
        INSERT OR REPLACE INTO kelly_signals
            (venture_id, total_revenue_eur, total_cost_eur, conversions, impressions,
             roi, win_rate, suggested_kelly_fraction, half_kelly_fraction, expected_value, computed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """
        with self._tx() as conn:
            conn.execute(upsert_sql, (
                signal.venture_id, signal.total_revenue_eur, signal.total_cost_eur,
                signal.conversions, signal.impressions, signal.roi, signal.win_rate,
                signal.suggested_kelly_fraction, signal.half_kelly_fraction,
                signal.expected_value, signal.computed_at,
            ))

        return signal

    def get_kelly_signal(self, venture_id: str) -> Optional[KellySignal]:
        """Load last computed Kelly signal from DB."""
        row = self._conn.execute(
            "SELECT * FROM kelly_signals WHERE venture_id=?", (venture_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        return KellySignal(
            venture_id=d["venture_id"],
            total_revenue_eur=d["total_revenue_eur"],
            total_cost_eur=d["total_cost_eur"],
            conversions=d["conversions"],
            impressions=d["impressions"],
            roi=d["roi"],
            win_rate=d["win_rate"],
            suggested_kelly_fraction=d["suggested_kelly_fraction"],
            half_kelly_fraction=d["half_kelly_fraction"],
            expected_value=d["expected_value"],
            computed_at=d["computed_at"],
        )

    def close(self) -> None:
        self._conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Agent-aware singleton
# ─────────────────────────────────────────────────────────────────────────────

_ledger_instances: Dict[str, OutcomeLedger] = {}
_ledger_lock = threading.Lock()


def get_ledger(agent=None) -> OutcomeLedger:
    """
    Return the process-wide OutcomeLedger singleton.
    DB path is derived from agent config memory subdir if agent is provided.
    """
    global _ledger_instances
    if agent is not None:
        try:
            memory_subdir = getattr(agent.config, "agent_memory_subdir", "cortex_main") or "cortex_main"
            db_path = os.path.join("usr", "memory", memory_subdir, "cortex_ledger.db")
        except Exception:
            db_path = os.path.join("usr", "memory", "cortex_main", "cortex_ledger.db")
    else:
        db_path = os.path.join("usr", "memory", "cortex_main", "cortex_ledger.db")

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with _ledger_lock:
        if db_path not in _ledger_instances:
            _ledger_instances[db_path] = OutcomeLedger(db_path)
        return _ledger_instances[db_path]
