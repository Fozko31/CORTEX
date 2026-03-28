"""
CORTEX Venture Action Log
=========================
Immutable audit log for all actions CORTEX takes on behalf of ventures.
Implements the HITL (Human-In-The-Loop) queue: actions pending approval
are logged with status='pending_approval' and surfaced at next interaction.

Database: usr/memory/cortex_main/venture_ops.db (shared with task_queue)

Action schema:
    action_id         TEXT PRIMARY KEY (UUID)
    timestamp         TEXT (ISO 8601)
    action_type       TEXT (mirrors action_class: READ, DRAFT, SEND_MESSAGE, etc.)
    venture_slug      TEXT
    tool_used         TEXT (e.g. "gmail_send", "stripe_charge")
    resource_id       TEXT (nullable — e.g. "gmail_primary")
    inputs            TEXT (JSON blob — parameters passed to the tool)
    autonomy_decision TEXT ("AUTO"|"DRAFT_FIRST"|"REQUIRE_APPROVAL")
    decision_reason   TEXT
    approved_by       TEXT (nullable — "user" if HITL, None if AUTO)
    cost_estimate     REAL (EUR, 0.0 if not applicable)
    outcome           TEXT (JSON blob — result from tool, nullable)
    status            TEXT ("executed"|"pending_approval"|"approved"|"rejected"|"draft_shown")
    error             TEXT (nullable)
    created_at        TEXT
    updated_at        TEXT

HITL flow:
    1. Action logged with status='pending_approval'
    2. venture_ops list_pending surfaces these to user
    3. venture_ops approve(action_id) → status='approved' → executes
    4. venture_ops reject(action_id) → status='rejected'
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from python.helpers.cortex_venture_task_queue import _DB_PATH, _get_conn, init_task_queue_schema


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_action_log_schema(conn: Optional[sqlite3.Connection] = None) -> None:
    """Create the action_log table if it doesn't exist."""
    close = conn is None
    if conn is None:
        conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS action_log (
            action_id         TEXT PRIMARY KEY,
            timestamp         TEXT NOT NULL,
            action_type       TEXT NOT NULL,
            venture_slug      TEXT NOT NULL,
            tool_used         TEXT NOT NULL,
            resource_id       TEXT,
            inputs            TEXT,
            autonomy_decision TEXT NOT NULL,
            decision_reason   TEXT,
            approved_by       TEXT,
            cost_estimate     REAL NOT NULL DEFAULT 0.0,
            outcome           TEXT,
            status            TEXT NOT NULL DEFAULT 'pending_approval',
            error             TEXT,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        )
    """)
    conn.commit()
    if close:
        conn.close()


def _ensure_schema() -> None:
    conn = _get_conn()
    init_task_queue_schema(conn)
    init_action_log_schema(conn)
    conn.close()


# ---------------------------------------------------------------------------
# Action Log
# ---------------------------------------------------------------------------

class VentureActionLog:
    """
    Immutable audit trail + HITL queue for venture actions.
    """

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def log_action(
        self,
        venture_slug: str,
        action_type: str,
        tool_used: str,
        inputs: dict,
        autonomy_decision: str,
        decision_reason: str = "",
        resource_id: Optional[str] = None,
        cost_estimate: float = 0.0,
        status: str = "pending_approval",
    ) -> str:
        """
        Log an action. Returns action_id.

        Args:
            venture_slug: Which venture
            action_type: Action class (READ, SEND_MESSAGE, etc.)
            tool_used: The tool/integration being called
            inputs: Parameters dict (will be JSON-serialized)
            autonomy_decision: Policy decision (AUTO/DRAFT_FIRST/REQUIRE_APPROVAL)
            decision_reason: Why this decision was made
            resource_id: Optional resource identifier
            cost_estimate: Estimated cost in EUR
            status: Initial status

        Returns: action_id (UUID string)
        """
        _ensure_schema()
        action_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        conn = _get_conn()
        conn.execute("""
            INSERT INTO action_log
                (action_id, timestamp, action_type, venture_slug, tool_used,
                 resource_id, inputs, autonomy_decision, decision_reason,
                 approved_by, cost_estimate, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
        """, (
            action_id, now, action_type.upper(), venture_slug, tool_used,
            resource_id, json.dumps(inputs), autonomy_decision, decision_reason,
            cost_estimate, status, now, now,
        ))
        conn.commit()
        conn.close()
        return action_id

    def update_status(
        self,
        action_id: str,
        status: str,
        outcome: Optional[Any] = None,
        error: Optional[str] = None,
        approved_by: Optional[str] = None,
    ) -> dict:
        """Update action status after execution or HITL decision."""
        _ensure_schema()
        conn = _get_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            UPDATE action_log
            SET status = ?, outcome = ?, error = ?, approved_by = ?, updated_at = ?
            WHERE action_id = ?
        """, (
            status,
            json.dumps(outcome) if outcome is not None else None,
            error,
            approved_by,
            now,
            action_id,
        ))
        conn.commit()
        conn.close()
        return {"status": "ok", "action_id": action_id, "new_status": status}

    def approve(self, action_id: str, approved_by: str = "user") -> dict:
        """Mark action as approved (HITL confirmation)."""
        return self.update_status(action_id, "approved", approved_by=approved_by)

    def reject(self, action_id: str, approved_by: str = "user") -> dict:
        """Mark action as rejected (HITL denial)."""
        return self.update_status(action_id, "rejected", approved_by=approved_by)

    def mark_executed(self, action_id: str, outcome: Any) -> dict:
        """Mark action as successfully executed with its outcome."""
        return self.update_status(action_id, "executed", outcome=outcome)

    def mark_failed(self, action_id: str, error: str) -> dict:
        """Mark action as failed."""
        return self.update_status(action_id, "failed", error=error)

    def mark_draft_shown(self, action_id: str) -> dict:
        """Mark that draft was surfaced to user (DRAFT_FIRST flow)."""
        return self.update_status(action_id, "draft_shown")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_action(self, action_id: str) -> Optional[dict]:
        _ensure_schema()
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM action_log WHERE action_id = ?", (action_id,)
        ).fetchone()
        conn.close()
        return _deserialize_row(dict(row)) if row else None

    def list_pending(self, venture_slug: Optional[str] = None) -> list[dict]:
        """Return actions waiting for HITL approval."""
        return self._list_by_status("pending_approval", venture_slug)

    def list_by_venture(
        self,
        venture_slug: str,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> list[dict]:
        """Recent action log for a venture."""
        _ensure_schema()
        conn = _get_conn()
        q = "SELECT * FROM action_log WHERE venture_slug = ?"
        params: list = [venture_slug]
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [_deserialize_row(dict(r)) for r in rows]

    def _list_by_status(self, status: str, venture_slug: Optional[str] = None) -> list[dict]:
        _ensure_schema()
        conn = _get_conn()
        q = "SELECT * FROM action_log WHERE status = ?"
        params: list = [status]
        if venture_slug:
            q += " AND venture_slug = ?"
            params.append(venture_slug)
        q += " ORDER BY timestamp ASC"
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [_deserialize_row(dict(r)) for r in rows]

    def pending_count(self, venture_slug: Optional[str] = None) -> int:
        """Quick count of pending approvals — for system prompt injection."""
        _ensure_schema()
        conn = _get_conn()
        q = "SELECT COUNT(*) FROM action_log WHERE status = 'pending_approval'"
        params: list = []
        if venture_slug:
            q += " AND venture_slug = ?"
            params.append(venture_slug)
        count = conn.execute(q, params).fetchone()[0]
        conn.close()
        return count

    def get_total_cost(self, venture_slug: str) -> float:
        """Sum of cost_estimate for executed actions on a venture."""
        _ensure_schema()
        conn = _get_conn()
        result = conn.execute("""
            SELECT COALESCE(SUM(cost_estimate), 0.0)
            FROM action_log
            WHERE venture_slug = ? AND status = 'executed'
        """, (venture_slug,)).fetchone()[0]
        conn.close()
        return float(result)

    @classmethod
    def from_agent_config(cls, agent) -> "VentureActionLog":
        return cls()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _deserialize_row(row: dict) -> dict:
    """Deserialize JSON fields in a row dict."""
    for field in ("inputs", "outcome"):
        if row.get(field) and isinstance(row[field], str):
            try:
                row[field] = json.loads(row[field])
            except Exception:
                pass
    return row
