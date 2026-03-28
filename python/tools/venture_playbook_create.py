"""
venture_playbook_create tool — Interactive Playbook Creation
=============================================================
9-step interactive flow for creating a venture's operational playbook.

Steps:
  1. Confirm venture + check for existing draft (resume logic)
  2. Business model recap — what the venture does, how it makes money
  3. Target customer profile — ICP, acquisition channels
  4. Core operations — daily/weekly repeatable processes
  5. Team & roles — who does what (human + AI roles)
  6. Tools & integrations — CRM, email, payments, comms
  7. Metrics & KPIs — what success looks like, how to measure
  8. Compliance & legal — GDPR data handling, terms, liabilities, jurisdiction
  9. Review + version + publish

Resume logic:
  - Detects existing draft (status='draft') on venture slug
  - Offers to resume from last completed step or start fresh
  - Draft auto-saved after each step completion

Storage:
  - Local: usr/memory/cortex_main/ventures/{slug}_playbooks/playbook_v{N}.json
  - SurfSense: {slug}_ops space, title: "{VentureName} Playbook v{N}"
  - Version: integer, increments from 1

Compliance section (Step 8):
  - Data handling: what user data is collected, how stored, retention
  - GDPR basis: consent / legitimate interest / contract
  - User rights: access, erasure, portability procedures
  - Legal entity & jurisdiction
  - Terms of service / privacy policy status
  - Key liabilities and risk mitigations
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from python.helpers.tool import Tool, Response


# ---------------------------------------------------------------------------
# Playbook schema
# ---------------------------------------------------------------------------

PLAYBOOK_STEPS = [
    "venture_confirmed",
    "business_model",
    "customer_profile",
    "core_operations",
    "team_and_roles",
    "tools_and_integrations",
    "metrics_and_kpis",
    "compliance_and_legal",
    "reviewed_and_published",
]

STEP_PROMPTS = {
    "business_model": (
        "Let's define the business model for {venture_name}.\n"
        "- What problem does it solve?\n"
        "- How does it make money? (subscription, one-time, marketplace, ads, services)\n"
        "- What are the main revenue streams?\n"
        "- What is the cost structure?"
    ),
    "customer_profile": (
        "Now the target customer for {venture_name}.\n"
        "- Who is the ideal customer? (role, company size, industry, demographics)\n"
        "- What pain do they have that you solve?\n"
        "- How do you reach them? (channels: SEO, cold email, paid, referral, etc.)\n"
        "- What does a typical customer journey look like?"
    ),
    "core_operations": (
        "What are the repeatable operations for {venture_name}?\n"
        "- Daily tasks (e.g. email triage, customer support, content posting)\n"
        "- Weekly tasks (e.g. lead review, invoicing, metrics review)\n"
        "- Monthly tasks (e.g. financials, planning, product review)\n"
        "- Which of these can CORTEX handle autonomously?"
    ),
    "team_and_roles": (
        "Team and roles for {venture_name}.\n"
        "- Who are the humans involved and what are their responsibilities?\n"
        "- What roles does CORTEX play? (research, outreach, scheduling, reporting)\n"
        "- Who has final authority on what?"
    ),
    "tools_and_integrations": (
        "Tools and integrations for {venture_name}.\n"
        "- CRM / sales tool\n"
        "- Email provider\n"
        "- Payment processor\n"
        "- Communication (Slack, Telegram, etc.)\n"
        "- Any existing tools already in use\n"
        "- Which need credentials stored in CORTEX vault?"
    ),
    "metrics_and_kpis": (
        "Metrics and KPIs for {venture_name}.\n"
        "- What does success look like in 30 days? 90 days? 1 year?\n"
        "- Primary metric (North Star)\n"
        "- Supporting metrics (revenue, CAC, LTV, churn, NPS, etc.)\n"
        "- What triggers a 'venture is failing' alert?"
    ),
    "compliance_and_legal": (
        "Compliance and legal for {venture_name}.\n"
        "- What user data is collected and how is it stored?\n"
        "- GDPR lawful basis: consent / legitimate interest / contract?\n"
        "- User rights procedures: access, erasure, data portability?\n"
        "- Legal entity and jurisdiction (e.g. EU, UK, US)\n"
        "- Is there a Terms of Service? Privacy Policy? Status: draft / live / needed?\n"
        "- Key liability risks and how they're mitigated"
    ),
}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _playbook_dir(slug: str) -> Path:
    return Path(f"usr/memory/cortex_main/ventures/{slug}_playbooks")


def _draft_path(slug: str) -> Path:
    return _playbook_dir(slug) / "playbook_draft.json"


def _versioned_path(slug: str, version: int) -> Path:
    return _playbook_dir(slug) / f"playbook_v{version}.json"


def _load_draft(slug: str) -> dict | None:
    path = _draft_path(slug)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_draft(slug: str, data: dict) -> None:
    d = _playbook_dir(slug)
    d.mkdir(parents=True, exist_ok=True)
    _draft_path(slug).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _next_version(slug: str) -> int:
    d = _playbook_dir(slug)
    if not d.exists():
        return 1
    existing = sorted(d.glob("playbook_v*.json"))
    return len(existing) + 1


def _publish_playbook(slug: str, data: dict) -> dict:
    """Finalize draft → versioned file."""
    version = _next_version(slug)
    d = _playbook_dir(slug)
    d.mkdir(parents=True, exist_ok=True)

    data["version"] = version
    data["status"] = "published"
    data["published_at"] = datetime.now(timezone.utc).isoformat()

    out_path = _versioned_path(slug, version)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Remove draft
    draft = _draft_path(slug)
    if draft.exists():
        draft.unlink()

    return {"path": str(out_path), "version": version}


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class VenturePlaybookCreate(Tool):

    async def execute(self, **kwargs) -> Response:
        operation = kwargs.get("operation", "start").lower()

        dispatch = {
            "start": self._start,
            "resume": self._resume,
            "save_step": self._save_step,
            "publish": self._publish,
            "get_status": self._get_status,
            "discard_draft": self._discard_draft,
        }

        handler = dispatch.get(operation)
        if not handler:
            ops = ", ".join(dispatch.keys())
            return Response(
                message=f"Unknown operation '{operation}'. Available: {ops}",
                break_loop=False,
            )

        try:
            result = await handler(**kwargs)
            return Response(message=json.dumps(result, indent=2), break_loop=False)
        except Exception as e:
            return Response(
                message=json.dumps({"status": "error", "error": str(e)}),
                break_loop=False,
            )

    # ------------------------------------------------------------------
    # start
    # ------------------------------------------------------------------

    async def _start(self, **kwargs) -> dict:
        """
        Begin playbook creation for a venture.
        Detects existing draft and offers to resume.
        """
        venture_slug = kwargs.get("venture_slug")
        if not venture_slug:
            return {"status": "error", "error": "venture_slug required"}

        venture_name = kwargs.get("venture_name", venture_slug.replace("_", " ").title())
        draft = _load_draft(venture_slug)

        if draft and draft.get("status") == "draft":
            last_step = draft.get("last_completed_step")
            completed = draft.get("completed_steps", [])
            remaining = [s for s in PLAYBOOK_STEPS if s not in completed]

            return {
                "status": "draft_found",
                "venture_slug": venture_slug,
                "venture_name": draft.get("venture_name", venture_name),
                "last_completed_step": last_step,
                "completed_steps": completed,
                "remaining_steps": remaining,
                "message": (
                    f"Found an existing draft playbook for {venture_name}. "
                    f"Last completed step: {last_step or 'none'}. "
                    f"Remaining: {', '.join(remaining)}. "
                    f"Use operation='resume' to continue, or operation='discard_draft' to start fresh."
                ),
            }

        # New playbook — venture_confirmed is implicit (venture already exists)
        draft_data = {
            "playbook_id": str(uuid.uuid4()),
            "venture_slug": venture_slug,
            "venture_name": venture_name,
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "completed_steps": ["venture_confirmed"],
            "last_completed_step": "venture_confirmed",
            "sections": {},
        }
        _save_draft(venture_slug, draft_data)

        next_step = PLAYBOOK_STEPS[1]  # business_model (skip venture_confirmed — already done)
        prompt_text = STEP_PROMPTS.get(next_step, "").format(venture_name=venture_name)

        return {
            "status": "started",
            "venture_slug": venture_slug,
            "venture_name": venture_name,
            "next_step": next_step,
            "step_prompt": prompt_text,
            "message": (
                f"Playbook creation started for {venture_name}. "
                f"Step 1 of {len(PLAYBOOK_STEPS) - 1}: {next_step}. "
                f"Asking the user: {prompt_text}"
            ),
        }

    # ------------------------------------------------------------------
    # resume
    # ------------------------------------------------------------------

    async def _resume(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        if not venture_slug:
            return {"status": "error", "error": "venture_slug required"}

        draft = _load_draft(venture_slug)
        if not draft:
            return {
                "status": "no_draft",
                "message": f"No draft found for {venture_slug}. Use operation='start' to begin.",
            }

        completed = draft.get("completed_steps", [])
        remaining = [s for s in PLAYBOOK_STEPS if s not in completed]

        if not remaining:
            return {
                "status": "all_steps_complete",
                "message": "All steps completed. Use operation='publish' to finalize.",
            }

        next_step = remaining[0]
        venture_name = draft.get("venture_name", venture_slug)
        prompt_text = STEP_PROMPTS.get(next_step, f"Complete step: {next_step}").format(
            venture_name=venture_name
        )

        return {
            "status": "resumed",
            "venture_slug": venture_slug,
            "next_step": next_step,
            "completed_steps": completed,
            "remaining_steps": remaining,
            "step_prompt": prompt_text,
        }

    # ------------------------------------------------------------------
    # save_step
    # ------------------------------------------------------------------

    async def _save_step(self, **kwargs) -> dict:
        """
        Save content for a completed step and advance to next.

        Args:
            venture_slug: str
            step: str (step name from PLAYBOOK_STEPS)
            content: dict (structured content for this step)
        """
        venture_slug = kwargs.get("venture_slug")
        step = kwargs.get("step")
        content = kwargs.get("content", {})

        if not all([venture_slug, step]):
            return {"status": "error", "error": "Required: venture_slug, step"}

        if step not in PLAYBOOK_STEPS:
            return {"status": "error", "error": f"Unknown step: {step}. Valid: {PLAYBOOK_STEPS}"}

        draft = _load_draft(venture_slug)
        if not draft:
            return {"status": "error", "error": "No draft found. Use operation='start' first."}

        # Save section content
        draft["sections"][step] = content
        if step not in draft["completed_steps"]:
            draft["completed_steps"].append(step)
        draft["last_completed_step"] = step
        draft["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_draft(venture_slug, draft)

        # Determine next step
        completed = draft["completed_steps"]
        remaining = [s for s in PLAYBOOK_STEPS if s not in completed]

        if not remaining:
            return {
                "status": "all_complete",
                "message": (
                    f"All {len(PLAYBOOK_STEPS)} steps complete. "
                    "Use operation='publish' to finalize and publish the playbook."
                ),
            }

        next_step = remaining[0]
        venture_name = draft.get("venture_name", venture_slug)
        prompt_text = STEP_PROMPTS.get(next_step, f"Complete step: {next_step}").format(
            venture_name=venture_name
        )

        return {
            "status": "step_saved",
            "step": step,
            "next_step": next_step,
            "step_prompt": prompt_text,
            "completed_count": len(completed),
            "total_steps": len(PLAYBOOK_STEPS),
        }

    # ------------------------------------------------------------------
    # publish
    # ------------------------------------------------------------------

    async def _publish(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        if not venture_slug:
            return {"status": "error", "error": "venture_slug required"}

        draft = _load_draft(venture_slug)
        if not draft:
            return {"status": "error", "error": "No draft found."}

        # Check all required steps completed
        required = [s for s in PLAYBOOK_STEPS if s != "venture_confirmed"]
        missing = [s for s in required if s not in draft.get("completed_steps", [])]
        if missing and not kwargs.get("force", False):
            return {
                "status": "incomplete",
                "missing_steps": missing,
                "message": f"Missing steps: {', '.join(missing)}. Complete them or pass force=true to publish anyway.",
            }

        pub = _publish_playbook(venture_slug, draft)
        venture_name = draft.get("venture_name", venture_slug)
        version = pub["version"]

        # Push to SurfSense ops space
        surfsense_result = await self._push_to_surfsense(
            venture_slug=venture_slug,
            venture_name=venture_name,
            version=version,
            playbook=draft,
        )

        return {
            "status": "published",
            "venture_slug": venture_slug,
            "venture_name": venture_name,
            "version": version,
            "path": pub["path"],
            "surfsense": surfsense_result,
            "message": (
                f"{venture_name} Playbook v{version} published. "
                f"Stored locally at {pub['path']}. "
                f"Retrieve with: venture_ops get_playbook(venture_slug='{venture_slug}')"
            ),
        }

    # ------------------------------------------------------------------
    # get_status
    # ------------------------------------------------------------------

    async def _get_status(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        if not venture_slug:
            return {"status": "error", "error": "venture_slug required"}

        draft = _load_draft(venture_slug)
        version = _next_version(venture_slug) - 1  # last published

        return {
            "status": "ok",
            "venture_slug": venture_slug,
            "has_draft": draft is not None,
            "draft_last_step": draft.get("last_completed_step") if draft else None,
            "draft_completed_steps": draft.get("completed_steps", []) if draft else [],
            "published_versions": max(version, 0),
            "latest_version": version if version > 0 else None,
        }

    # ------------------------------------------------------------------
    # discard_draft
    # ------------------------------------------------------------------

    async def _discard_draft(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        if not venture_slug:
            return {"status": "error", "error": "venture_slug required"}

        path = _draft_path(venture_slug)
        if path.exists():
            path.unlink()
            return {"status": "ok", "message": "Draft discarded."}
        return {"status": "not_found", "message": "No draft to discard."}

    # ------------------------------------------------------------------
    # SurfSense push
    # ------------------------------------------------------------------

    async def _push_to_surfsense(
        self,
        venture_slug: str,
        venture_name: str,
        version: int,
        playbook: dict,
    ) -> dict:
        try:
            from python.helpers.cortex_surfsense_client import CortexSurfSenseClient
            client = CortexSurfSenseClient.from_agent_config(self.agent)
            if not await client.health_check():
                return {"status": "skipped", "reason": "SurfSense unreachable"}

            space_name = f"{venture_slug}_ops"
            title = f"{venture_name} Playbook v{version}"
            content = json.dumps(playbook, indent=2, ensure_ascii=False)

            result = await client.push_document(
                space_name=space_name,
                title=title,
                content=content,
                metadata={
                    "type": "playbook",
                    "version": version,
                    "venture_slug": venture_slug,
                },
            )
            return {"status": "ok", "space": space_name, "title": title}
        except Exception as e:
            return {"status": "error", "error": str(e)}
