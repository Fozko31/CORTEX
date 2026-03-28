"""
cortex_version_manager.py — Named version pinning, checkpoints, rollback.

Safety rules enforced here:
  - Pre-experiment checkpoint: auto git tag + FAISS snapshot + integrity verify
  - Rollback: DOUBLE confirmation required (rollback_request → rollback_execute)
  - Rollback reason + failed assumptions always logged
  - Destructive ops never happen in one step

Version naming: CORTEX vX.Y  (major = phase, minor = applied experiment count)
Git tag format: cortex-vX-Y  (dots replaced to be valid git tag)
"""

import json
import os
import shutil
import subprocess
from datetime import datetime
from typing import Optional


def _base_path() -> str:
    try:
        from python.helpers.memory import abs_db_dir
        base = abs_db_dir("cortex_main")
    except Exception:
        base = os.path.join("usr", "memory", "cortex_main")
    os.makedirs(base, exist_ok=True)
    return base


def _versions_path() -> str:
    return os.path.join(_base_path(), "cortex_versions.json")


def _snapshots_dir() -> str:
    p = os.path.join(_base_path(), "cortex_snapshots")
    os.makedirs(p, exist_ok=True)
    return p


def _pending_rollback_path() -> str:
    return os.path.join(_base_path(), "cortex_pending_rollback.json")


def _load_versions() -> dict:
    try:
        p = _versions_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"versions": [], "current": None}


def _save_versions(data: dict):
    p = _versions_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _git(args: list, cwd: str = ".") -> tuple:
    """Run git command. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def _git_commit_and_tag(tag: str, message: str) -> bool:
    """Commit any staged changes + create annotated tag."""
    _git(["add", "-A"])
    _git(["commit", "-m", message, "--allow-empty"])
    ok, _, _ = _git(["tag", "-a", tag, "-m", message])
    return ok


def _git_checkout_tag(tag: str) -> bool:
    ok, _, _ = _git(["checkout", tag])
    return ok


def _snapshot_faiss(tag: str) -> str:
    """
    Copy FAISS memory files to snapshots/{tag}/.
    Excludes the event store DB and the snapshots dir itself.
    Returns snapshot path (empty string on failure).
    """
    try:
        src = os.path.join("usr", "memory", "cortex_main")
        if not os.path.exists(src):
            return ""
        dst = os.path.join(_snapshots_dir(), tag)
        os.makedirs(dst, exist_ok=True)
        for item in os.listdir(src):
            if item in ("cortex_event_store.db", "cortex_snapshots", "cortex_versions.json", "cortex_pending_rollback.json"):
                continue
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        return dst
    except Exception:
        return ""


def _restore_faiss(snapshot_path: str) -> bool:
    """Restore FAISS files from snapshot. Does NOT touch DBs or config."""
    try:
        if not snapshot_path or not os.path.exists(snapshot_path):
            return False
        dst = os.path.join("usr", "memory", "cortex_main")
        os.makedirs(dst, exist_ok=True)
        for item in os.listdir(snapshot_path):
            s = os.path.join(snapshot_path, item)
            d = os.path.join(dst, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        return True
    except Exception:
        return False


def _verify_snapshot(snapshot_path: str) -> bool:
    return bool(snapshot_path) and os.path.exists(snapshot_path) and len(os.listdir(snapshot_path)) > 0


def _stack_summary() -> dict:
    """Brief stack snapshot for version records."""
    try:
        from python.helpers.cortex_stack_inventory import get_all as stack_get_all
        return {c["component"]: c.get("version", "unknown") for c in stack_get_all()[:12]}
    except Exception:
        return {
            "cortex_core": "Phase G",
            "primary_llm": "claude-sonnet-4-6 via OpenRouter",
            "memory_l1": "FAISS (local)",
            "memory_l2": "Zep Cloud / Graphiti",
            "memory_l3": "SurfSense",
            "telegram": "python-telegram-bot",
            "research_tier1": "Tavily + Exa",
            "research_tier2": "Perplexity via OpenRouter",
        }


# ─── PUBLIC API ──────────────────────────────────────────────────────────────

def pre_experiment_checkpoint(experiment_name: str) -> dict:
    """
    Mandatory call before any experiment or stack change.
    1. Git commit + tag
    2. FAISS snapshot
    3. Integrity verify
    4. Record in versions log
    Returns {"tag": str, "success": bool, "snapshot_path": str, "verified": bool}
    """
    tag = f"pre-exp-{datetime.now().strftime('%Y%m%d-%H%M')}"
    message = f"Auto-checkpoint before: {experiment_name}"

    tagged = _git_commit_and_tag(tag, message)
    snapshot = _snapshot_faiss(tag)
    verified = _verify_snapshot(snapshot)

    record = {
        "id": tag,
        "type": "experiment_checkpoint",
        "experiment_name": experiment_name,
        "timestamp": datetime.now().isoformat(),
        "git_tagged": tagged,
        "snapshot_path": snapshot,
        "snapshot_verified": verified,
    }
    data = _load_versions()
    data["versions"].append(record)
    _save_versions(data)

    return {
        "tag": tag,
        "success": tagged,
        "snapshot_path": snapshot,
        "verified": verified,
        "message": f"Checkpoint created: {tag}. Git tagged: {tagged}. FAISS snapshot verified: {verified}.",
    }


def pin_version(
    name: str,
    notes: str = "",
    changes_from_previous: str = "",
    outcome: str = "",
) -> dict:
    """
    Pin a named stable CORTEX version.
    Creates git tag + FAISS snapshot + two-layer version record.
    name: e.g. "v7.0" or "Phase G complete"
    """
    tag = f"cortex-{name.lower().replace(' ', '-').replace('.', '-')}"
    message = f"CORTEX {name}: {notes[:80]}" if notes else f"CORTEX {name}"

    data = _load_versions()
    previous_id = next(
        (v["id"] for v in reversed(data["versions"]) if v.get("type") == "stable"),
        None,
    )

    tagged = _git_commit_and_tag(tag, message)
    snapshot = _snapshot_faiss(tag)
    verified = _verify_snapshot(snapshot)

    record = {
        "id": tag,
        "name": name,
        "type": "stable",
        "timestamp": datetime.now().isoformat(),
        "notes": notes,
        "changes_from_previous": changes_from_previous,
        "previous_version": previous_id,
        "outcome": outcome,
        "git_tagged": tagged,
        "snapshot_path": snapshot,
        "snapshot_verified": verified,
        # Two-layer version data
        "human_report": _build_human_report(name, notes, changes_from_previous, outcome, previous_id),
        "stack_snapshot": _stack_summary(),
    }

    data["versions"].append(record)
    data["current"] = tag
    _save_versions(data)

    return {"tag": tag, "success": tagged and verified, "record": record}


def _build_human_report(name, notes, changes, outcome, previous_id) -> str:
    lines = [
        f"# CORTEX {name}",
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        f"Stable: YES",
        "",
    ]
    if notes:
        lines += ["## Summary", notes, ""]
    if changes:
        prev_label = previous_id or "previous version"
        lines += [f"## Changes from {prev_label}", changes, ""]
    if outcome:
        lines += ["## Outcome", outcome, ""]
    return "\n".join(lines)


def rollback_request(tag: str, reason: str, failed_assumptions: str = "") -> dict:
    """
    FIRST confirmation step. Stages a rollback — does NOT execute it.
    Returns a confirm_phrase that must be passed to rollback_execute().
    The user must call rollback_execute() explicitly — two separate actions required.
    """
    confirm_phrase = f"ROLLBACK-{tag[-10:]}-{datetime.now().strftime('%H%M')}-CONFIRM"

    pending = {
        "tag": tag,
        "reason": reason,
        "failed_assumptions": failed_assumptions,
        "confirm_phrase": confirm_phrase,
        "requested_at": datetime.now().isoformat(),
    }
    with open(_pending_rollback_path(), "w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2)

    return {
        "status": "pending_confirmation",
        "confirm_phrase": confirm_phrase,
        "warning": (
            f"Rollback to '{tag}' staged. This will revert code AND FAISS memory. "
            f"Zep and SurfSense are NOT affected (cloud-external). "
            f"To confirm: call rollback_execute with confirm_phrase='{confirm_phrase}'. "
            f"This is irreversible for local changes since {tag}."
        ),
    }


def rollback_execute(confirm_phrase: str) -> dict:
    """
    SECOND confirmation step. Executes rollback only if confirm_phrase matches.
    Records reason + failed assumptions in version log.
    """
    pending_path = _pending_rollback_path()
    if not os.path.exists(pending_path):
        return {"success": False, "error": "No pending rollback. Call rollback_request() first."}

    with open(pending_path, "r", encoding="utf-8") as f:
        pending = json.load(f)

    if pending.get("confirm_phrase") != confirm_phrase:
        return {"success": False, "error": "Confirm phrase mismatch. Rollback aborted. Existing request preserved."}

    tag = pending["tag"]

    # Find snapshot for this tag
    data = _load_versions()
    record = next((v for v in data["versions"] if v.get("id") == tag), None)
    snapshot_path = record.get("snapshot_path", "") if record else ""

    git_ok = _git_checkout_tag(tag)
    faiss_ok = _restore_faiss(snapshot_path) if snapshot_path else False

    rollback_record = {
        "id": f"rollback-{datetime.now().strftime('%Y%m%d-%H%M')}",
        "type": "rollback",
        "rolled_back_to": tag,
        "reason": pending["reason"],
        "failed_assumptions": pending.get("failed_assumptions", ""),
        "timestamp": datetime.now().isoformat(),
        "git_restored": git_ok,
        "faiss_restored": faiss_ok,
    }
    data["versions"].append(rollback_record)
    data["current"] = tag
    _save_versions(data)

    # Clear pending
    try:
        os.remove(pending_path)
    except Exception:
        pass

    return {
        "success": git_ok,
        "faiss_restored": faiss_ok,
        "rolled_back_to": tag,
        "reason_logged": pending["reason"],
        "message": f"Rolled back to {tag}. Git: {git_ok}. FAISS: {faiss_ok}.",
    }


def list_versions(stable_only: bool = False) -> list:
    data = _load_versions()
    versions = data["versions"]
    if stable_only:
        versions = [v for v in versions if v.get("type") == "stable"]
    return versions


def get_version_report(version_id: str, format: str = "human") -> str:
    data = _load_versions()
    record = next((v for v in data["versions"] if v.get("id") == version_id), None)

    if not record:
        return f"Version '{version_id}' not found. Available: {[v['id'] for v in data['versions'][-5:]]}"

    if format == "human":
        stored = record.get("human_report")
        if stored:
            return stored
        # Fallback for checkpoints
        return (
            f"Checkpoint: {record['id']}\n"
            f"Type: {record.get('type', 'unknown')}\n"
            f"Created: {record.get('timestamp', '')[:10]}\n"
            f"Experiment: {record.get('experiment_name', 'N/A')}\n"
            f"Verified: {record.get('snapshot_verified', False)}"
        )
    else:
        return json.dumps(record, indent=2)


def get_current_version() -> Optional[str]:
    return _load_versions().get("current")


def health_check() -> dict:
    data = _load_versions()
    pending = os.path.exists(_pending_rollback_path())
    snap_dir = _snapshots_dir()
    snaps = len(os.listdir(snap_dir)) if os.path.exists(snap_dir) else 0
    return {
        "versions_total": len(data["versions"]),
        "stable_versions": len([v for v in data["versions"] if v.get("type") == "stable"]),
        "current": data.get("current"),
        "pending_rollback": pending,
        "snapshots_count": snaps,
    }
