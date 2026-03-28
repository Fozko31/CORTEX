"""
python/cortex/scheduler.py — CORTEX Task Scheduler
====================================================
APScheduler 3.x backend replacing Agent Zero's TaskScheduler.

Design:
  - AsyncIOScheduler (APScheduler 3.x) as the engine
  - In-memory job store — no Redis, no SQLite, no external services
  - Lazy start: scheduler starts on first add_task() call
  - Restart-safe: _15_register_schedulers.py re-registers all jobs on startup
  - Fly.io compatible: in-memory store is fine because startup re-registration handles restarts

Public API (matches what all CORTEX files expect):
    from python.cortex.scheduler import TaskScheduler, ScheduledTask, TaskSchedule

    schedule = TaskSchedule(minute="0", hour="3", day="*", month="*",
                            weekday="0", timezone="UTC")
    task = ScheduledTask.create(
        name="my_task",
        callable_fn=my_async_function,
        schedule=schedule,
    )
    scheduler = TaskScheduler.get()
    if not scheduler.get_task_by_name("my_task"):
        await scheduler.add_task(task)

    # Remove a task:
    existing = scheduler.get_task_by_name("my_task")
    if existing:
        await scheduler.remove_task(existing.id)

Backward compatibility:
    ScheduledTask.create() accepts system_prompt/prompt kwargs (AZ pattern) but
    logs a warning and skips registration if callable_fn is not provided.
    This prevents silent failures during transition.

Re-exported stubs (AZ imports that CORTEX code referenced but doesn't use):
    TaskPlan, TaskState, TaskType, AdHocTask, PlannedTask,
    SchedulerTaskList, SCHEDULER_FOLDER
    — all are no-ops; present only to prevent ImportError during transition.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger("cortex.scheduler")

# ---------------------------------------------------------------------------
# Stub re-exports — prevent ImportError for any code that imported these
# from python.cortex.scheduler (they were re-exported from AZ in the old file)
# ---------------------------------------------------------------------------

SCHEDULER_FOLDER = "scheduler"  # AZ stored tasks here; we use in-memory only


class TaskType:
    SCHEDULED = "scheduled"
    AD_HOC = "adhoc"
    PLANNED = "planned"


class TaskState:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class TaskPlan:
    """Stub — AZ's time-plan model. Not used by CORTEX APScheduler backend."""
    @classmethod
    def create(cls, *args, **kwargs):
        return cls()


class AdHocTask:
    """Stub — AZ's one-shot task. Not used in CORTEX."""
    pass


class PlannedTask:
    """Stub — AZ's planned-run task. Not used in CORTEX."""
    pass


class SchedulerTaskList:
    """Stub — AZ's persistent task list. Not used in CORTEX (in-memory only)."""
    @classmethod
    def get(cls):
        return cls()


# ---------------------------------------------------------------------------
# TaskSchedule — cron parameters
# ---------------------------------------------------------------------------

@dataclass
class TaskSchedule:
    """
    Cron schedule definition.
    Same field names as AZ's TaskSchedule so existing CORTEX code works unchanged.
    """
    minute: str = "*"
    hour: str = "*"
    day: str = "*"
    month: str = "*"
    weekday: str = "*"
    timezone: str = "UTC"

    def to_cron_trigger(self) -> CronTrigger:
        """Convert to APScheduler CronTrigger."""
        return CronTrigger(
            minute=self.minute,
            hour=self.hour,
            day=self.day,
            month=self.month,
            day_of_week=self.weekday if self.weekday != "*" else None,
            timezone=self.timezone,
        )

    def to_crontab(self) -> str:
        """AZ-compat helper used in some logging paths."""
        return f"{self.minute} {self.hour} {self.day} {self.month} {self.weekday}"


# ---------------------------------------------------------------------------
# ScheduledTask — task definition
# ---------------------------------------------------------------------------

@dataclass
class ScheduledTask:
    """
    A named task with a cron schedule and an async callable.

    The callable receives no arguments. Any agent/context dependencies
    should be captured via closure in the _scheduled_* functions.
    """
    id: str
    name: str
    schedule: TaskSchedule
    callable_fn: Optional[Callable[[], Coroutine[Any, Any, Any]]]
    # AZ-compat fields — stored but not used by APScheduler backend
    system_prompt: str = ""
    prompt: str = ""

    @classmethod
    def create(
        cls,
        name: str,
        schedule: TaskSchedule,
        callable_fn: Optional[Callable] = None,
        # AZ backward-compat kwargs — accepted but generate a warning if callable_fn missing
        system_prompt: str = "",
        prompt: str = "",
        **_kwargs: Any,
    ) -> "ScheduledTask":
        """
        Factory. Primary interface:
            ScheduledTask.create(name, callable_fn=fn, schedule=schedule)

        AZ backward-compat (callable_fn=None):
            ScheduledTask.create(name, system_prompt=..., prompt=..., schedule=schedule)
            → logs warning; task is created but will not be registered with APScheduler.
        """
        if callable_fn is None and (system_prompt or prompt):
            log.warning(
                "ScheduledTask.create() called with system_prompt/prompt but no callable_fn. "
                "Task '%s' will not be scheduled. Provide callable_fn= to register it.",
                name,
            )
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            schedule=schedule,
            callable_fn=callable_fn,
            system_prompt=system_prompt,
            prompt=prompt,
        )


# ---------------------------------------------------------------------------
# TaskScheduler — singleton backed by APScheduler AsyncIOScheduler
# ---------------------------------------------------------------------------

class TaskScheduler:
    """
    CORTEX task scheduler singleton.
    Backed by APScheduler 3.x AsyncIOScheduler (in-memory job store).
    """

    _instance: Optional["TaskScheduler"] = None
    _tasks: dict[str, ScheduledTask]   # name → task
    _apscheduler: AsyncIOScheduler

    @classmethod
    def get(cls, *_args: Any, **_kwargs: Any) -> "TaskScheduler":
        """
        Return the singleton instance.
        Accepts (and ignores) any positional/keyword args for AZ-compat
        (AZ's TaskScheduler.get() sometimes received an agent).
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._tasks = {}
        self._apscheduler = AsyncIOScheduler()

    def _ensure_started(self) -> None:
        """Start APScheduler lazily — must be called from a running event loop."""
        if not self._apscheduler.running:
            try:
                self._apscheduler.start()
                log.info("CORTEX scheduler started (APScheduler 3.x AsyncIOScheduler)")
            except Exception as exc:
                log.error("Failed to start CORTEX scheduler: %s", exc)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def add_task(self, task: ScheduledTask) -> "TaskScheduler":
        """Register a task with APScheduler. No-op if callable_fn is None."""
        if task.callable_fn is None:
            log.warning(
                "Skipping task '%s': no callable_fn provided. "
                "Update register function to pass callable_fn=.",
                task.name,
            )
            return self

        self._ensure_started()
        try:
            trigger = task.schedule.to_cron_trigger()
            self._apscheduler.add_job(
                task.callable_fn,
                trigger,
                id=task.id,
                name=task.name,
                replace_existing=True,
                misfire_grace_time=300,  # 5 min grace — handles Fly cold starts
            )
            self._tasks[task.name] = task
            log.info(
                "Scheduled task '%s' → cron(%s)", task.name, task.schedule.to_crontab()
            )
        except Exception as exc:
            log.error("Failed to schedule task '%s': %s", task.name, exc)
        return self

    async def remove_task(self, task_id: str) -> "TaskScheduler":
        """Remove a task by its UUID. AZ-compat alias: remove_task_by_uuid."""
        return await self.remove_task_by_uuid(task_id)

    async def remove_task_by_uuid(self, task_id: str) -> "TaskScheduler":
        """Remove a task by its UUID."""
        # Find by ID and remove from name registry
        name_to_remove = None
        for name, task in list(self._tasks.items()):
            if task.id == task_id:
                name_to_remove = name
                break
        if name_to_remove:
            del self._tasks[name_to_remove]
        try:
            self._apscheduler.remove_job(task_id)
            log.info("Removed scheduled task id=%s", task_id)
        except Exception:
            pass  # job may not exist in APScheduler yet
        return self

    async def remove_task_by_name(self, name: str) -> "TaskScheduler":
        """Remove a task by name."""
        task = self._tasks.pop(name, None)
        if task:
            await self.remove_task_by_uuid(task.id)
        return self

    def get_task_by_name(self, name: str) -> Optional[ScheduledTask]:
        """Return the task registered under this name, or None."""
        return self._tasks.get(name)

    def get_task_by_uuid(self, task_id: str) -> Optional[ScheduledTask]:
        """Return task by UUID."""
        for task in self._tasks.values():
            if task.id == task_id:
                return task
        return None

    def get_tasks(self) -> list[ScheduledTask]:
        """Return all registered tasks."""
        return list(self._tasks.values())

    def find_task_by_name(self, name: str) -> list[ScheduledTask]:
        """Return tasks whose name contains the search string."""
        return [t for t in self._tasks.values() if name in t.name]

    def shutdown(self, wait: bool = False) -> None:
        """Shutdown APScheduler. Called on app exit."""
        if self._apscheduler.running:
            self._apscheduler.shutdown(wait=wait)
            log.info("CORTEX scheduler shut down")

    # ------------------------------------------------------------------
    # Class-level reset (tests only)
    # ------------------------------------------------------------------

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton — for test isolation only."""
        if cls._instance is not None:
            try:
                cls._instance.shutdown(wait=False)
            except Exception:
                pass
            cls._instance = None


__all__ = [
    "TaskScheduler",
    "ScheduledTask",
    "TaskSchedule",
    # AZ-compat stubs
    "TaskPlan",
    "TaskState",
    "TaskType",
    "AdHocTask",
    "PlannedTask",
    "SchedulerTaskList",
    "SCHEDULER_FOLDER",
]
