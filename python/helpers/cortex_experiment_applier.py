"""
cortex_experiment_applier.py — Applies an approved experiment to live files.

Approved: write proposed change to target file + git commit via version manager.
Rejected: no file changes, log the rejection + reason.

The change written is the same one that was tested in the experiment run.
The version manager handles the git commit + version record.
"""

import json
import os
from datetime import datetime
from typing import Optional


def apply_experiment(
    result_dict: dict,
    approved_by: str = "user",
) -> dict:
    """
    Apply an approved experiment result to the live target file.

    result_dict: the ExperimentResult.to_dict() output
    Returns: {"success": bool, "version_tag": str, "message": str}
    """
    exp_id = result_dict.get("experiment_id", "unknown")
    hypothesis = result_dict.get("hypothesis", {})
    target_file = hypothesis.get("target_file", "")
    target_type = hypothesis.get("target_type", "prompt")
    change_summary = hypothesis.get("proposed_change_summary", "")
    hypothesis_text = hypothesis.get("hypothesis_text", "")
    overall_delta = result_dict.get("overall_delta", 0)
    baseline = result_dict.get("baseline_avg", 0)
    experimental = result_dict.get("experimental_avg", 0)

    if not target_file:
        return {"success": False, "version_tag": "", "message": "No target file specified in hypothesis."}

    # Write the change
    write_ok = _write_change(target_file, target_type, hypothesis)
    if not write_ok:
        return {"success": False, "version_tag": "", "message": f"Failed to write to {target_file}."}

    # Pin version via version manager
    version_name = f"exp-applied-{exp_id}"
    changes_desc = (
        f"Applied experiment {exp_id}\n"
        f"Hypothesis: {hypothesis_text}\n"
        f"Change: {change_summary}\n"
        f"Score delta: {overall_delta:+.1f} pts ({baseline:.1f} -> {experimental:.1f})\n"
        f"Approved by: {approved_by} on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    try:
        from python.helpers import cortex_version_manager as vm
        pin_result = vm.pin_version(
            name=version_name,
            notes=f"Experiment {exp_id} applied: {change_summary[:100]}",
            changes_from_previous=changes_desc,
            outcome=f"Predicted improvement: +{overall_delta:.1f} pts. Actual outcome tracked via Loop 2.",
        )
        version_tag = pin_result.get("tag", "")
    except Exception as e:
        version_tag = ""

    # Update experiment log to mark as applied
    try:
        from python.helpers import cortex_event_store as es
        es.log_experiment(
            experiment_id=f"{exp_id}-applied",
            hypothesis=hypothesis,
            baseline_score=baseline,
            experimental_score=experimental,
            applied=True,
        )
    except Exception:
        pass

    return {
        "success": write_ok,
        "version_tag": version_tag,
        "message": (
            f"Experiment {exp_id} applied to {target_file.split('/')[-1]}. "
            f"Version pinned: {version_tag}. "
            f"Rollback available via version manager if needed."
        ),
    }


def reject_experiment(
    result_dict: dict,
    reason: str = "",
) -> dict:
    """
    Reject an experiment — no file changes made.
    Logs the rejection for future pattern analysis.
    """
    exp_id = result_dict.get("experiment_id", "unknown")

    try:
        from python.helpers import cortex_event_store as es
        es.log_experiment(
            experiment_id=f"{exp_id}-rejected",
            hypothesis={
                **result_dict.get("hypothesis", {}),
                "rejection_reason": reason,
                "rejected_at": datetime.now().isoformat(),
            },
            baseline_score=result_dict.get("baseline_avg", 0),
            experimental_score=result_dict.get("experimental_avg", 0),
            applied=False,
        )
    except Exception:
        pass

    return {
        "success": True,
        "message": f"Experiment {exp_id} rejected. Reason logged: '{reason or 'not specified'}'. No files changed.",
    }


# ─── INTERNALS ───────────────────────────────────────────────────────────────

def _write_change(target_file: str, target_type: str, hypothesis: dict) -> bool:
    """
    Write the proposed change to the target file.
    Currently: appends a structured section to the end of the file.
    Future (G.1): DSPy-optimized targeted insertion.
    """
    try:
        if not os.path.exists(target_file):
            return False

        with open(target_file, "r", encoding="utf-8") as f:
            original = f.read()

        addition = _build_addition(hypothesis)

        with open(target_file, "w", encoding="utf-8") as f:
            f.write(original + addition)

        return True
    except Exception:
        return False


def _build_addition(hypothesis: dict) -> str:
    """Build the text block to append to the target file."""
    topic = hypothesis.get("cluster_topic", "unknown").replace("_", " ").title()
    change = hypothesis.get("proposed_change_summary", "")
    exp_id = hypothesis.get("experiment_id", "")
    date = datetime.now().strftime("%Y-%m-%d")

    return (
        f"\n\n---\n"
        f"<!-- Experiment {exp_id} applied {date} -->\n"
        f"## {topic} Context (Optimization Applied)\n\n"
        f"{change}\n\n"
        f"*This section was added by CORTEX self-improvement Loop 1, "
        f"experiment {exp_id}. Applied after user approval.*\n"
    )
