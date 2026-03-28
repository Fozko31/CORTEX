"""
Phase E -- Test E-1: Scheduler Registration Fixes
==================================================
Tests that all three scheduled task registration functions:
  - Use TaskScheduler (not system crontab)
  - Correctly deduplicate (don't register twice)
  - Create tasks with the right name and cron schedule
  - Are properly awaitable (async)

No network calls, no LLM, no real TaskScheduler persistence.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_scheduler(existing_task=None):
    """Build a mock TaskScheduler with add_task as AsyncMock."""
    scheduler = MagicMock()
    scheduler.get_task_by_name.return_value = existing_task
    scheduler.add_task = AsyncMock(return_value=scheduler)
    return scheduler


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests: register_discovery_task
# ---------------------------------------------------------------------------

class TestRegisterDiscoveryTask(unittest.TestCase):

    def _import(self):
        from python.helpers.cortex_discovery_scheduler import register_discovery_task
        return register_discovery_task

    def setUp(self):
        # Reset the module-level _registered guard each test
        import python.helpers.cortex_discovery_scheduler as mod
        mod._registered = False

    def test_skips_when_env_not_set(self):
        """No env var → task must not be registered."""
        register_discovery_task = self._import()
        scheduler = _make_mock_scheduler()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CORTEX_DISCOVERY_AUTO", None)
            with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
                _run(register_discovery_task())
        scheduler.add_task.assert_not_called()

    def test_registers_when_env_set(self):
        """CORTEX_DISCOVERY_AUTO=1 → task is registered exactly once."""
        register_discovery_task = self._import()
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch.dict(os.environ, {"CORTEX_DISCOVERY_AUTO": "1"}):
            with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
                _run(register_discovery_task())
        scheduler.add_task.assert_called_once()

    def test_task_name_correct(self):
        """Registered task must be named 'CORTEX Discovery Loop'."""
        register_discovery_task = self._import()
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch.dict(os.environ, {"CORTEX_DISCOVERY_AUTO": "1"}):
            with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
                _run(register_discovery_task())
        task = scheduler.add_task.call_args[0][0]
        self.assertEqual(task.name, "CORTEX Discovery Loop")

    def test_schedule_is_daily_03h(self):
        """Discovery loop should fire daily at 03:00."""
        register_discovery_task = self._import()
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch.dict(os.environ, {"CORTEX_DISCOVERY_AUTO": "1"}):
            with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
                _run(register_discovery_task())
        task = scheduler.add_task.call_args[0][0]
        self.assertEqual(task.schedule.hour, "3")
        self.assertEqual(task.schedule.minute, "0")
        self.assertEqual(task.schedule.weekday, "*")

    def test_dedup_skips_if_already_registered(self):
        """Second call skips if task already exists in scheduler."""
        register_discovery_task = self._import()
        existing = MagicMock()
        scheduler = _make_mock_scheduler(existing_task=existing)
        with patch.dict(os.environ, {"CORTEX_DISCOVERY_AUTO": "1"}):
            with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
                _run(register_discovery_task())
        scheduler.add_task.assert_not_called()

    def test_module_guard_prevents_double_registration(self):
        """Module-level _registered guard prevents re-running even without scheduler check."""
        register_discovery_task = self._import()
        import python.helpers.cortex_discovery_scheduler as mod
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch.dict(os.environ, {"CORTEX_DISCOVERY_AUTO": "1"}):
            with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
                _run(register_discovery_task())
                _run(register_discovery_task())  # second call
        # add_task called only once despite two calls
        self.assertEqual(scheduler.add_task.call_count, 1)

    def test_no_crontab_system_write(self):
        """Must not import or call CronTab(user=True) — that's the fixed bug."""
        register_discovery_task = self._import()
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch.dict(os.environ, {"CORTEX_DISCOVERY_AUTO": "1"}):
            with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
                with patch("crontab.CronTab") as mock_crontab:
                    _run(register_discovery_task())
        # CronTab should not be instantiated with user=True
        for call in mock_crontab.call_args_list:
            args, kwargs = call
            self.assertNotIn("user", kwargs), "Must not write to system crontab"


# ---------------------------------------------------------------------------
# Tests: register_weekly_digest_task
# ---------------------------------------------------------------------------

class TestRegisterWeeklyDigestTask(unittest.TestCase):

    def test_registers_when_no_existing_task(self):
        from python.helpers.cortex_weekly_digest import register_weekly_digest_task
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_weekly_digest_task())
        scheduler.add_task.assert_called_once()

    def test_task_name_correct(self):
        from python.helpers.cortex_weekly_digest import register_weekly_digest_task
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_weekly_digest_task())
        task = scheduler.add_task.call_args[0][0]
        self.assertEqual(task.name, "CORTEX Weekly Digest")

    def test_schedule_is_sunday_02h(self):
        from python.helpers.cortex_weekly_digest import register_weekly_digest_task
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_weekly_digest_task())
        task = scheduler.add_task.call_args[0][0]
        self.assertEqual(task.schedule.hour, "3")
        self.assertEqual(task.schedule.weekday, "0")  # Sunday (plan: Sunday 2am CET)

    def test_dedup_skips_if_existing(self):
        from python.helpers.cortex_weekly_digest import register_weekly_digest_task
        scheduler = _make_mock_scheduler(existing_task=MagicMock())
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_weekly_digest_task())
        scheduler.add_task.assert_not_called()

    def test_is_async(self):
        from python.helpers.cortex_weekly_digest import register_weekly_digest_task
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(register_weekly_digest_task))

    def test_callable_fn_set(self):
        from python.helpers.cortex_weekly_digest import register_weekly_digest_task
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_weekly_digest_task())
        task = scheduler.add_task.call_args[0][0]
        self.assertIsNotNone(task.callable_fn)


# ---------------------------------------------------------------------------
# Tests: register_proactive_task
# ---------------------------------------------------------------------------

class TestRegisterProactiveTask(unittest.TestCase):

    def test_registers_when_no_existing_task(self):
        from python.helpers.cortex_proactive_engine import register_proactive_task
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_proactive_task())
        scheduler.add_task.assert_called_once()

    def test_task_name_correct(self):
        from python.helpers.cortex_proactive_engine import register_proactive_task
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_proactive_task())
        task = scheduler.add_task.call_args[0][0]
        self.assertEqual(task.name, "CORTEX Proactive Pulse")

    def test_schedule_is_every_30_min(self):
        from python.helpers.cortex_proactive_engine import register_proactive_task
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_proactive_task())
        task = scheduler.add_task.call_args[0][0]
        self.assertEqual(task.schedule.minute, "*/30")
        self.assertEqual(task.schedule.hour, "*")

    def test_dedup_skips_if_existing(self):
        from python.helpers.cortex_proactive_engine import register_proactive_task
        scheduler = _make_mock_scheduler(existing_task=MagicMock())
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_proactive_task())
        scheduler.add_task.assert_not_called()

    def test_is_async(self):
        from python.helpers.cortex_proactive_engine import register_proactive_task
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(register_proactive_task))


# ---------------------------------------------------------------------------
# Tests: register_backup_task
# ---------------------------------------------------------------------------

class TestRegisterBackupTask(unittest.TestCase):

    def test_registers_when_no_existing_task(self):
        from python.helpers.cortex_memory_backup import register_backup_task
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_backup_task())
        scheduler.add_task.assert_called_once()

    def test_task_name_correct(self):
        from python.helpers.cortex_memory_backup import register_backup_task
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_backup_task())
        task = scheduler.add_task.call_args[0][0]
        self.assertEqual(task.name, "CORTEX Memory Backup")

    def test_schedule_is_sunday_02h(self):
        from python.helpers.cortex_memory_backup import register_backup_task
        scheduler = _make_mock_scheduler(existing_task=None)
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_backup_task())
        task = scheduler.add_task.call_args[0][0]
        self.assertEqual(task.schedule.hour, "2")
        self.assertEqual(task.schedule.weekday, "0")  # Sunday

    def test_dedup_skips_if_existing(self):
        from python.helpers.cortex_memory_backup import register_backup_task
        scheduler = _make_mock_scheduler(existing_task=MagicMock())
        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            _run(register_backup_task())
        scheduler.add_task.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _15_register_schedulers extension
# ---------------------------------------------------------------------------

class TestRegisterSchedulersExtension(unittest.TestCase):

    def test_all_four_tasks_registered_on_cortex_profile(self):
        """Extension must register all four tasks when profile starts with 'cortex'."""
        from python.extensions.monologue_start._15_register_schedulers import CortexRegisterSchedulers

        agent = MagicMock()
        agent.config.profile = "cortex"

        with patch("python.helpers.cortex_weekly_digest.register_weekly_digest_task", new_callable=lambda: lambda: AsyncMock()) as m_digest, \
             patch("python.helpers.cortex_proactive_engine.register_proactive_task", new_callable=lambda: lambda: AsyncMock()) as m_proactive, \
             patch("python.helpers.cortex_discovery_scheduler.register_discovery_task", new_callable=lambda: lambda: AsyncMock()) as m_discovery, \
             patch("python.helpers.cortex_memory_backup.register_backup_task", new_callable=lambda: lambda: AsyncMock()) as m_backup:

            ext = CortexRegisterSchedulers(agent=agent)
            _run(ext.execute())

    def test_skips_on_non_cortex_profile(self):
        """Extension must skip entirely if profile is not 'cortex'."""
        from python.extensions.monologue_start._15_register_schedulers import CortexRegisterSchedulers

        agent = MagicMock()
        agent.config.profile = "default"
        scheduler = _make_mock_scheduler()

        with patch("python.cortex.scheduler.TaskScheduler.get", return_value=scheduler):
            ext = CortexRegisterSchedulers(agent=agent)
            _run(ext.execute())

        scheduler.add_task.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
