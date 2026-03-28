"""
tests/test_cortex_scheduler.py — Unit tests for python/cortex/scheduler.py

Tests the APScheduler 3.x backend in complete isolation.
No actual jobs fire (we test registration, not execution timing).
"""
import asyncio
import pytest

from python.cortex.scheduler import (
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_scheduler():
    """Reset the TaskScheduler singleton before and after every test."""
    TaskScheduler._reset()
    yield
    TaskScheduler._reset()


def make_schedule(**kwargs) -> TaskSchedule:
    defaults = dict(minute="0", hour="3", day="*", month="*", weekday="0", timezone="UTC")
    defaults.update(kwargs)
    return TaskSchedule(**defaults)


async def _noop_job():
    """Dummy async callable for testing."""
    pass


# ---------------------------------------------------------------------------
# TaskSchedule tests
# ---------------------------------------------------------------------------

class TestTaskSchedule:
    def test_defaults(self):
        s = TaskSchedule()
        assert s.minute == "*"
        assert s.timezone == "UTC"

    def test_to_crontab(self):
        s = make_schedule(minute="30", hour="2")
        assert s.to_crontab() == "30 2 * * 0"

    def test_to_cron_trigger(self):
        from apscheduler.triggers.cron import CronTrigger
        s = make_schedule(minute="0", hour="3", weekday="1")
        trigger = s.to_cron_trigger()
        assert isinstance(trigger, CronTrigger)

    def test_custom_timezone(self):
        s = TaskSchedule(minute="0", hour="1", day="*", month="*",
                         weekday="6", timezone="CET")
        trigger = s.to_cron_trigger()
        assert trigger is not None


# ---------------------------------------------------------------------------
# ScheduledTask tests
# ---------------------------------------------------------------------------

class TestScheduledTask:
    def test_create_with_callable(self):
        task = ScheduledTask.create(
            name="test_task",
            callable_fn=_noop_job,
            schedule=make_schedule(),
        )
        assert task.name == "test_task"
        assert task.callable_fn is _noop_job
        assert task.id  # UUID assigned

    def test_create_without_callable_logs_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="cortex.scheduler"):
            task = ScheduledTask.create(
                name="legacy_task",
                system_prompt="You are CORTEX.",
                prompt="Do something.",
                schedule=make_schedule(),
            )
        assert task.callable_fn is None
        assert "callable_fn" in caplog.text

    def test_each_task_has_unique_id(self):
        t1 = ScheduledTask.create(name="t1", callable_fn=_noop_job, schedule=make_schedule())
        t2 = ScheduledTask.create(name="t2", callable_fn=_noop_job, schedule=make_schedule())
        assert t1.id != t2.id

    def test_extra_kwargs_ignored(self):
        """AZ compat: extra kwargs like attachments, context_id are silently ignored."""
        task = ScheduledTask.create(
            name="t",
            callable_fn=_noop_job,
            schedule=make_schedule(),
            attachments=[],
            context_id=None,
            project_name=None,
        )
        assert task.name == "t"


# ---------------------------------------------------------------------------
# TaskScheduler singleton tests
# ---------------------------------------------------------------------------

class TestTaskSchedulerSingleton:
    def test_get_returns_same_instance(self):
        a = TaskScheduler.get()
        b = TaskScheduler.get()
        assert a is b

    def test_get_ignores_extra_args(self):
        """AZ compat: TaskScheduler.get(agent) must not raise."""
        scheduler = TaskScheduler.get("fake_agent")
        assert scheduler is not None

    def test_reset_clears_singleton(self):
        a = TaskScheduler.get()
        TaskScheduler._reset()
        b = TaskScheduler.get()
        assert a is not b


# ---------------------------------------------------------------------------
# TaskScheduler registration tests
# ---------------------------------------------------------------------------

class TestTaskSchedulerRegistration:
    @pytest.mark.asyncio
    async def test_add_task_registers_by_name(self):
        scheduler = TaskScheduler.get()
        task = ScheduledTask.create(name="digest", callable_fn=_noop_job, schedule=make_schedule())
        await scheduler.add_task(task)
        assert scheduler.get_task_by_name("digest") is task

    @pytest.mark.asyncio
    async def test_get_task_by_name_returns_none_for_unknown(self):
        scheduler = TaskScheduler.get()
        assert scheduler.get_task_by_name("nonexistent") is None

    @pytest.mark.asyncio
    async def test_add_task_without_callable_is_skipped(self):
        scheduler = TaskScheduler.get()
        task = ScheduledTask.create(
            name="noop", system_prompt="x", prompt="y", schedule=make_schedule()
        )
        await scheduler.add_task(task)
        assert scheduler.get_task_by_name("noop") is None  # not registered

    @pytest.mark.asyncio
    async def test_get_tasks_returns_all(self):
        scheduler = TaskScheduler.get()
        t1 = ScheduledTask.create(name="a", callable_fn=_noop_job, schedule=make_schedule())
        t2 = ScheduledTask.create(name="b", callable_fn=_noop_job, schedule=make_schedule())
        await scheduler.add_task(t1)
        await scheduler.add_task(t2)
        names = {t.name for t in scheduler.get_tasks()}
        assert names == {"a", "b"}

    @pytest.mark.asyncio
    async def test_remove_task_by_name(self):
        scheduler = TaskScheduler.get()
        task = ScheduledTask.create(name="backup", callable_fn=_noop_job, schedule=make_schedule())
        await scheduler.add_task(task)
        assert scheduler.get_task_by_name("backup") is not None
        await scheduler.remove_task_by_name("backup")
        assert scheduler.get_task_by_name("backup") is None

    @pytest.mark.asyncio
    async def test_remove_task_by_uuid(self):
        scheduler = TaskScheduler.get()
        task = ScheduledTask.create(name="bench", callable_fn=_noop_job, schedule=make_schedule())
        await scheduler.add_task(task)
        await scheduler.remove_task_by_uuid(task.id)
        assert scheduler.get_task_by_name("bench") is None

    @pytest.mark.asyncio
    async def test_remove_task_alias(self):
        """remove_task(id) is the alias venture_task_queue uses."""
        scheduler = TaskScheduler.get()
        task = ScheduledTask.create(name="venture", callable_fn=_noop_job, schedule=make_schedule())
        await scheduler.add_task(task)
        await scheduler.remove_task(task.id)
        assert scheduler.get_task_by_name("venture") is None

    @pytest.mark.asyncio
    async def test_double_register_guard(self):
        """Standard pattern: guard with get_task_by_name before add_task."""
        scheduler = TaskScheduler.get()
        task1 = ScheduledTask.create(name="loop1", callable_fn=_noop_job, schedule=make_schedule())
        task2 = ScheduledTask.create(name="loop1", callable_fn=_noop_job, schedule=make_schedule())

        if not scheduler.get_task_by_name("loop1"):
            await scheduler.add_task(task1)
        if not scheduler.get_task_by_name("loop1"):
            await scheduler.add_task(task2)

        # Only one should be registered
        assert len([t for t in scheduler.get_tasks() if t.name == "loop1"]) == 1

    @pytest.mark.asyncio
    async def test_get_task_by_uuid(self):
        scheduler = TaskScheduler.get()
        task = ScheduledTask.create(name="z", callable_fn=_noop_job, schedule=make_schedule())
        await scheduler.add_task(task)
        found = scheduler.get_task_by_uuid(task.id)
        assert found is task

    @pytest.mark.asyncio
    async def test_find_task_by_name_partial(self):
        scheduler = TaskScheduler.get()
        t = ScheduledTask.create(name="CORTEX Weekly Digest", callable_fn=_noop_job,
                                  schedule=make_schedule())
        await scheduler.add_task(t)
        results = scheduler.find_task_by_name("Weekly")
        assert len(results) == 1
        assert results[0].name == "CORTEX Weekly Digest"


# ---------------------------------------------------------------------------
# AZ-compat stub tests
# ---------------------------------------------------------------------------

class TestAZCompatStubs:
    def test_task_plan_create(self):
        plan = TaskPlan.create()
        assert plan is not None

    def test_task_state_constants(self):
        assert TaskState.PENDING == "pending"
        assert TaskState.RUNNING == "running"

    def test_task_type_constants(self):
        assert TaskType.SCHEDULED == "scheduled"

    def test_adhoc_task_instantiates(self):
        t = AdHocTask()
        assert t is not None

    def test_planned_task_instantiates(self):
        t = PlannedTask()
        assert t is not None

    def test_scheduler_task_list(self):
        stl = SchedulerTaskList.get()
        assert stl is not None

    def test_scheduler_folder_is_string(self):
        assert isinstance(SCHEDULER_FOLDER, str)

    def test_import_all_symbols(self):
        """Ensures no ImportError for any symbol CORTEX code imports."""
        from python.cortex.scheduler import (  # noqa: F401
            TaskScheduler, ScheduledTask, TaskSchedule,
            TaskPlan, TaskState, TaskType,
            AdHocTask, PlannedTask, SchedulerTaskList, SCHEDULER_FOLDER,
        )
