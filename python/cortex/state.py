"""
python/cortex/state.py — CortexState (Persistent Session KV Store)
===================================================================
Replaces agent.get_data() / agent.set_data().

Design:
  - In-memory dict for fast reads (no I/O on get)
  - Atomic JSON file persistence on every set() — crash-safe
  - Loads from JSON file on init — state survives app restarts
  - One file per agent memory subdir: cortex_session_state.json

Atomicity:
  write to .tmp file → os.rename() to final path
  rename() is atomic on Linux, macOS, and Windows (same filesystem)
  A crash during write leaves the .tmp file; original is untouched.

Fly.io compatibility:
  JSON file lives in memory subdir → already on Fly Volume.
  No code changes needed for production deployment.

Usage:
    state = CortexState.for_agent(agent)
    state.set("active_venture", "verdant")
    name = state.get("active_venture")           # "verdant"
    name = state.get("missing_key", default=[])  # []
    state.delete("active_venture")

Drop-in replacement for agent.get_data / agent.set_data:
    # Before (AZ):
    agent.set_data("cortex_awareness_feed", feed)
    feed = agent.get_data("cortex_awareness_feed") or []

    # After (CORTEX):
    state = CortexState.for_agent(agent)
    state.set("cortex_awareness_feed", feed)
    feed = state.get("cortex_awareness_feed", default=[])
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

_STATE_FILENAME = "cortex_session_state.json"

# Module-level cache: one CortexState per memory-subdir path
_instances: dict[str, "CortexState"] = {}


class CortexState:
    """
    Persistent session key-value store for a single CORTEX agent instance.
    Thread-safe for single-writer use (CORTEX is single-instance).
    """

    def __init__(self, state_path: Path):
        self._path = state_path
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def for_agent(cls, agent: Any) -> "CortexState":
        """
        Get (or create) the CortexState for this agent.
        Cached by memory-subdir path — same instance returned on every call.
        """
        try:
            from python.cortex.memory import get_agent_memory_subdir, abs_db_dir
            subdir = get_agent_memory_subdir(agent)
            base = abs_db_dir(subdir)
        except Exception:
            # Fallback: use a temp dir (tests / standalone mode)
            import tempfile
            base = tempfile.gettempdir()

        path = Path(base) / _STATE_FILENAME

        cache_key = str(path)
        if cache_key not in _instances:
            _instances[cache_key] = cls(path)
        return _instances[cache_key]

    @classmethod
    def for_path(cls, base_dir: str | Path) -> "CortexState":
        """
        Create a CortexState at an explicit path.
        Useful for tests and standalone scripts.
        """
        path = Path(base_dir) / _STATE_FILENAME
        cache_key = str(path)
        if cache_key not in _instances:
            _instances[cache_key] = cls(path)
        return _instances[cache_key]

    # ------------------------------------------------------------------
    # Core KV API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value. Returns default if key not found. Never raises."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Write a value. Persists atomically to disk. Never raises."""
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> None:
        """Remove a key. Persists atomically. No-op if key not found."""
        if key in self._data:
            del self._data[key]
            self._save()

    def all(self) -> dict[str, Any]:
        """Return a shallow copy of all state."""
        return dict(self._data)

    def clear(self) -> None:
        """Remove all keys. Persists atomically."""
        self._data.clear()
        self._save()

    def __contains__(self, key: str) -> bool:
        return key in self._data

    # ------------------------------------------------------------------
    # Persistence — atomic writes (crash-safe)
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load state from JSON file on startup. Silent on error (starts empty)."""
        try:
            if self._path.exists():
                text = self._path.read_text(encoding="utf-8")
                loaded = json.loads(text)
                if isinstance(loaded, dict):
                    self._data = loaded
        except Exception:
            self._data = {}

    def _save(self) -> None:
        """
        Persist state to disk atomically.
        Write to .tmp → rename to final path.
        rename() is atomic: a crash during write leaves original intact.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            # Atomic replace — os.replace works on Windows too
            os.replace(tmp, self._path)
        except Exception:
            pass  # persistence failure is non-fatal; in-memory state still works


def clear_cache() -> None:
    """Clear the instance cache. Used in tests to get fresh instances."""
    global _instances
    _instances.clear()
