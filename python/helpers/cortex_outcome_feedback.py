"""
cortex_outcome_feedback.py — Loop 2: outcome ingestion and execution checkin.

Two ingestion paths:
1. Telegram checkin: "Did you complete X?" → user answers yes/no
2. Manual input via self_improve tool: structured outcome record

When a commitment is marked as due, this module generates a checkin question
and waits for user response before attributing the outcome.

Outcome records are stored in the event store for Loop 2 processing.
"""

import json
import os
from datetime import datetime
from typing import Optional

from python.helpers.cortex_outcome_attributor import OutcomeRecord, classify


_PENDING_CHECKINS_KEY = "cortex_pending_outcome_checkins"


def create_execution_checkin(
    commitment_id: str,
    commitment_description: str,
    venture_id: str,
    venture_name: str,
    cortex_recommendation: str,
) -> dict:
    """
    Create a pending execution checkin for a due commitment.
    Returns the checkin record (should be stored in agent data or SurfSense).
    """
    checkin = {
        "checkin_id": f"checkin-{commitment_id}-{datetime.now().strftime('%Y%m%d')}",
        "commitment_id": commitment_id,
        "commitment_description": commitment_description,
        "venture_id": venture_id,
        "venture_name": venture_name,
        "cortex_recommendation": cortex_recommendation,
        "created_at": datetime.now().isoformat(),
        "status": "pending",  # pending | confirmed_yes | confirmed_no | skipped
        "user_response": None,
    }
    return checkin


def format_checkin_question(checkin: dict) -> str:
    """Format the Telegram checkin question."""
    commitment = checkin.get("commitment_description", "the agreed action")
    venture = checkin.get("venture_name", "your venture")
    return (
        f"*Outcome Check: {venture}*\n\n"
        f"I recommended: _{checkin.get('cortex_recommendation', commitment)}_\n\n"
        f"Did you complete this? (yes / no / skip)\n"
        f"Checkin ID: `{checkin['checkin_id']}`"
    )


def record_execution_response(checkin: dict, user_response: str) -> dict:
    """Update checkin with user's yes/no/skip response."""
    cleaned = user_response.strip().lower()
    if cleaned in ("yes", "y", "da", "ja", "done", "completed"):
        checkin["status"] = "confirmed_yes"
        checkin["user_execution_confirmed"] = True
    elif cleaned in ("no", "n", "ne", "nein", "didn't", "not done"):
        checkin["status"] = "confirmed_no"
        checkin["user_execution_confirmed"] = False
    else:
        checkin["status"] = "skipped"
        checkin["user_execution_confirmed"] = None
    checkin["user_response"] = user_response
    checkin["responded_at"] = datetime.now().isoformat()
    return checkin


def ingest_outcome(
    venture_id: str,
    venture_name: str,
    period: str,
    metric_type: str,
    target_value: float,
    actual_value: float,
    cortex_controlled_slice: str,
    user_execution_confirmed: Optional[bool] = None,
    external_confounders: Optional[list] = None,
    autonomy_score: float = 0.5,
) -> dict:
    """
    Ingest a new outcome record, classify it, and store it.
    Returns the classified outcome record dict.
    """
    record = OutcomeRecord(
        venture_id=venture_id,
        venture_name=venture_name,
        period=period,
        metric_type=metric_type,
        target_value=target_value,
        actual_value=actual_value,
        cortex_controlled_slice=cortex_controlled_slice,
        user_execution_confirmed=user_execution_confirmed,
        external_confounders=external_confounders or [],
        autonomy_score=autonomy_score,
    )

    classified = classify(record)

    # Store in event store (as a special experiment log entry for now)
    # Full Loop 2 storage will use a dedicated outcomes table in the next iteration
    try:
        from python.helpers import cortex_event_store as es
        es.log_experiment(
            experiment_id=f"outcome-{venture_id}-{period}-{metric_type}",
            hypothesis={
                "type": "outcome_record",
                "record": classified.to_dict(),
            },
            baseline_score=classified.target_value,
            experimental_score=classified.actual_value,
            applied=False,
        )
    except Exception:
        pass

    return classified.to_dict()


def get_pending_checkins(agent) -> list:
    """Get pending outcome checkins from agent data."""
    return agent.get_data(_PENDING_CHECKINS_KEY) or []


def add_pending_checkin(agent, checkin: dict):
    """Add a checkin to the pending queue."""
    pending = get_pending_checkins(agent)
    pending.append(checkin)
    agent.set_data(_PENDING_CHECKINS_KEY, pending)


def resolve_checkin(agent, checkin_id: str, response: str) -> Optional[dict]:
    """Find, update, and remove a checkin from the pending queue."""
    pending = get_pending_checkins(agent)
    resolved = None
    remaining = []

    for c in pending:
        if c.get("checkin_id") == checkin_id:
            resolved = record_execution_response(c, response)
        else:
            remaining.append(c)

    agent.set_data(_PENDING_CHECKINS_KEY, remaining)
    return resolved


def format_pending_checkins_summary(agent) -> str:
    """Format pending checkins for the morning digest."""
    pending = get_pending_checkins(agent)
    if not pending:
        return ""
    lines = ["*Outcome Checkins Pending:*"]
    for c in pending[:5]:
        lines.append(f"- {c.get('venture_name', 'unknown')}: {c.get('commitment_description', '')[:60]}")
        lines.append(f"  Reply: yes / no / skip to `{c['checkin_id']}`")
    return "\n".join(lines)
