"""
Phase Op-A — Test OPA-3: Task Queue + Action Log
=================================================
Tests for cortex_venture_task_queue.py and cortex_venture_action_log.py covering:
  - Task CRUD: add, get, list, update, enable, disable, delete
  - Action log: log_action, update_status, approve, reject, mark_executed
  - HITL: pending_count, list_pending
  - Shared DB: both tables coexist in venture_ops.db
  - Schema idempotency: init runs multiple times safely
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _tmp_db(tmp_dir):
    return patch(
        "python.helpers.cortex_venture_task_queue._DB_PATH",
        Path(tmp_dir) / "venture_ops.db",
    )


# ---------------------------------------------------------------------------
# Task Queue Tests
# ---------------------------------------------------------------------------

class TestVentureTaskQueue(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = _tmp_db(self.tmp)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _queue(self):
        from python.helpers.cortex_venture_task_queue import VentureTaskQueue
        return VentureTaskQueue()

    def _sample_task(self, **overrides):
        defaults = dict(
            venture_slug="test_venture",
            task_type="email_handling",
            name="Test Email Task",
            cadence="0 9 * * 1-5",
            prompt="Check and triage emails for test_venture.",
        )
        defaults.update(overrides)
        return defaults

    def test_add_task_returns_task_id(self):
        q = self._queue()
        task = q.add_task(**self._sample_task())
        self.assertIn("task_id", task)
        self.assertIsNotNone(task["task_id"])

    def test_get_task_retrieves_by_id(self):
        q = self._queue()
        task = q.add_task(**self._sample_task())
        retrieved = q.get_task(task["task_id"])
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["name"], "Test Email Task")

    def test_get_task_returns_none_for_unknown(self):
        q = self._queue()
        self.assertIsNone(q.get_task("nonexistent-uuid"))

    def test_list_tasks_filters_by_venture(self):
        q = self._queue()
        q.add_task(**self._sample_task(venture_slug="v1", name="T1"))
        q.add_task(**self._sample_task(venture_slug="v2", name="T2"))
        tasks = q.list_tasks(venture_slug="v1")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "T1")

    def test_list_tasks_enabled_only(self):
        q = self._queue()
        t1 = q.add_task(**self._sample_task(name="Active"))
        t2 = q.add_task(**self._sample_task(name="Disabled"))
        q.disable_task(t2["task_id"])
        tasks = q.list_tasks(enabled_only=True)
        names = [t["name"] for t in tasks]
        self.assertIn("Active", names)
        self.assertNotIn("Disabled", names)

    def test_disable_task_sets_status(self):
        q = self._queue()
        task = q.add_task(**self._sample_task())
        q.disable_task(task["task_id"])
        retrieved = q.get_task(task["task_id"])
        self.assertEqual(retrieved["status"], "disabled")
        self.assertEqual(retrieved["enabled"], 0)

    def test_enable_task_after_disable(self):
        q = self._queue()
        task = q.add_task(**self._sample_task())
        q.disable_task(task["task_id"])
        q.enable_task(task["task_id"])
        retrieved = q.get_task(task["task_id"])
        self.assertEqual(retrieved["status"], "active")
        self.assertEqual(retrieved["enabled"], 1)

    def test_mark_last_run_updates_timestamp(self):
        q = self._queue()
        task = q.add_task(**self._sample_task())
        self.assertIsNone(q.get_task(task["task_id"])["last_run"])
        q.mark_last_run(task["task_id"])
        self.assertIsNotNone(q.get_task(task["task_id"])["last_run"])

    def test_mark_failed_sets_error(self):
        q = self._queue()
        task = q.add_task(**self._sample_task())
        q.mark_failed(task["task_id"], "Network timeout")
        retrieved = q.get_task(task["task_id"])
        self.assertEqual(retrieved["status"], "failed")
        self.assertEqual(retrieved["last_error"], "Network timeout")

    def test_delete_task_removes_it(self):
        q = self._queue()
        task = q.add_task(**self._sample_task())
        q.delete_task(task["task_id"])
        self.assertIsNone(q.get_task(task["task_id"]))

    def test_schema_idempotent(self):
        from python.helpers.cortex_venture_task_queue import init_task_queue_schema
        # Running twice should not raise
        init_task_queue_schema()
        init_task_queue_schema()


# ---------------------------------------------------------------------------
# Action Log Tests
# ---------------------------------------------------------------------------

class TestVentureActionLog(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = _tmp_db(self.tmp)
        self._p.start()
        # Also patch the import reference in action_log
        self._p2 = patch(
            "python.helpers.cortex_venture_action_log._DB_PATH",
            Path(self.tmp) / "venture_ops.db",
        )
        self._p2.start()

    def tearDown(self):
        self._p.stop()
        self._p2.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _log(self):
        from python.helpers.cortex_venture_action_log import VentureActionLog
        return VentureActionLog()

    def _log_action(self, log, **overrides):
        defaults = dict(
            venture_slug="test_venture",
            action_type="SEND_MESSAGE",
            tool_used="gmail_send",
            inputs={"to": "user@example.com", "subject": "Hello"},
            autonomy_decision="REQUIRE_APPROVAL",
            decision_reason="Policy: REQUIRE_APPROVAL for SEND_MESSAGE",
        )
        defaults.update(overrides)
        return log.log_action(**defaults)

    def test_log_action_returns_uuid(self):
        log = self._log()
        action_id = self._log_action(log)
        self.assertIsNotNone(action_id)
        self.assertIsInstance(action_id, str)

    def test_get_action_by_id(self):
        log = self._log()
        action_id = self._log_action(log)
        action = log.get_action(action_id)
        self.assertIsNotNone(action)
        self.assertEqual(action["tool_used"], "gmail_send")

    def test_get_action_returns_none_for_missing(self):
        log = self._log()
        self.assertIsNone(log.get_action("unknown-id"))

    def test_inputs_deserialized_to_dict(self):
        log = self._log()
        action_id = self._log_action(log, inputs={"key": "value"})
        action = log.get_action(action_id)
        self.assertIsInstance(action["inputs"], dict)
        self.assertEqual(action["inputs"]["key"], "value")

    def test_initial_status_pending_approval(self):
        log = self._log()
        action_id = self._log_action(log)
        action = log.get_action(action_id)
        self.assertEqual(action["status"], "pending_approval")

    def test_approve_changes_status(self):
        log = self._log()
        action_id = self._log_action(log)
        log.approve(action_id)
        action = log.get_action(action_id)
        self.assertEqual(action["status"], "approved")
        self.assertEqual(action["approved_by"], "user")

    def test_reject_changes_status(self):
        log = self._log()
        action_id = self._log_action(log)
        log.reject(action_id)
        action = log.get_action(action_id)
        self.assertEqual(action["status"], "rejected")

    def test_mark_executed_stores_outcome(self):
        log = self._log()
        action_id = self._log_action(log)
        log.mark_executed(action_id, {"message_id": "abc123"})
        action = log.get_action(action_id)
        self.assertEqual(action["status"], "executed")
        self.assertEqual(action["outcome"]["message_id"], "abc123")

    def test_mark_failed_stores_error(self):
        log = self._log()
        action_id = self._log_action(log)
        log.mark_failed(action_id, "SMTP connection refused")
        action = log.get_action(action_id)
        self.assertEqual(action["status"], "failed")
        self.assertEqual(action["error"], "SMTP connection refused")

    def test_pending_count_counts_only_pending(self):
        log = self._log()
        a1 = self._log_action(log)
        a2 = self._log_action(log)
        log.approve(a1)
        self.assertEqual(log.pending_count(), 1)

    def test_pending_count_per_venture(self):
        log = self._log()
        self._log_action(log, venture_slug="v1")
        self._log_action(log, venture_slug="v2")
        self.assertEqual(log.pending_count("v1"), 1)
        self.assertEqual(log.pending_count("v2"), 1)

    def test_list_pending_returns_pending_only(self):
        log = self._log()
        a1 = self._log_action(log)
        a2 = self._log_action(log)
        log.approve(a1)
        pending = log.list_pending()
        ids = [p["action_id"] for p in pending]
        self.assertNotIn(a1, ids)
        self.assertIn(a2, ids)

    def test_list_by_venture_filters_correctly(self):
        log = self._log()
        self._log_action(log, venture_slug="v_a")
        self._log_action(log, venture_slug="v_b")
        actions = log.list_by_venture("v_a")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["venture_slug"], "v_a")

    def test_resource_id_stored_and_retrieved(self):
        log = self._log()
        action_id = self._log_action(log, resource_id="gmail_primary")
        action = log.get_action(action_id)
        self.assertEqual(action["resource_id"], "gmail_primary")

    def test_cost_estimate_stored(self):
        log = self._log()
        action_id = self._log_action(log, cost_estimate=0.05)
        action = log.get_action(action_id)
        self.assertAlmostEqual(action["cost_estimate"], 0.05)

    def test_get_total_cost_sums_executed(self):
        log = self._log()
        a1 = self._log_action(log, cost_estimate=0.10)
        a2 = self._log_action(log, cost_estimate=0.20)
        log.mark_executed(a1, {})
        log.mark_executed(a2, {})
        total = log.get_total_cost("test_venture")
        self.assertAlmostEqual(total, 0.30)

    def test_action_log_schema_idempotent(self):
        from python.helpers.cortex_venture_action_log import init_action_log_schema
        init_action_log_schema()
        init_action_log_schema()

    def test_both_tables_coexist_in_shared_db(self):
        """Task queue and action log both work in the same DB file."""
        from python.helpers.cortex_venture_task_queue import VentureTaskQueue
        q = VentureTaskQueue()
        task = q.add_task(
            venture_slug="shared_db_test",
            task_type="test",
            name="Test Task",
            cadence="0 9 * * *",
            prompt="Test prompt",
        )
        log = self._log()
        action_id = self._log_action(log, venture_slug="shared_db_test")

        # Both should be retrievable
        self.assertIsNotNone(q.get_task(task["task_id"]))
        self.assertIsNotNone(log.get_action(action_id))


if __name__ == "__main__":
    unittest.main(verbosity=2)
