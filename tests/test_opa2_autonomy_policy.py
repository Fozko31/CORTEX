"""
Phase Op-A — Test OPA-2: Autonomy Policy
=========================================
Tests for cortex_autonomy_policy.py covering:
  - get_level: lookup hierarchy (resource > action_class > venture_default > global)
  - set_rule / delete_rule
  - set_venture_default / spend_threshold
  - should_auto_execute (incl. spend gate)
  - should_draft_first
  - get_venture_summary
  - list_rules filtering
  - make_autonomy_decision helper
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _tmp_policy(tmp_dir):
    return patch(
        "python.helpers.cortex_autonomy_policy._POLICY_FILE",
        Path(tmp_dir) / "autonomy_policy.json",
    )


class TestAutonomyPolicyLookup(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = _tmp_policy(self.tmp)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _policy(self):
        from python.helpers.cortex_autonomy_policy import CortexAutonomyPolicy
        return CortexAutonomyPolicy()

    def test_resource_specific_rule_wins(self):
        p = self._policy()
        p.set_rule("v1", "SEND_MESSAGE", "REQUIRE_APPROVAL")  # venture+action
        p.set_rule("v1", "SEND_MESSAGE", "AUTO", resource_id="gmail_bulk")  # resource-specific
        self.assertEqual(p.get_level("v1", "SEND_MESSAGE", resource_id="gmail_bulk"), "AUTO")

    def test_action_class_rule_beats_venture_default(self):
        p = self._policy()
        p.set_venture_default("v1", "REQUIRE_APPROVAL")
        p.set_rule("v1", "READ", "AUTO")
        self.assertEqual(p.get_level("v1", "READ"), "AUTO")

    def test_venture_default_beats_global(self):
        p = self._policy()
        p.set_venture_default("v1", "DRAFT_FIRST")
        # No action-class or resource rule
        level = p.get_level("v1", "SCHEDULE")
        self.assertEqual(level, "DRAFT_FIRST")

    def test_global_action_safe_default_for_send_message(self):
        p = self._policy()
        # No rules set at all
        level = p.get_level("new_venture", "SEND_MESSAGE")
        self.assertEqual(level, "REQUIRE_APPROVAL")

    def test_global_action_safe_default_for_read(self):
        p = self._policy()
        level = p.get_level("new_venture", "READ")
        self.assertEqual(level, "AUTO")

    def test_falls_back_to_action_class_default_when_no_resource_rule(self):
        p = self._policy()
        p.set_rule("v1", "SEND_MESSAGE", "AUTO", resource_id="gmail_bulk")
        # Different resource — should fall back to action class default
        level = p.get_level("v1", "SEND_MESSAGE", resource_id="gmail_personal")
        self.assertEqual(level, "REQUIRE_APPROVAL")  # built-in safe default

    def test_case_insensitive_action_class(self):
        p = self._policy()
        p.set_rule("v1", "SEND_MESSAGE", "AUTO")
        self.assertEqual(p.get_level("v1", "send_message"), "AUTO")
        self.assertEqual(p.get_level("v1", "Send_Message"), "AUTO")


class TestAutonomyPolicySetDelete(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = _tmp_policy(self.tmp)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _policy(self):
        from python.helpers.cortex_autonomy_policy import CortexAutonomyPolicy
        return CortexAutonomyPolicy()

    def test_set_rule_returns_ok(self):
        p = self._policy()
        result = p.set_rule("v1", "READ", "AUTO")
        self.assertEqual(result["status"], "ok")

    def test_set_rule_invalid_action_class(self):
        p = self._policy()
        result = p.set_rule("v1", "INVALID_CLASS", "AUTO")
        self.assertEqual(result["status"], "error")

    def test_set_rule_invalid_level(self):
        p = self._policy()
        result = p.set_rule("v1", "READ", "MAYBE")
        self.assertEqual(result["status"], "error")

    def test_overwrite_rule(self):
        p = self._policy()
        p.set_rule("v1", "READ", "AUTO")
        p.set_rule("v1", "READ", "REQUIRE_APPROVAL")
        self.assertEqual(p.get_level("v1", "READ"), "REQUIRE_APPROVAL")

    def test_delete_rule_falls_back_to_default(self):
        p = self._policy()
        p.set_rule("v1", "READ", "REQUIRE_APPROVAL")
        p.delete_rule("v1", "READ")
        # Should fall back to safe default for READ = AUTO
        self.assertEqual(p.get_level("v1", "READ"), "AUTO")

    def test_resource_rules_independent_of_venture_rule(self):
        p = self._policy()
        p.set_rule("v1", "SEND_MESSAGE", "AUTO", resource_id="r1")
        p.set_rule("v1", "SEND_MESSAGE", "REQUIRE_APPROVAL", resource_id="r2")
        self.assertEqual(p.get_level("v1", "SEND_MESSAGE", "r1"), "AUTO")
        self.assertEqual(p.get_level("v1", "SEND_MESSAGE", "r2"), "REQUIRE_APPROVAL")

    def test_list_rules_filtered_by_venture(self):
        p = self._policy()
        p.set_rule("v1", "READ", "AUTO")
        p.set_rule("v2", "READ", "REQUIRE_APPROVAL")
        rules = p.list_rules("v1")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["venture_slug"], "v1")

    def test_venture_default_spend_threshold(self):
        p = self._policy()
        p.set_venture_default("v1", "AUTO", spend_auto_threshold_eur=5.0)
        self.assertEqual(p.get_spend_threshold("v1"), 5.0)

    def test_get_venture_summary_includes_all_action_classes(self):
        from python.helpers.cortex_autonomy_policy import ACTION_CLASSES
        p = self._policy()
        summary = p.get_venture_summary("v1")
        for ac in ACTION_CLASSES:
            self.assertIn(ac, summary["action_classes"])


class TestAutoExecuteDecision(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = _tmp_policy(self.tmp)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _policy(self):
        from python.helpers.cortex_autonomy_policy import CortexAutonomyPolicy
        return CortexAutonomyPolicy()

    def test_auto_level_returns_true(self):
        p = self._policy()
        p.set_rule("v1", "READ", "AUTO")
        self.assertTrue(p.should_auto_execute("v1", "READ"))

    def test_require_approval_returns_false(self):
        p = self._policy()
        p.set_rule("v1", "SEND_MESSAGE", "REQUIRE_APPROVAL")
        self.assertFalse(p.should_auto_execute("v1", "SEND_MESSAGE"))

    def test_draft_first_returns_false_for_auto_execute(self):
        p = self._policy()
        p.set_rule("v1", "SEND_MESSAGE", "DRAFT_FIRST")
        self.assertFalse(p.should_auto_execute("v1", "SEND_MESSAGE"))

    def test_draft_first_returns_true_for_should_draft(self):
        p = self._policy()
        p.set_rule("v1", "SEND_MESSAGE", "DRAFT_FIRST")
        self.assertTrue(p.should_draft_first("v1", "SEND_MESSAGE"))

    def test_spend_gate_blocks_over_threshold(self):
        p = self._policy()
        p.set_rule("v1", "SPEND_MONEY", "AUTO")
        p.set_venture_default("v1", "AUTO", spend_auto_threshold_eur=10.0)
        # €5 is under threshold → allow
        self.assertTrue(p.should_auto_execute("v1", "SPEND_MONEY", cost_eur=5.0))
        # €15 is over threshold → block
        self.assertFalse(p.should_auto_execute("v1", "SPEND_MONEY", cost_eur=15.0))

    def test_spend_gate_blocks_any_amount_when_threshold_zero(self):
        p = self._policy()
        p.set_rule("v1", "SPEND_MONEY", "AUTO")
        # Default threshold is 0.0
        self.assertFalse(p.should_auto_execute("v1", "SPEND_MONEY", cost_eur=0.01))


class TestMakeAutonomyDecision(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = _tmp_policy(self.tmp)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _policy(self):
        from python.helpers.cortex_autonomy_policy import CortexAutonomyPolicy
        return CortexAutonomyPolicy()

    def test_returns_decision_and_reason(self):
        from python.helpers.cortex_autonomy_policy import make_autonomy_decision
        p = self._policy()
        p.set_rule("v1", "READ", "AUTO")
        d = make_autonomy_decision(p, "v1", "READ")
        self.assertIn("decision", d)
        self.assertIn("reason", d)
        self.assertEqual(d["decision"], "AUTO")

    def test_spend_override_in_decision(self):
        from python.helpers.cortex_autonomy_policy import make_autonomy_decision
        p = self._policy()
        p.set_rule("v1", "SPEND_MONEY", "AUTO")
        d = make_autonomy_decision(p, "v1", "SPEND_MONEY", cost_eur=999.0)
        self.assertEqual(d["decision"], "REQUIRE_APPROVAL")
        self.assertIn("threshold", d["reason"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
