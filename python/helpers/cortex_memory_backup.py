"""
CORTEX Memory Backup -- Phase E
================================

Backs up all three memory layers on a weekly schedule:

  L1 (FAISS)      — local copy of usr/memory/ to dated backup dir
  L2 (Graphiti)   — full JSON export of edges + episodes from Zep Cloud
  L3 (SurfSense)  — incremental source content export (new docs since last run)

Schedule: Weekly (Sunday 02:00 UTC) via Agent Zero TaskScheduler.
Cost: ~$0 — file I/O + a few dozen API calls/week.

Usage:
  # From agent context (scheduled task)
  from python.helpers.cortex_memory_backup import run_full_backup
  await run_full_backup(agent)

  # Standalone (manual / testing)
  python -m python.helpers.cortex_memory_backup
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Backup directory
# ---------------------------------------------------------------------------

def _backup_root() -> Path:
    """Base backup directory. Relative to CORTEX root."""
    return Path("usr") / "memory" / "backups"


def _dated_dir(layer: str) -> Path:
    """e.g. usr/memory/backups/graphiti/2026-03-30/"""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return _backup_root() / layer / today


def _prune_old(layer: str, keep_weeks: int = 8) -> None:
    """Remove backup dirs older than keep_weeks weeks (by directory name date)."""
    base = _backup_root() / layer
    if not base.exists():
        return
    dirs = sorted(base.iterdir())
    if len(dirs) > keep_weeks:
        for old in dirs[:-keep_weeks]:
            try:
                shutil.rmtree(old)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# L1: FAISS / local files
# ---------------------------------------------------------------------------

async def backup_l1_faiss() -> dict:
    """
    Copy usr/memory/ (FAISS index + related files) to dated backup dir.
    Excludes the backups/ subdirectory to avoid recursive copy.
    Returns a status dict.
    """
    src = Path("usr") / "memory"
    dst = _dated_dir("faiss")

    if not src.exists():
        return {"status": "skipped", "reason": "src not found", "path": str(src)}

    try:
        dst.mkdir(parents=True, exist_ok=True)

        def _ignore(directory: str, contents: list) -> list:
            if "backups" in Path(directory).parts:
                return contents  # already inside backups — skip everything
            return ["backups"]

        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore)
        _prune_old("faiss")
        return {"status": "ok", "path": str(dst)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# L2: Graphiti / Zep Cloud
# ---------------------------------------------------------------------------

async def backup_l2_graphiti(agent=None) -> dict:
    """
    Export all edges and episodes from Zep Cloud to a compressed JSON file.
    Uses broad search queries to capture as much of the graph as possible.

    Zep Cloud is cloud-managed (no data loss risk), but this export provides:
    - Portability (leave Zep without losing the graph)
    - Offline disaster recovery copy
    """
    try:
        from python.helpers.cortex_graphiti_client import CortexGraphitiClient

        if agent:
            client = CortexGraphitiClient.from_agent_config(agent)
        else:
            api_key = os.getenv("ZEP_API_KEY", "")
            client = CortexGraphitiClient(api_key=api_key)

        if not client.is_configured():
            return {"status": "skipped", "reason": "Graphiti not configured"}

        zep = client._get_client()
        user_id = client.user_id

        edges: list = []
        episodes: list = []

        # Broad queries to capture graph content
        # Zep graph search returns up to limit results per query
        # Multiple broad queries increase coverage
        broad_queries = [
            "business venture opportunity market",
            "user preference decision commitment",
            "entity relationship fact knowledge",
            "CORTEX conversation session",
        ]

        seen_edge_ids: set = set()
        seen_episode_ids: set = set()

        for query in broad_queries:
            try:
                resp = await zep.graph.search(
                    user_id=user_id,
                    query=query,
                    limit=250,
                    scope="edges",
                )
                for edge in (getattr(resp, "edges", None) or []):
                    eid = str(getattr(edge, "uuid", "") or id(edge))
                    if eid not in seen_edge_ids:
                        seen_edge_ids.add(eid)
                        edges.append({
                            "uuid": eid,
                            "source": getattr(edge, "source_node_name", ""),
                            "target": getattr(edge, "target_node_name", ""),
                            "name": getattr(edge, "name", ""),
                            "fact": getattr(edge, "fact", ""),
                            "created_at": str(getattr(edge, "created_at", "")),
                        })
            except Exception:
                pass

            try:
                resp = await zep.graph.search(
                    user_id=user_id,
                    query=query,
                    limit=100,
                    scope="episodes",
                )
                for ep in (getattr(resp, "episodes", None) or []):
                    eid = str(getattr(ep, "uuid", "") or id(ep))
                    if eid not in seen_episode_ids:
                        seen_episode_ids.add(eid)
                        episodes.append({
                            "uuid": eid,
                            "content": getattr(ep, "content", ""),
                            "created_at": str(getattr(ep, "created_at", "")),
                        })
            except Exception:
                pass

        # Also try user.get_facts() if available (Zep SDK dependent)
        facts: list = []
        try:
            facts_resp = await zep.user.get_facts(user_id)
            for f in (getattr(facts_resp, "facts", None) or []):
                facts.append({
                    "fact": getattr(f, "fact", str(f)),
                    "rating": str(getattr(f, "rating", "")),
                    "created_at": str(getattr(f, "created_at", "")),
                })
        except Exception:
            pass

        export = {
            "exported_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "edges_count": len(edges),
            "episodes_count": len(episodes),
            "facts_count": len(facts),
            "edges": edges,
            "episodes": episodes,
            "facts": facts,
        }

        dst = _dated_dir("graphiti")
        dst.mkdir(parents=True, exist_ok=True)
        out_path = dst / "graphiti_export.json.gz"

        with gzip.open(out_path, "wt", encoding="utf-8") as f:
            json.dump(export, f, indent=2, default=str)

        _prune_old("graphiti")
        return {
            "status": "ok",
            "path": str(out_path),
            "edges": len(edges),
            "episodes": len(episodes),
            "facts": len(facts),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# L3: SurfSense — incremental source content export
# ---------------------------------------------------------------------------

_LAST_BACKUP_FILE = Path("usr") / "memory" / "backups" / "surfsense_last_backup.json"


def _load_last_backup_state() -> dict:
    try:
        if _LAST_BACKUP_FILE.exists():
            with open(_LAST_BACKUP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_last_backup_state(state: dict) -> None:
    try:
        _LAST_BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_LAST_BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


async def backup_l3_surfsense(agent=None) -> dict:
    """
    Incremental export of SurfSense source content.
    Exports all documents from all spaces, skipping document IDs seen in
    previous backup runs (tracked in surfsense_last_backup.json).

    Embeddings are NOT backed up — fully recomputable from source content.
    Source content includes both user-uploaded files and CORTEX-pushed content
    (session summaries, knowledge extracts, discovery findings).
    """
    try:
        from python.helpers.cortex_surfsense_client import CortexSurfSenseClient

        if agent:
            client = CortexSurfSenseClient.from_agent_config(agent)
        else:
            url = os.getenv("CORTEX_SURFSENSE_URL", "")
            username = os.getenv("CORTEX_SURFSENSE_USERNAME", "")
            password = os.getenv("CORTEX_SURFSENSE_PASSWORD", "")
            if not url:
                return {"status": "skipped", "reason": "SurfSense not configured"}
            client = CortexSurfSenseClient(base_url=url, username=username, password=password)

        if not await client.health_check():
            return {"status": "skipped", "reason": "SurfSense unreachable"}

        state = _load_last_backup_state()
        seen_ids: set = set(state.get("seen_document_ids", []))

        spaces = await client.list_spaces()
        dst = _dated_dir("surfsense")
        dst.mkdir(parents=True, exist_ok=True)

        total_new = 0
        space_summary: dict = {}

        for space in spaces:
            space_name = space.get("name", "") or str(space.get("id", "unknown"))
            new_docs: list = []

            # Paginate through all documents in this space
            page = 0
            page_size = 100
            while True:
                try:
                    http_client = await client._get_client()
                    headers = await client._headers()
                    space_id = space.get("id")
                    resp = await http_client.get(
                        f"{client.base_url}/api/v1/documents",
                        headers=headers,
                        params={
                            "search_space_id": space_id,
                            "page_size": page_size,
                            "page": page,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    items = data.get("items", []) if isinstance(data, dict) else data
                    if not items:
                        break

                    for doc in items:
                        doc_id = str(doc.get("id", "") or doc.get("document_id", ""))
                        if doc_id and doc_id not in seen_ids:
                            new_docs.append({
                                "id": doc_id,
                                "title": doc.get("title", ""),
                                "content": doc.get("content", "") or doc.get("document_content", ""),
                                "metadata": doc.get("metadata", {}),
                                "created_at": str(doc.get("created_at", "")),
                            })
                            seen_ids.add(doc_id)

                    # If fewer items returned than page_size, we've reached the end
                    if len(items) < page_size:
                        break
                    page += 1
                except Exception:
                    break

            if new_docs:
                space_file = dst / f"{space_name}.json.gz"
                mode = "at" if space_file.exists() else "wt"
                # Append to existing file or create new — write as newline-delimited JSON
                with gzip.open(space_file, mode, encoding="utf-8") as f:
                    for doc in new_docs:
                        f.write(json.dumps(doc, default=str) + "\n")
                total_new += len(new_docs)
                space_summary[space_name] = len(new_docs)

        # Persist updated seen IDs
        state["seen_document_ids"] = list(seen_ids)
        state["last_backup_at"] = datetime.utcnow().isoformat()
        _save_last_backup_state(state)

        _prune_old("surfsense")
        return {
            "status": "ok",
            "new_documents": total_new,
            "spaces": space_summary,
            "path": str(dst),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Full backup — runs all three layers
# ---------------------------------------------------------------------------

async def run_full_backup(agent=None) -> dict:
    """
    Run all three memory layer backups sequentially.
    Returns a summary dict with results per layer.
    """
    ts = datetime.utcnow().isoformat()
    print(f"[CORTEX backup] Starting full memory backup at {ts}")

    try:
        l1 = await backup_l1_faiss()
    except Exception as e:
        l1 = {"status": "error", "error": str(e)}
    print(f"[CORTEX backup] L1 FAISS: {l1['status']}")

    try:
        l2 = await backup_l2_graphiti(agent)
    except Exception as e:
        l2 = {"status": "error", "error": str(e)}
    print(f"[CORTEX backup] L2 Graphiti: {l2['status']}")

    try:
        l3 = await backup_l3_surfsense(agent)
    except Exception as e:
        l3 = {"status": "error", "error": str(e)}
    print(f"[CORTEX backup] L3 SurfSense: {l3['status']}")

    summary = {"timestamp": ts, "l1_faiss": l1, "l2_graphiti": l2, "l3_surfsense": l3}

    # Write summary log
    log_dir = Path("usr") / "memory" / "backups"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "backup.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, default=str) + "\n")
    except Exception:
        pass

    print(f"[CORTEX backup] Done. Log: {log_path}")
    return summary


# ---------------------------------------------------------------------------
# Scheduler registration
# ---------------------------------------------------------------------------

async def register_backup_task() -> None:
    """Register weekly full backup via Agent Zero TaskScheduler."""
    try:
        from python.cortex.scheduler import TaskScheduler, ScheduledTask, TaskSchedule

        scheduler = TaskScheduler.get()
        task_name = "CORTEX Memory Backup"

        if scheduler.get_task_by_name(task_name):
            return

        schedule = TaskSchedule(
            minute="0",
            hour="2",
            day="*",
            month="*",
            weekday="0",  # Sunday 02:00 UTC
            timezone="UTC",
        )

        task = ScheduledTask.create(
            name=task_name,
            callable_fn=_scheduled_memory_backup,
            schedule=schedule,
        )

        await scheduler.add_task(task)
        print("[CORTEX backup] Registered weekly backup task (Sunday 02:00 UTC)")
    except Exception as e:
        print(f"[CORTEX backup] Could not register backup task: {e}")


async def _scheduled_memory_backup() -> None:
    """Weekly memory backup — called directly by APScheduler."""
    try:
        await run_full_backup(agent=None)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_full_backup())
