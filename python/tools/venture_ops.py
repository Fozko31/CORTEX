"""
venture_ops tool — Venture Operations Management
=================================================
Agent-callable tool for Op-A shared infrastructure.

Operations:
    health_check        — venture ops status, pending actions, credential warnings, scheduler tasks
    list_tasks          — list recurring tasks for a venture
    add_task            — add a recurring task + register with scheduler
    disable_task        — disable a recurring task
    set_autonomy        — set autonomy rule (venture+class or venture+class+resource)
    get_autonomy        — get autonomy summary for a venture
    list_pending        — list actions waiting for HITL approval
    approve             — approve a pending action (queues for execution)
    reject              — reject a pending action
    set_credential      — store an encrypted credential
    list_credential_keys — list credential names + expiry state (never values)
    delete_credential   — remove a credential
    get_playbook        — retrieve a playbook from venture ops space
"""

import json
from python.cortex.tool import Tool, Response


class VentureOps(Tool):

    async def execute(self, **kwargs) -> Response:
        operation = kwargs.get("operation", "").lower().strip()

        dispatch = {
            "health_check": self._health_check,
            "list_tasks": self._list_tasks,
            "add_task": self._add_task,
            "disable_task": self._disable_task,
            "set_autonomy": self._set_autonomy,
            "get_autonomy": self._get_autonomy,
            "list_pending": self._list_pending,
            "approve": self._approve,
            "reject": self._reject,
            "set_credential": self._set_credential,
            "list_credential_keys": self._list_credential_keys,
            "delete_credential": self._delete_credential,
            "get_playbook": self._get_playbook,
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
    # health_check
    # ------------------------------------------------------------------

    async def _health_check(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        result: dict = {"status": "ok", "timestamp": self._now()}

        # Scheduler tasks
        try:
            from python.helpers.task_scheduler import TaskScheduler
            scheduler = TaskScheduler.get(self.agent)
            tasks = scheduler.tasks if hasattr(scheduler, "tasks") else []
            cortex_tasks = [
                {"name": t.name if hasattr(t, "name") else str(t)}
                for t in tasks
                if "CORTEX" in (t.name if hasattr(t, "name") else "")
                   or "venture" in (t.name if hasattr(t, "name") else "").lower()
            ]
            result["scheduler_tasks"] = cortex_tasks
        except Exception as e:
            result["scheduler_tasks"] = {"error": str(e)}

        # Pending HITL actions
        try:
            from python.helpers.cortex_venture_action_log import VentureActionLog
            log = VentureActionLog()
            result["pending_actions"] = log.pending_count(venture_slug)
        except Exception as e:
            result["pending_actions"] = {"error": str(e)}

        # Credential expiry warnings
        if venture_slug:
            try:
                from python.helpers.cortex_credential_vault import CortexCredentialVault
                vault = CortexCredentialVault(venture_slug)
                expiring = vault.expiring_soon()
                result["credential_warnings"] = expiring
            except Exception as e:
                result["credential_warnings"] = {"error": str(e)}

        # Venture task queue
        try:
            from python.helpers.cortex_venture_task_queue import VentureTaskQueue
            q = VentureTaskQueue()
            tasks = q.list_tasks(venture_slug=venture_slug, enabled_only=True)
            result["venture_tasks"] = [
                {"name": t["name"], "cadence": t["cadence"], "status": t["status"],
                 "last_run": t["last_run"]}
                for t in tasks
            ]
        except Exception as e:
            result["venture_tasks"] = {"error": str(e)}

        return result

    # ------------------------------------------------------------------
    # list_tasks / add_task / disable_task
    # ------------------------------------------------------------------

    async def _list_tasks(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        from python.helpers.cortex_venture_task_queue import VentureTaskQueue
        q = VentureTaskQueue()
        tasks = q.list_tasks(venture_slug=venture_slug)
        return {"status": "ok", "tasks": tasks, "count": len(tasks)}

    async def _add_task(self, **kwargs) -> dict:
        required = ["venture_slug", "task_type", "name", "cadence", "prompt"]
        for field in required:
            if not kwargs.get(field):
                return {"status": "error", "error": f"Missing required field: {field}"}

        from python.helpers.cortex_venture_task_queue import VentureTaskQueue
        q = VentureTaskQueue()
        task = q.add_task(
            venture_slug=kwargs["venture_slug"],
            task_type=kwargs["task_type"],
            name=kwargs["name"],
            cadence=kwargs["cadence"],
            prompt=kwargs["prompt"],
        )

        # Optionally register with scheduler
        if kwargs.get("register_scheduler", True):
            reg_result = await q.register_with_scheduler(self.agent, task["task_id"])
            task["scheduler_registration"] = reg_result

        return {"status": "ok", "task": task}

    async def _disable_task(self, **kwargs) -> dict:
        task_id = kwargs.get("task_id")
        if not task_id:
            return {"status": "error", "error": "task_id required"}

        from python.helpers.cortex_venture_task_queue import VentureTaskQueue
        q = VentureTaskQueue()
        result = q.disable_task(task_id)

        # Also deregister from scheduler if possible
        task = q.get_task(task_id)
        if task:
            try:
                await q.deregister_from_scheduler(self.agent, task_id)
            except Exception:
                pass

        return {"status": "ok", "task_id": task_id}

    # ------------------------------------------------------------------
    # set_autonomy / get_autonomy
    # ------------------------------------------------------------------

    async def _set_autonomy(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        action_class = kwargs.get("action_class")
        level = kwargs.get("level")

        if not all([venture_slug, action_class, level]):
            return {
                "status": "error",
                "error": "Required: venture_slug, action_class, level"
            }

        from python.helpers.cortex_autonomy_policy import CortexAutonomyPolicy
        policy = CortexAutonomyPolicy()

        # Venture default — no specific action class
        if action_class.upper() == "DEFAULT":
            return policy.set_venture_default(
                venture_slug=venture_slug,
                default_level=level,
                spend_auto_threshold_eur=float(kwargs.get("spend_auto_threshold_eur", 0.0)),
                reason=kwargs.get("reason", ""),
            )

        return policy.set_rule(
            venture_slug=venture_slug,
            action_class=action_class,
            level=level,
            resource_id=kwargs.get("resource_id"),
            resource_description=kwargs.get("resource_description", ""),
            reason=kwargs.get("reason", ""),
            set_by="user",
        )

    async def _get_autonomy(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        if not venture_slug:
            return {"status": "error", "error": "venture_slug required"}

        from python.helpers.cortex_autonomy_policy import CortexAutonomyPolicy
        policy = CortexAutonomyPolicy()
        return {
            "status": "ok",
            **policy.get_venture_summary(venture_slug),
        }

    # ------------------------------------------------------------------
    # list_pending / approve / reject
    # ------------------------------------------------------------------

    async def _list_pending(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        from python.helpers.cortex_venture_action_log import VentureActionLog
        log = VentureActionLog()
        pending = log.list_pending(venture_slug=venture_slug)
        return {
            "status": "ok",
            "pending": pending,
            "count": len(pending),
        }

    async def _approve(self, **kwargs) -> dict:
        action_id = kwargs.get("action_id")
        if not action_id:
            return {"status": "error", "error": "action_id required"}

        from python.helpers.cortex_venture_action_log import VentureActionLog
        log = VentureActionLog()
        action = log.get_action(action_id)
        if not action:
            return {"status": "error", "error": f"Action {action_id} not found"}
        if action["status"] != "pending_approval":
            return {"status": "error", "error": f"Action status is '{action['status']}', not pending_approval"}

        log.approve(action_id, approved_by="user")
        return {
            "status": "ok",
            "action_id": action_id,
            "message": "Action approved. CORTEX will execute on next opportunity.",
            "tool_used": action.get("tool_used"),
            "inputs": action.get("inputs"),
        }

    async def _reject(self, **kwargs) -> dict:
        action_id = kwargs.get("action_id")
        if not action_id:
            return {"status": "error", "error": "action_id required"}

        from python.helpers.cortex_venture_action_log import VentureActionLog
        log = VentureActionLog()
        action = log.get_action(action_id)
        if not action:
            return {"status": "error", "error": f"Action {action_id} not found"}

        log.reject(action_id, approved_by="user")
        return {"status": "ok", "action_id": action_id, "message": "Action rejected and logged."}

    # ------------------------------------------------------------------
    # set_credential / list_credential_keys / delete_credential
    # ------------------------------------------------------------------

    async def _set_credential(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        name = kwargs.get("name")
        value = kwargs.get("value")

        if not all([venture_slug, name, value]):
            return {"status": "error", "error": "Required: venture_slug, name, value"}

        from python.helpers.cortex_credential_vault import CortexCredentialVault
        vault = CortexCredentialVault(venture_slug)
        result = vault.set(
            name=name,
            value=value,
            description=kwargs.get("description", ""),
            expires_at=kwargs.get("expires_at"),
        )
        return {**result, "message": f"Credential '{name}' stored securely for {venture_slug}."}

    async def _list_credential_keys(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        if not venture_slug:
            return {"status": "error", "error": "venture_slug required"}

        from python.helpers.cortex_credential_vault import CortexCredentialVault
        vault = CortexCredentialVault(venture_slug)
        keys = vault.list_keys()
        warnings = [k for k in keys if k["expiry_status"] in ("warning", "expired")]
        return {
            "status": "ok",
            "venture_slug": venture_slug,
            "credentials": keys,
            "count": len(keys),
            "expiry_warnings": len(warnings),
        }

    async def _delete_credential(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        name = kwargs.get("name")
        if not all([venture_slug, name]):
            return {"status": "error", "error": "Required: venture_slug, name"}

        from python.helpers.cortex_credential_vault import CortexCredentialVault
        vault = CortexCredentialVault(venture_slug)
        return vault.delete(name)

    # ------------------------------------------------------------------
    # get_playbook
    # ------------------------------------------------------------------

    async def _get_playbook(self, **kwargs) -> dict:
        venture_slug = kwargs.get("venture_slug")
        version = kwargs.get("version")  # optional — returns latest if omitted

        if not venture_slug:
            return {"status": "error", "error": "venture_slug required"}

        # Check local JSON first
        from pathlib import Path
        import json as _json

        playbook_dir = Path(f"usr/memory/cortex_main/ventures/{venture_slug}_playbooks")
        if not playbook_dir.exists():
            return {"status": "not_found", "venture_slug": venture_slug}

        playbook_files = sorted(playbook_dir.glob("playbook_v*.json"), reverse=True)
        if not playbook_files:
            return {"status": "not_found", "venture_slug": venture_slug}

        if version:
            target = playbook_dir / f"playbook_v{version}.json"
            if not target.exists():
                return {"status": "not_found", "version": version}
            playbook = _json.loads(target.read_text(encoding="utf-8"))
        else:
            playbook = _json.loads(playbook_files[0].read_text(encoding="utf-8"))

        return {"status": "ok", "playbook": playbook}

    # ------------------------------------------------------------------
    # Util
    # ------------------------------------------------------------------

    def _now(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
