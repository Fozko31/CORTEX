"""
CORTEX Autonomy Policy
======================
Per-venture + per-action-class + per-resource-instance autonomy rules.

Lookup hierarchy (most specific wins):
  1. (venture_slug, action_class, resource_id)  — resource-specific rule
  2. (venture_slug, action_class)               — venture + action class default
  3. (venture_slug, *)                          — venture-level default
  4. global default                             — REQUIRE_APPROVAL for everything

Design decisions:
- CORTEX never overrides a saved rule without explicit user instruction
- resource_id is optional; enables two email accounts on same venture to have
  different autonomy rules (e.g. "gmail_primary" → AUTO, "gmail_personal" → DRAFT_FIRST)
- spend_auto_threshold_eur: autonomous spend up to this amount per action; €0.00 = never
- Stored in usr/memory/cortex_main/autonomy_policy.json (plain JSON, no secrets)
- set_rule() is the only write path — always conversational, always explicit

Action classes:
  READ              — fetch, list, read (safe)
  DRAFT             — compose email/message/doc draft, do not send
  SEND_MESSAGE      — send email, post message, comment
  SPEND_MONEY       — any payment, subscription, API call with cost
  DEPLOY            — publish, deploy, push to production
  SCHEDULE          — schedule a recurring task or reminder
  MODIFY_DATA       — write/update/delete data in external systems

Autonomy levels:
  AUTO              — execute without asking
  DRAFT_FIRST       — prepare draft, show user, execute after implicit confirmation
  REQUIRE_APPROVAL  — always surface to HITL queue before executing
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POLICY_FILE = Path("usr/memory/cortex_main/autonomy_policy.json")

# Global fallback — conservative default
_GLOBAL_DEFAULT_LEVEL = "REQUIRE_APPROVAL"

# Action classes with safe defaults
ACTION_CLASSES = ["READ", "DRAFT", "SEND_MESSAGE", "SPEND_MONEY", "DEPLOY", "SCHEDULE", "MODIFY_DATA"]

# What level is assumed if never explicitly set (per action class)
_ACTION_CLASS_SAFE_DEFAULTS: dict[str, str] = {
    "READ": "AUTO",
    "DRAFT": "AUTO",
    "SEND_MESSAGE": "REQUIRE_APPROVAL",
    "SPEND_MONEY": "REQUIRE_APPROVAL",
    "DEPLOY": "REQUIRE_APPROVAL",
    "SCHEDULE": "DRAFT_FIRST",
    "MODIFY_DATA": "REQUIRE_APPROVAL",
}

AUTONOMY_LEVELS = ["AUTO", "DRAFT_FIRST", "REQUIRE_APPROVAL"]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _load_policy() -> dict:
    if _POLICY_FILE.exists():
        try:
            return json.loads(_POLICY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"rules": [], "venture_defaults": {}, "updated_at": None}


def _save_policy(data: dict) -> None:
    _POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _POLICY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Policy Engine
# ---------------------------------------------------------------------------

class CortexAutonomyPolicy:
    """
    Manages autonomy rules at three granularity levels:
      1. Per-resource (most specific)
      2. Per venture + action class
      3. Per venture (venture default)

    Never write to this directly — always go through set_rule() / set_venture_default().
    """

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_level(
        self,
        venture_slug: str,
        action_class: str,
        resource_id: Optional[str] = None,
    ) -> str:
        """
        Return the autonomy level for this context.
        Lookup order: resource-specific → action-class → venture default → global default.
        """
        data = _load_policy()
        rules = data.get("rules", [])
        venture_defaults = data.get("venture_defaults", {})

        ac = action_class.upper()

        # 1. Resource-specific rule
        if resource_id:
            for rule in rules:
                if (
                    rule.get("venture_slug") == venture_slug
                    and rule.get("action_class") == ac
                    and rule.get("resource_id") == resource_id
                ):
                    return rule["level"]

        # 2. Venture + action class rule (no resource)
        for rule in rules:
            if (
                rule.get("venture_slug") == venture_slug
                and rule.get("action_class") == ac
                and not rule.get("resource_id")
            ):
                return rule["level"]

        # 3. Venture-level default
        if venture_slug in venture_defaults:
            return venture_defaults[venture_slug].get("default_level", _GLOBAL_DEFAULT_LEVEL)

        # 4. Action-class safe default (built-in)
        return _ACTION_CLASS_SAFE_DEFAULTS.get(ac, _GLOBAL_DEFAULT_LEVEL)

    def should_auto_execute(
        self,
        venture_slug: str,
        action_class: str,
        resource_id: Optional[str] = None,
        cost_eur: float = 0.0,
    ) -> bool:
        """
        Returns True if the action should execute without asking.
        Also applies spend threshold check for SPEND_MONEY actions.
        """
        level = self.get_level(venture_slug, action_class, resource_id)

        if level == "REQUIRE_APPROVAL":
            return False
        if level == "DRAFT_FIRST":
            return False  # Needs user to see draft first

        # AUTO: check spend threshold
        if action_class.upper() == "SPEND_MONEY" and cost_eur > 0:
            threshold = self.get_spend_threshold(venture_slug)
            if cost_eur > threshold:
                return False

        return True

    def should_draft_first(
        self,
        venture_slug: str,
        action_class: str,
        resource_id: Optional[str] = None,
    ) -> bool:
        """Returns True if action requires showing a draft before executing."""
        level = self.get_level(venture_slug, action_class, resource_id)
        return level == "DRAFT_FIRST"

    def get_spend_threshold(self, venture_slug: str) -> float:
        """Return the autonomous spend threshold in EUR for this venture."""
        data = _load_policy()
        vd = data.get("venture_defaults", {}).get(venture_slug, {})
        return float(vd.get("spend_auto_threshold_eur", 0.0))

    def get_rule(
        self,
        venture_slug: str,
        action_class: str,
        resource_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Return the explicit rule dict if one exists, else None."""
        data = _load_policy()
        ac = action_class.upper()
        for rule in data.get("rules", []):
            if (
                rule.get("venture_slug") == venture_slug
                and rule.get("action_class") == ac
                and rule.get("resource_id") == resource_id
            ):
                return rule
        return None

    def list_rules(self, venture_slug: Optional[str] = None) -> list[dict]:
        """Return all explicit rules, optionally filtered to one venture."""
        data = _load_policy()
        rules = data.get("rules", [])
        if venture_slug:
            rules = [r for r in rules if r.get("venture_slug") == venture_slug]
        return rules

    def get_venture_summary(self, venture_slug: str) -> dict:
        """
        Return a summary of all autonomy settings for a venture,
        showing effective level (explicit or inferred) for each action class.
        Safe to surface in system prompts.
        """
        data = _load_policy()
        venture_defaults = data.get("venture_defaults", {})

        summary = {
            "venture_slug": venture_slug,
            "spend_auto_threshold_eur": self.get_spend_threshold(venture_slug),
            "action_classes": {},
        }

        for ac in ACTION_CLASSES:
            effective = self.get_level(venture_slug, ac)
            explicit_rule = self.get_rule(venture_slug, ac)
            summary["action_classes"][ac] = {
                "level": effective,
                "source": "explicit" if explicit_rule else "default",
            }

        # Include any resource-specific rules
        resource_rules = [
            r for r in data.get("rules", [])
            if r.get("venture_slug") == venture_slug and r.get("resource_id")
        ]
        if resource_rules:
            summary["resource_rules"] = resource_rules

        return summary

    # ------------------------------------------------------------------
    # Write — only explicit user-initiated changes
    # ------------------------------------------------------------------

    def set_rule(
        self,
        venture_slug: str,
        action_class: str,
        level: str,
        resource_id: Optional[str] = None,
        resource_description: str = "",
        reason: str = "",
        set_by: str = "user",
    ) -> dict:
        """
        Set an autonomy rule. Only called after explicit user instruction.

        Args:
            venture_slug: The venture this applies to
            action_class: One of ACTION_CLASSES
            level: One of AUTONOMY_LEVELS
            resource_id: Optional — enables per-resource granularity
                         (e.g. "gmail_primary", "stripe_live")
            resource_description: Human-readable note about this resource
            reason: Why this rule was set (stored for transparency)
            set_by: "user" always — CORTEX never sets this autonomously
        """
        ac = action_class.upper()
        if ac not in ACTION_CLASSES:
            return {"status": "error", "error": f"Unknown action class: {ac}"}
        if level not in AUTONOMY_LEVELS:
            return {"status": "error", "error": f"Unknown autonomy level: {level}"}

        data = _load_policy()
        rules = data.get("rules", [])

        # Find and update existing rule, or append
        found = False
        for rule in rules:
            if (
                rule.get("venture_slug") == venture_slug
                and rule.get("action_class") == ac
                and rule.get("resource_id") == resource_id
            ):
                rule["level"] = level
                rule["reason"] = reason
                rule["resource_description"] = resource_description
                rule["updated_at"] = datetime.now(timezone.utc).isoformat()
                rule["set_by"] = set_by
                found = True
                break

        if not found:
            rules.append({
                "venture_slug": venture_slug,
                "action_class": ac,
                "resource_id": resource_id,
                "resource_description": resource_description,
                "level": level,
                "reason": reason,
                "set_by": set_by,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

        data["rules"] = rules
        _save_policy(data)

        return {
            "status": "ok",
            "venture_slug": venture_slug,
            "action_class": ac,
            "resource_id": resource_id,
            "level": level,
        }

    def set_venture_default(
        self,
        venture_slug: str,
        default_level: str,
        spend_auto_threshold_eur: float = 0.0,
        reason: str = "",
    ) -> dict:
        """
        Set venture-wide defaults. More specific rules still take precedence.
        """
        if default_level not in AUTONOMY_LEVELS:
            return {"status": "error", "error": f"Unknown autonomy level: {default_level}"}

        data = _load_policy()
        vd = data.setdefault("venture_defaults", {})
        vd[venture_slug] = {
            "default_level": default_level,
            "spend_auto_threshold_eur": spend_auto_threshold_eur,
            "reason": reason,
            "set_by": "user",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_policy(data)

        return {
            "status": "ok",
            "venture_slug": venture_slug,
            "default_level": default_level,
            "spend_auto_threshold_eur": spend_auto_threshold_eur,
        }

    def delete_rule(
        self,
        venture_slug: str,
        action_class: str,
        resource_id: Optional[str] = None,
    ) -> dict:
        """Remove an explicit rule (lookup will fall back to defaults)."""
        ac = action_class.upper()
        data = _load_policy()
        before = len(data.get("rules", []))
        data["rules"] = [
            r for r in data.get("rules", [])
            if not (
                r.get("venture_slug") == venture_slug
                and r.get("action_class") == ac
                and r.get("resource_id") == resource_id
            )
        ]
        after = len(data["rules"])
        _save_policy(data)
        return {"status": "ok", "removed": before - after}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_agent_config(cls, agent) -> "CortexAutonomyPolicy":
        return cls()


# ---------------------------------------------------------------------------
# HITL decision helper — used by venture_ops approve/reject
# ---------------------------------------------------------------------------

def make_autonomy_decision(
    policy: CortexAutonomyPolicy,
    venture_slug: str,
    action_class: str,
    resource_id: Optional[str] = None,
    cost_eur: float = 0.0,
) -> dict:
    """
    Returns a decision dict for logging in the action log.
    {decision: "AUTO"|"DRAFT_FIRST"|"REQUIRE_APPROVAL", reason: str}
    """
    level = policy.get_level(venture_slug, action_class, resource_id)
    rule = policy.get_rule(venture_slug, action_class, resource_id)

    # Spend override
    if action_class.upper() == "SPEND_MONEY" and level == "AUTO":
        threshold = policy.get_spend_threshold(venture_slug)
        if cost_eur > threshold:
            return {
                "decision": "REQUIRE_APPROVAL",
                "reason": f"Cost €{cost_eur:.2f} exceeds auto threshold €{threshold:.2f}",
            }

    source = "explicit rule" if rule else "default"
    resource_note = f" (resource: {resource_id})" if resource_id else ""
    return {
        "decision": level,
        "reason": f"Policy {source} for {venture_slug}/{action_class}{resource_note} → {level}",
    }
