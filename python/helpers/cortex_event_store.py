"""
cortex_event_store.py — SQLite event log for Phase G self-optimization.

All raw events (struggles, tool calls, corrections, latency, extension failures,
benchmark runs, experiments) are written here. Lives on Fly Volume (same as FAISS).
Aggregated summaries are pushed to SurfSense cortex_optimization space separately.

Tables:
  struggle_events, tool_calls, user_corrections, latency_events,
  extension_failures, benchmark_runs, experiment_log
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional


_DB_FILENAME = "cortex_event_store.db"


def _db_path() -> str:
    try:
        from python.helpers.memory import abs_db_dir
        base = abs_db_dir("cortex_main")
    except Exception:
        base = os.path.join("usr", "memory", "cortex_main")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, _DB_FILENAME)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS struggle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium',
    signals TEXT,
    context_snippet TEXT,
    session_id TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 1,
    duration_ms INTEGER DEFAULT 0,
    session_id TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correction_type TEXT NOT NULL,
    context_snippet TEXT DEFAULT '',
    session_id TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS latency_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    turn_count INTEGER NOT NULL,
    session_id TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extension_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    extension_name TEXT NOT NULL,
    exception_type TEXT DEFAULT '',
    exception_msg TEXT DEFAULT '',
    session_id TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    query_id TEXT NOT NULL,
    score REAL NOT NULL,
    rubric_scores TEXT DEFAULT '{}',
    judge_model TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL,
    hypothesis TEXT DEFAULT '{}',
    baseline_score REAL DEFAULT 0,
    experimental_score REAL DEFAULT 0,
    applied INTEGER NOT NULL DEFAULT 0,
    timestamp TEXT NOT NULL
);
"""


def initialize() -> bool:
    """Create all tables if they don't exist. Safe to call repeatedly."""
    try:
        conn = _connect()
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ─── WRITE ──────────────────────────────────────────────────────────────────

def log_struggle(
    topic: str,
    severity: str = "medium",
    signals: Optional[list] = None,
    context_snippet: str = "",
    session_id: str = "",
) -> bool:
    try:
        initialize()
        conn = _connect()
        conn.execute(
            "INSERT INTO struggle_events (topic, severity, signals, context_snippet, session_id, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                topic,
                severity,
                json.dumps(signals or []),
                context_snippet[:400],
                session_id,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def log_tool_call(
    tool_name: str,
    success: bool = True,
    duration_ms: int = 0,
    session_id: str = "",
) -> bool:
    try:
        initialize()
        conn = _connect()
        conn.execute(
            "INSERT INTO tool_calls (tool_name, success, duration_ms, session_id, timestamp) VALUES (?, ?, ?, ?, ?)",
            (tool_name, 1 if success else 0, duration_ms, session_id, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def log_correction(
    correction_type: str,
    context_snippet: str = "",
    session_id: str = "",
) -> bool:
    try:
        initialize()
        conn = _connect()
        conn.execute(
            "INSERT INTO user_corrections (correction_type, context_snippet, session_id, timestamp) VALUES (?, ?, ?, ?)",
            (correction_type, context_snippet[:400], session_id, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def log_latency(task_type: str, turn_count: int, session_id: str = "") -> bool:
    try:
        initialize()
        conn = _connect()
        conn.execute(
            "INSERT INTO latency_events (task_type, turn_count, session_id, timestamp) VALUES (?, ?, ?, ?)",
            (task_type, turn_count, session_id, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def log_extension_failure(
    extension_name: str,
    exception_type: str = "",
    exception_msg: str = "",
    session_id: str = "",
) -> bool:
    try:
        initialize()
        conn = _connect()
        conn.execute(
            "INSERT INTO extension_failures (extension_name, exception_type, exception_msg, session_id, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (extension_name, exception_type, exception_msg[:600], session_id, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def log_benchmark_run(
    run_date: str,
    query_id: str,
    score: float,
    rubric_scores: Optional[dict] = None,
    judge_model: str = "",
) -> bool:
    try:
        initialize()
        conn = _connect()
        conn.execute(
            "INSERT INTO benchmark_runs (run_date, query_id, score, rubric_scores, judge_model, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_date, query_id, score, json.dumps(rubric_scores or {}), judge_model, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def log_experiment(
    experiment_id: str,
    hypothesis: Optional[dict] = None,
    baseline_score: float = 0.0,
    experimental_score: float = 0.0,
    applied: bool = False,
) -> bool:
    try:
        initialize()
        conn = _connect()
        conn.execute(
            "INSERT INTO experiment_log (experiment_id, hypothesis, baseline_score, experimental_score, applied, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                experiment_id,
                json.dumps(hypothesis or {}),
                baseline_score,
                experimental_score,
                1 if applied else 0,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ─── READ ────────────────────────────────────────────────────────────────────

def get_struggle_events(days: int = 7) -> list:
    try:
        initialize()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM struggle_events WHERE timestamp >= ? ORDER BY timestamp DESC", (cutoff,)
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["signals"] = json.loads(d["signals"] or "[]")
            except Exception:
                d["signals"] = []
            result.append(d)
        return result
    except Exception:
        return []


def get_tool_usage_summary(days: int = 30) -> dict:
    try:
        initialize()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = _connect()
        rows = conn.execute(
            "SELECT tool_name, COUNT(*) as calls, SUM(success) as successes "
            "FROM tool_calls WHERE timestamp >= ? GROUP BY tool_name ORDER BY calls DESC",
            (cutoff,),
        ).fetchall()
        sessions = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM tool_calls WHERE timestamp >= ? AND session_id != ''",
            (cutoff,),
        ).fetchone()[0]
        conn.close()
        by_tool = {}
        for r in rows:
            by_tool[r["tool_name"]] = {
                "calls": r["calls"],
                "success_rate": round(r["successes"] / r["calls"], 3) if r["calls"] else 0.0,
            }
        return {"by_tool": by_tool, "total_sessions": sessions}
    except Exception:
        return {"by_tool": {}, "total_sessions": 0}


def get_correction_summary(days: int = 30) -> list:
    try:
        initialize()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = _connect()
        rows = conn.execute(
            "SELECT correction_type, COUNT(*) as count, context_snippet "
            "FROM user_corrections WHERE timestamp >= ? GROUP BY correction_type ORDER BY count DESC",
            (cutoff,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_latency_summary(days: int = 30) -> list:
    try:
        initialize()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = _connect()
        rows = conn.execute(
            """SELECT task_type,
               ROUND(AVG(turn_count), 2) as avg_turns,
               MAX(turn_count) as max_turns,
               COUNT(*) as occurrences
               FROM latency_events WHERE timestamp >= ?
               GROUP BY task_type ORDER BY avg_turns DESC""",
            (cutoff,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_extension_failures(days: int = 30) -> list:
    try:
        initialize()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = _connect()
        rows = conn.execute(
            "SELECT extension_name, COUNT(*) as count, MAX(exception_type) as last_type, MAX(exception_msg) as last_msg "
            "FROM extension_failures WHERE timestamp >= ? GROUP BY extension_name ORDER BY count DESC",
            (cutoff,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_benchmark_history(query_id: Optional[str] = None, days: int = 90) -> list:
    try:
        initialize()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = _connect()
        if query_id:
            rows = conn.execute(
                "SELECT * FROM benchmark_runs WHERE query_id = ? AND timestamp >= ? ORDER BY timestamp DESC",
                (query_id, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM benchmark_runs WHERE timestamp >= ? ORDER BY timestamp DESC", (cutoff,)
            ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["rubric_scores"] = json.loads(d["rubric_scores"] or "{}")
            except Exception:
                d["rubric_scores"] = {}
            result.append(d)
        return result
    except Exception:
        return []


def get_benchmark_drift(query_id: str, window_days: int = 90) -> dict:
    """Returns score trend for a specific query over time."""
    history = get_benchmark_history(query_id=query_id, days=window_days)
    if not history:
        return {"query_id": query_id, "runs": 0, "trend": "no_data"}
    scores = [h["score"] for h in history]
    recent = scores[:3]
    older = scores[3:6] if len(scores) > 3 else []
    trend = "stable"
    if older:
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        if recent_avg < older_avg - 10:
            trend = "degrading"
        elif recent_avg > older_avg + 10:
            trend = "improving"
    return {
        "query_id": query_id,
        "runs": len(scores),
        "latest_score": scores[0] if scores else 0,
        "avg_score": round(sum(scores) / len(scores), 1),
        "trend": trend,
    }


def get_experiment_history(days: int = 90) -> list:
    try:
        initialize()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM experiment_log WHERE timestamp >= ? ORDER BY timestamp DESC", (cutoff,)
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["hypothesis"] = json.loads(d["hypothesis"] or "{}")
            except Exception:
                d["hypothesis"] = {}
            result.append(d)
        return result
    except Exception:
        return []


def health_check() -> bool:
    try:
        initialize()
        conn = _connect()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return True
    except Exception:
        return False
