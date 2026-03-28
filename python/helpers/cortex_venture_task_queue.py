"""
CORTEX Venture Task Queue
=========================
Per-venture recurring task management. Stores scheduled tasks that
Agent Zero's TaskScheduler executes.

Database: usr/memory/cortex_main/venture_ops.db (shared with action_log)

Task schema:
    task_id         TEXT PRIMARY KEY
    task_type       TEXT  (e.g. "email_handling", "invoicing", "digest")
    venture_slug    TEXT
    name            TEXT  (human-readable display name)
    cadence         TEXT  (cron expression, e.g. "0 9 * * 1" = Mon 09:00)
    last_run        TEXT  (ISO 8601, nullable)
    next_run        TEXT  (ISO 8601, nullable)
    enabled         INTEGER (0/1)
    status          TEXT  ("active", "paused", "failed", "disabled")
    last_error      TEXT  (nullable)
    prompt          TEXT  (what the scheduled agent is told to do)
    created_at      TEXT
    updated_at      TEXT

Integration with TaskScheduler:
    register_venture_task() → creates ScheduledTask via TaskScheduler
    deregister_venture_task() → removes from TaskScheduler + marks disabled in DB
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DB_PATH = Path("usr/memory/cortex_main/venture_ops.db")


# ---------------------------------------------------------------------------
# DB init
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_task_queue_schema(conn: Optional[sqlite3.Connection] = None) -> None:
    """Create the task_queue table if it doesn't exist."""
    close = conn is None
    if conn is None:
        conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            task_id      TEXT PRIMARY KEY,
            task_type    TEXT NOT NULL,
            venture_slug TEXT NOT NULL,
            name         TEXT NOT NULL,
            cadence      TEXT NOT NULL,
            last_run     TEXT,
            next_run     TEXT,
            enabled      INTEGER NOT NULL DEFAULT 1,
            status       TEXT NOT NULL DEFAULT 'active',
            last_error   TEXT,
            prompt       TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        )
    """)
    conn.commit()
    if close:
        conn.close()


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------

class VentureTaskQueue:
    """
    Manage recurring tasks for a venture.
    Each task maps to a TaskScheduler entry in Agent Zero.
    """

    def add_task(
        self,
        venture_slug: str,
        task_type: str,
        name: str,
        cadence: str,
        prompt: str,
    ) -> dict:
        """
        Add a recurring task.

        Args:
            venture_slug: Which venture owns this task
            task_type: Functional type (email_handling, invoicing, etc.)
            name: Display name
            cadence: Cron expression (e.g. "0 9 * * *")
            prompt: What the agent should do when this fires

        Returns: task dict with task_id
        """
        conn = _get_conn()
        init_task_queue_schema(conn)

        now = datetime.now(timezone.utc).isoformat()
        task_id = str(uuid.uuid4())

        conn.execute("""
            INSERT INTO task_queue
                (task_id, task_type, venture_slug, name, cadence, enabled,
                 status, prompt, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, 'active', ?, ?, ?)
        """, (task_id, task_type, venture_slug, name, cadence, prompt, now, now))
        conn.commit()
        conn.close()

        return {
            "task_id": task_id,
            "task_type": task_type,
            "venture_slug": venture_slug,
            "name": name,
            "cadence": cadence,
            "status": "active",
            "enabled": True,
        }

    def get_task(self, task_id: str) -> Optional[dict]:
        conn = _get_conn()
        init_task_queue_schema(conn)
        row = conn.execute(
            "SELECT * FROM task_queue WHERE task_id = ?", (task_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_tasks(
        self,
        venture_slug: Optional[str] = None,
        enabled_only: bool = False,
    ) -> list[dict]:
        conn = _get_conn()
        init_task_queue_schema(conn)
        q = "SELECT * FROM task_queue WHERE 1=1"
        params: list = []
        if venture_slug:
            q += " AND venture_slug = ?"
            params.append(venture_slug)
        if enabled_only:
            q += " AND enabled = 1"
        q += " ORDER BY venture_slug, name"
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_task(self, task_id: str, **kwargs) -> dict:
        """Update mutable fields: name, cadence, prompt, enabled, status, last_error."""
        allowed = {"name", "cadence", "prompt", "enabled", "status", "last_error", "last_run", "next_run"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return {"status": "no_change"}

        conn = _get_conn()
        init_task_queue_schema(conn)
        now = datetime.now(timezone.utc).isoformat()
        updates["updated_at"] = now

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        conn.execute(
            f"UPDATE task_queue SET {set_clause} WHERE task_id = ?", values
        )
        conn.commit()
        conn.close()
        return {"status": "ok", "task_id": task_id, "updated": list(updates.keys())}

    def enable_task(self, task_id: str) -> dict:
        return self.update_task(task_id, enabled=1, status="active")

    def disable_task(self, task_id: str) -> dict:
        return self.update_task(task_id, enabled=0, status="disabled")

    def mark_last_run(self, task_id: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return self.update_task(task_id, last_run=now, status="active", last_error=None)

    def mark_failed(self, task_id: str, error: str) -> dict:
        return self.update_task(task_id, status="failed", last_error=error)

    def delete_task(self, task_id: str) -> dict:
        conn = _get_conn()
        init_task_queue_schema(conn)
        conn.execute("DELETE FROM task_queue WHERE task_id = ?", (task_id,))
        conn.commit()
        conn.close()
        return {"status": "ok", "task_id": task_id}

    # ------------------------------------------------------------------
    # TaskScheduler integration
    # ------------------------------------------------------------------

    async def register_with_scheduler(self, agent, task_id: str) -> dict:
        """Register a venture task via APScheduler."""
        task = self.get_task(task_id)
        if not task:
            return {"status": "error", "error": f"Task {task_id} not found"}

        try:
            from python.cortex.scheduler import TaskScheduler, ScheduledTask
            scheduler = TaskScheduler.get(agent)

            # Dedup check
            existing = scheduler.get_task_by_name(task["name"])
            if existing:
                return {"status": "already_registered", "task_id": task_id}

            # Build a closure so the callable captures task identity
            _tid = task_id
            _slug = task["venture_slug"]
            _tname = task["name"]

            async def _venture_callable() -> None:
                try:
                    from python.helpers.cortex_venture_action_log import log_venture_action
                    log_venture_action(
                        venture_slug=_slug,
                        action=f"scheduled_task:{_tname}",
                        details={"task_id": _tid},
                    )
                except Exception:
                    pass

            scheduled = ScheduledTask.create(
                name=task["name"],
                callable_fn=_venture_callable,
                schedule=task["cadence"],
            )
            await scheduler.add_task(scheduled)
            return {"status": "ok", "task_id": task_id, "scheduler_task_name": task["name"]}

        except Exception as e:
            self.mark_failed(task_id, str(e))
            return {"status": "error", "error": str(e)}

    async def deregister_from_scheduler(self, agent, task_id: str) -> dict:
        """Remove a task from Agent Zero's TaskScheduler."""
        task = self.get_task(task_id)
        if not task:
            return {"status": "error", "error": f"Task {task_id} not found"}

        try:
            from python.cortex.scheduler import TaskScheduler
            scheduler = TaskScheduler.get(agent)
            existing = scheduler.get_task_by_name(task["name"])
            if existing:
                await scheduler.remove_task(existing.id)
            self.disable_task(task_id)
            return {"status": "ok", "task_id": task_id}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @classmethod
    def from_agent_config(cls, agent) -> "VentureTaskQueue":
        return cls()
