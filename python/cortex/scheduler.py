"""
python/cortex/scheduler.py — Task Scheduler
============================================
Re-exports AZ's TaskScheduler during H1 transition.
Replaced with APScheduler-backed implementation in H1-C.

CORTEX code imports:
    from python.cortex.scheduler import TaskScheduler, ScheduledTask, TaskSchedule

Usage pattern (all 5 CORTEX autonomous loops):
    scheduler = TaskScheduler.get()
    if scheduler.get_task_by_name(task_name):
        return  # already registered
    schedule = TaskSchedule(minute="0", hour="3", day="*", month="*", weekday="0", timezone="UTC")
    task = ScheduledTask.create(name=..., system_prompt=..., prompt=..., schedule=schedule)
    await scheduler.add_task(task)

H1-C replacement: APScheduler with in-memory job store.
    - Jobs re-registered on startup by _15_register_schedulers.py
    - Same TaskSchedule(minute, hour, day, month, weekday, timezone) API
    - Same ScheduledTask.create() signature
    - Fly.io compatible: in-memory job store, startup re-registration handles restarts
"""
from python.helpers.task_scheduler import (
    TaskScheduler,
    ScheduledTask,
    TaskSchedule,
    TaskPlan,
    TaskState,
    TaskType,
    AdHocTask,
    PlannedTask,
    SchedulerTaskList,
    SCHEDULER_FOLDER,
)

__all__ = [
    "TaskScheduler",
    "ScheduledTask",
    "TaskSchedule",
    "TaskPlan",
    "TaskState",
    "TaskType",
    "AdHocTask",
    "PlannedTask",
    "SchedulerTaskList",
    "SCHEDULER_FOLDER",
]
