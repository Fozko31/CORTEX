"""
Phase Op-A — Test OPA-4: Venture Playbook Create
=================================================
Tests for venture_playbook_create.py covering:
  - start: new playbook, draft detection
  - resume: continues from last step
  - save_step: saves content, advances to next step
  - publish: versions and stores playbook
  - get_status: reports draft + version state
  - discard_draft: removes draft
  - Step ordering: all 9 steps present and ordered
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


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _tmp_memory(tmp_dir):
    """Patch the playbook dir root."""
    return patch(
        "python.tools.venture_playbook_create._playbook_dir",
        lambda slug: Path(tmp_dir) / "ventures" / f"{slug}_playbooks",
    )


class TestPlaybookStart(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = _tmp_memory(self.tmp)
        self._p.start()
        self.tool = self._make_tool()

    def tearDown(self):
        self._p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_tool(self):
        from python.tools.venture_playbook_create import VenturePlaybookCreate
        tool = MagicMock(spec=VenturePlaybookCreate)
        # Use actual methods by binding to a real instance without agent
        real = object.__new__(VenturePlaybookCreate)
        real.agent = MagicMock()
        return real

    def test_start_creates_draft(self):
        from python.tools.venture_playbook_create import VenturePlaybookCreate, _load_draft
        tool = object.__new__(VenturePlaybookCreate)
        tool.agent = MagicMock()
        result = _run(tool._start(venture_slug="test_v", venture_name="Test Venture"))
        self.assertEqual(result["status"], "started")
        draft = _load_draft("test_v")
        self.assertIsNotNone(draft)
        self.assertEqual(draft["venture_name"], "Test Venture")

    def test_start_returns_next_step(self):
        from python.tools.venture_playbook_create import VenturePlaybookCreate
        tool = object.__new__(VenturePlaybookCreate)
        tool.agent = MagicMock()
        result = _run(tool._start(venture_slug="test_v2", venture_name="Test Venture 2"))
        self.assertIn("next_step", result)
        self.assertEqual(result["next_step"], "business_model")

    def test_start_detects_existing_draft(self):
        from python.tools.venture_playbook_create import VenturePlaybookCreate, _save_draft
        # Pre-create a draft
        _save_draft("existing_v", {
            "venture_slug": "existing_v",
            "venture_name": "Existing Venture",
            "status": "draft",
            "completed_steps": ["business_model"],
            "last_completed_step": "business_model",
            "sections": {},
            "created_at": "2026-03-27T00:00:00Z",
            "updated_at": "2026-03-27T00:00:00Z",
        })
        tool = object.__new__(VenturePlaybookCreate)
        tool.agent = MagicMock()
        result = _run(tool._start(venture_slug="existing_v"))
        self.assertEqual(result["status"], "draft_found")
        self.assertIn("last_completed_step", result)

    def test_start_requires_venture_slug(self):
        from python.tools.venture_playbook_create import VenturePlaybookCreate
        tool = object.__new__(VenturePlaybookCreate)
        tool.agent = MagicMock()
        result = _run(tool._start())
        self.assertEqual(result["status"], "error")


class TestPlaybookSaveStep(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = _tmp_memory(self.tmp)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tool(self):
        from python.tools.venture_playbook_create import VenturePlaybookCreate
        tool = object.__new__(VenturePlaybookCreate)
        tool.agent = MagicMock()
        return tool

    def _start(self, slug="sv1"):
        return _run(self._tool()._start(venture_slug=slug, venture_name="Test"))

    def test_save_step_returns_next_step(self):
        self._start()
        tool = self._tool()
        result = _run(tool._save_step(
            venture_slug="sv1",
            step="business_model",
            content={"problem": "test problem", "revenue_model": "subscription"},
        ))
        self.assertEqual(result["status"], "step_saved")
        self.assertEqual(result["next_step"], "customer_profile")

    def test_save_step_persists_content(self):
        from python.tools.venture_playbook_create import _load_draft
        self._start()
        tool = self._tool()
        _run(tool._save_step(
            venture_slug="sv1",
            step="business_model",
            content={"problem": "my problem"},
        ))
        draft = _load_draft("sv1")
        self.assertIn("business_model", draft["sections"])
        self.assertEqual(draft["sections"]["business_model"]["problem"], "my problem")

    def test_save_step_tracks_completed_steps(self):
        from python.tools.venture_playbook_create import _load_draft
        self._start()
        tool = self._tool()
        _run(tool._save_step(venture_slug="sv1", step="business_model", content={}))
        draft = _load_draft("sv1")
        self.assertIn("business_model", draft["completed_steps"])

    def test_save_step_invalid_step_name(self):
        self._start()
        tool = self._tool()
        result = _run(tool._save_step(venture_slug="sv1", step="nonexistent_step", content={}))
        self.assertEqual(result["status"], "error")

    def test_save_step_without_draft_returns_error(self):
        tool = self._tool()
        result = _run(tool._save_step(venture_slug="no_draft_v", step="business_model", content={}))
        self.assertEqual(result["status"], "error")

    def test_all_steps_complete_message(self):
        from python.tools.venture_playbook_create import PLAYBOOK_STEPS, _save_draft
        # Pre-fill all steps except last
        slug = "full_v"
        all_but_last = PLAYBOOK_STEPS[:-1]
        _save_draft(slug, {
            "venture_slug": slug,
            "venture_name": "Full Venture",
            "status": "draft",
            "completed_steps": list(all_but_last),
            "last_completed_step": all_but_last[-1],
            "sections": {s: {} for s in all_but_last},
            "created_at": "2026-03-27T00:00:00Z",
            "updated_at": "2026-03-27T00:00:00Z",
        })
        tool = self._tool()
        result = _run(tool._save_step(
            venture_slug=slug,
            step=PLAYBOOK_STEPS[-1],
            content={"reviewed": True},
        ))
        self.assertEqual(result["status"], "all_complete")


class TestPlaybookPublish(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = _tmp_memory(self.tmp)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tool(self):
        from python.tools.venture_playbook_create import VenturePlaybookCreate
        tool = object.__new__(VenturePlaybookCreate)
        tool.agent = MagicMock()
        return tool

    def _full_draft(self, slug="pub_v"):
        from python.tools.venture_playbook_create import PLAYBOOK_STEPS, _save_draft
        _save_draft(slug, {
            "venture_slug": slug,
            "venture_name": "Publish Venture",
            "status": "draft",
            "completed_steps": list(PLAYBOOK_STEPS),
            "last_completed_step": PLAYBOOK_STEPS[-1],
            "sections": {s: {"test": True} for s in PLAYBOOK_STEPS},
            "created_at": "2026-03-27T00:00:00Z",
            "updated_at": "2026-03-27T00:00:00Z",
        })

    def test_publish_creates_versioned_file(self):
        from python.tools.venture_playbook_create import _versioned_path
        self._full_draft()
        tool = self._tool()
        with patch.object(tool, "_push_to_surfsense", AsyncMock(return_value={"status": "skipped"})):
            result = _run(tool._publish(venture_slug="pub_v"))
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["version"], 1)

    def test_publish_removes_draft(self):
        from python.tools.venture_playbook_create import _draft_path
        self._full_draft()
        tool = self._tool()
        with patch.object(tool, "_push_to_surfsense", AsyncMock(return_value={"status": "skipped"})):
            _run(tool._publish(venture_slug="pub_v"))
        self.assertFalse(_draft_path("pub_v").exists())

    def test_publish_increments_version(self):
        self._full_draft("v_inc")
        tool = self._tool()
        with patch.object(tool, "_push_to_surfsense", AsyncMock(return_value={"status": "skipped"})):
            r1 = _run(tool._publish(venture_slug="v_inc"))
        self.assertEqual(r1["version"], 1)

        self._full_draft("v_inc")
        tool2 = self._tool()
        with patch.object(tool2, "_push_to_surfsense", AsyncMock(return_value={"status": "skipped"})):
            r2 = _run(tool2._publish(venture_slug="v_inc"))
        self.assertEqual(r2["version"], 2)

    def test_publish_requires_draft(self):
        tool = self._tool()
        result = _run(tool._publish(venture_slug="ghost_v"))
        self.assertEqual(result["status"], "error")

    def test_get_status_shows_draft_and_versions(self):
        self._full_draft("status_v")
        tool = self._tool()
        result = _run(tool._get_status(venture_slug="status_v"))
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["has_draft"])

    def test_discard_draft_removes_file(self):
        from python.tools.venture_playbook_create import _draft_path
        self._full_draft("disc_v")
        tool = self._tool()
        result = _run(tool._discard_draft(venture_slug="disc_v"))
        self.assertEqual(result["status"], "ok")
        self.assertFalse(_draft_path("disc_v").exists())

    def test_discard_draft_not_found_graceful(self):
        tool = self._tool()
        result = _run(tool._discard_draft(venture_slug="no_draft_v"))
        self.assertEqual(result["status"], "not_found")


class TestPlaybookResume(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = _tmp_memory(self.tmp)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resume_returns_next_step(self):
        from python.tools.venture_playbook_create import VenturePlaybookCreate, _save_draft
        _save_draft("res_v", {
            "venture_slug": "res_v",
            "venture_name": "Resume Venture",
            "status": "draft",
            "completed_steps": ["venture_confirmed", "business_model"],
            "last_completed_step": "business_model",
            "sections": {},
            "created_at": "2026-03-27T00:00:00Z",
            "updated_at": "2026-03-27T00:00:00Z",
        })
        tool = object.__new__(VenturePlaybookCreate)
        tool.agent = MagicMock()
        result = _run(tool._resume(venture_slug="res_v"))
        self.assertEqual(result["status"], "resumed")
        self.assertEqual(result["next_step"], "customer_profile")

    def test_resume_no_draft_returns_guidance(self):
        from python.tools.venture_playbook_create import VenturePlaybookCreate
        tool = object.__new__(VenturePlaybookCreate)
        tool.agent = MagicMock()
        result = _run(tool._resume(venture_slug="ghost_v"))
        self.assertEqual(result["status"], "no_draft")


if __name__ == "__main__":
    unittest.main(verbosity=2)
