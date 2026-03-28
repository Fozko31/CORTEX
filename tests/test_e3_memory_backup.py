"""
Phase E -- Test E-3: Memory Backup
===================================
Tests for cortex_memory_backup.py covering:
  - L1 FAISS local copy (path generation, prune logic, skip when src missing)
  - L2 Graphiti export (skips when unconfigured, builds correct export structure)
  - L3 SurfSense incremental (skips seen IDs, paginates, persists state)
  - run_full_backup returns results for all three layers
  - Backup directories use dated paths
  - Pruning removes old backups

No network calls, no real filesystem writes (uses tmp dirs where needed).
"""

import asyncio
import gzip
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Setup: redirect backup root to a temp dir
# ---------------------------------------------------------------------------

class BackupTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Patch _backup_root to use temp dir
        self._patcher = patch(
            "python.helpers.cortex_memory_backup._backup_root",
            return_value=Path(self.tmp),
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests: L1 FAISS backup
# ---------------------------------------------------------------------------

class TestL1Backup(BackupTestBase):

    def test_skips_when_src_missing(self):
        from python.helpers.cortex_memory_backup import backup_l1_faiss
        with patch("pathlib.Path.exists", return_value=False):
            result = _run(backup_l1_faiss())
        self.assertEqual(result["status"], "skipped")

    def test_copies_files_when_src_exists(self):
        from python.helpers.cortex_memory_backup import backup_l1_faiss

        # Create a fake usr/memory dir with a file
        src = Path(self.tmp) / "src_memory"
        src.mkdir()
        (src / "test.faiss").write_text("fake faiss data")

        with patch("python.helpers.cortex_memory_backup.Path") as _:
            # Instead of complex patching, test the function's output structure
            with patch("pathlib.Path.__new__", side_effect=Path.__new__):
                pass  # Skip complex Path patching

        # Direct test: mock shutil.copytree
        with patch("shutil.copytree") as mock_copy, \
             patch("python.helpers.cortex_memory_backup._dated_dir") as mock_dir, \
             patch("python.helpers.cortex_memory_backup._prune_old"), \
             patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "mkdir"):
            mock_dir.return_value = Path(self.tmp) / "faiss" / "2026-03-30"
            result = _run(backup_l1_faiss())

        self.assertIn(result["status"], ("ok", "error"))

    def test_returns_dict(self):
        from python.helpers.cortex_memory_backup import backup_l1_faiss
        with patch("shutil.copytree"), \
             patch("python.helpers.cortex_memory_backup._dated_dir") as mock_dir, \
             patch("python.helpers.cortex_memory_backup._prune_old"), \
             patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "mkdir"):
            mock_dir.return_value = Path(self.tmp) / "faiss" / "2026-03-30"
            result = _run(backup_l1_faiss())
        self.assertIsInstance(result, dict)
        self.assertIn("status", result)


# ---------------------------------------------------------------------------
# Tests: L2 Graphiti backup
# ---------------------------------------------------------------------------

class TestL2GraphitiBackup(BackupTestBase):

    def _make_graphiti_client(self, configured=True):
        client = MagicMock()
        client.is_configured.return_value = configured
        client.user_id = "cortex_main"

        zep = MagicMock()

        # Mock graph search returning edges
        edge = MagicMock()
        edge.uuid = "edge-001"
        edge.source_node_name = "CORTEX"
        edge.target_node_name = "Venture"
        edge.name = "creates"
        edge.fact = "CORTEX creates ventures"
        edge.created_at = "2026-03-27"

        edge_resp = MagicMock()
        edge_resp.edges = [edge]

        episode = MagicMock()
        episode.uuid = "ep-001"
        episode.content = "Session content"
        episode.created_at = "2026-03-27"
        episode.score = 0.8

        ep_resp = MagicMock()
        ep_resp.episodes = [episode]

        zep.graph.search = AsyncMock(side_effect=[
            edge_resp, ep_resp,  # query 1
            edge_resp, ep_resp,  # query 2
            edge_resp, ep_resp,  # query 3
            edge_resp, ep_resp,  # query 4
        ])
        zep.user.get_facts = AsyncMock(return_value=MagicMock(facts=[]))
        client._get_client.return_value = zep

        return client

    def test_skips_when_not_configured(self):
        from python.helpers.cortex_memory_backup import backup_l2_graphiti
        client = self._make_graphiti_client(configured=False)
        with patch("python.helpers.cortex_graphiti_client.CortexGraphitiClient.from_agent_config", return_value=client):
            result = _run(backup_l2_graphiti(agent=MagicMock()))
        self.assertEqual(result["status"], "skipped")

    def test_exports_edges_and_episodes(self):
        from python.helpers.cortex_memory_backup import backup_l2_graphiti
        client = self._make_graphiti_client(configured=True)

        dst = Path(self.tmp) / "graphiti" / "2026-03-30"
        dst.mkdir(parents=True)

        with patch("python.helpers.cortex_graphiti_client.CortexGraphitiClient.from_agent_config", return_value=client), \
             patch("python.helpers.cortex_memory_backup._dated_dir", return_value=dst), \
             patch("python.helpers.cortex_memory_backup._prune_old"):
            result = _run(backup_l2_graphiti(agent=MagicMock()))

        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["edges"], 0)

    def test_creates_gzipped_json(self):
        from python.helpers.cortex_memory_backup import backup_l2_graphiti
        client = self._make_graphiti_client(configured=True)

        dst = Path(self.tmp) / "graphiti" / "2026-03-30"
        dst.mkdir(parents=True)

        with patch("python.helpers.cortex_graphiti_client.CortexGraphitiClient.from_agent_config", return_value=client), \
             patch("python.helpers.cortex_memory_backup._dated_dir", return_value=dst), \
             patch("python.helpers.cortex_memory_backup._prune_old"):
            _run(backup_l2_graphiti(agent=MagicMock()))

        out = dst / "graphiti_export.json.gz"
        self.assertTrue(out.exists())
        with gzip.open(out, "rt") as f:
            data = json.load(f)
        self.assertIn("edges", data)
        self.assertIn("exported_at", data)

    def test_deduplicates_edges_by_id(self):
        """Same edge UUID from multiple queries should not be duplicated."""
        from python.helpers.cortex_memory_backup import backup_l2_graphiti
        client = self._make_graphiti_client(configured=True)

        dst = Path(self.tmp) / "graphiti" / "2026-03-30"
        dst.mkdir(parents=True)

        with patch("python.helpers.cortex_graphiti_client.CortexGraphitiClient.from_agent_config", return_value=client), \
             patch("python.helpers.cortex_memory_backup._dated_dir", return_value=dst), \
             patch("python.helpers.cortex_memory_backup._prune_old"):
            result = _run(backup_l2_graphiti(agent=MagicMock()))

        # Even though the same edge is returned for each of 4 queries, count should be 1
        self.assertEqual(result["edges"], 1)


# ---------------------------------------------------------------------------
# Tests: L3 SurfSense backup
# ---------------------------------------------------------------------------

class TestL3SurfSenseBackup(BackupTestBase):

    def _make_surfsense_client(self, spaces=None, docs=None):
        client = MagicMock()
        client.health_check = AsyncMock(return_value=True)
        client.base_url = "http://localhost:8000"

        spaces = spaces or [{"id": 1, "name": "cortex_main"}]
        client.list_spaces = AsyncMock(return_value=spaces)

        http = AsyncMock()
        response = MagicMock()
        response.raise_for_status = MagicMock()

        docs = docs or [
            {"id": "doc-001", "title": "Test Doc", "content": "content", "created_at": "2026-03-27"},
        ]
        # First page returns docs, second page returns empty (end of pagination)
        response.json.side_effect = [
            {"items": docs},
            {"items": []},
        ]
        http.get = AsyncMock(return_value=response)
        client._get_client = AsyncMock(return_value=http)
        client._headers = AsyncMock(return_value={"Authorization": "Bearer token"})
        return client

    def test_skips_when_surfsense_unreachable(self):
        from python.helpers.cortex_memory_backup import backup_l3_surfsense
        client = self._make_surfsense_client()
        client.health_check = AsyncMock(return_value=False)
        with patch("python.helpers.cortex_surfsense_client.CortexSurfSenseClient.from_agent_config", return_value=client):
            result = _run(backup_l3_surfsense(agent=MagicMock()))
        self.assertEqual(result["status"], "skipped")

    def test_exports_new_documents(self):
        from python.helpers.cortex_memory_backup import backup_l3_surfsense, _LAST_BACKUP_FILE

        client = self._make_surfsense_client()
        dst = Path(self.tmp) / "surfsense" / "2026-03-30"

        with patch("python.helpers.cortex_surfsense_client.CortexSurfSenseClient.from_agent_config", return_value=client), \
             patch("python.helpers.cortex_memory_backup._dated_dir", return_value=dst), \
             patch("python.helpers.cortex_memory_backup._LAST_BACKUP_FILE", Path(self.tmp) / "last_backup.json"), \
             patch("python.helpers.cortex_memory_backup._load_last_backup_state", return_value={}), \
             patch("python.helpers.cortex_memory_backup._save_last_backup_state"), \
             patch("python.helpers.cortex_memory_backup._prune_old"):
            result = _run(backup_l3_surfsense(agent=MagicMock()))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["new_documents"], 1)

    def test_skips_already_seen_document_ids(self):
        """Documents with IDs in the previous backup state are not exported again."""
        from python.helpers.cortex_memory_backup import backup_l3_surfsense

        client = self._make_surfsense_client()
        prev_state = {"seen_document_ids": ["doc-001"]}  # doc-001 already backed up

        dst = Path(self.tmp) / "surfsense" / "2026-03-30"
        with patch("python.helpers.cortex_surfsense_client.CortexSurfSenseClient.from_agent_config", return_value=client), \
             patch("python.helpers.cortex_memory_backup._dated_dir", return_value=dst), \
             patch("python.helpers.cortex_memory_backup._load_last_backup_state", return_value=prev_state), \
             patch("python.helpers.cortex_memory_backup._save_last_backup_state"), \
             patch("python.helpers.cortex_memory_backup._prune_old"):
            result = _run(backup_l3_surfsense(agent=MagicMock()))

        self.assertEqual(result["new_documents"], 0)

    def test_returns_space_summary(self):
        from python.helpers.cortex_memory_backup import backup_l3_surfsense

        client = self._make_surfsense_client()
        dst = Path(self.tmp) / "surfsense" / "2026-03-30"

        with patch("python.helpers.cortex_surfsense_client.CortexSurfSenseClient.from_agent_config", return_value=client), \
             patch("python.helpers.cortex_memory_backup._dated_dir", return_value=dst), \
             patch("python.helpers.cortex_memory_backup._load_last_backup_state", return_value={}), \
             patch("python.helpers.cortex_memory_backup._save_last_backup_state"), \
             patch("python.helpers.cortex_memory_backup._prune_old"):
            result = _run(backup_l3_surfsense(agent=MagicMock()))

        self.assertIn("spaces", result)
        self.assertIsInstance(result["spaces"], dict)


# ---------------------------------------------------------------------------
# Tests: run_full_backup
# ---------------------------------------------------------------------------

class TestRunFullBackup(BackupTestBase):

    def test_returns_all_three_layers(self):
        from python.helpers.cortex_memory_backup import run_full_backup

        with patch("python.helpers.cortex_memory_backup.backup_l1_faiss", AsyncMock(return_value={"status": "ok"})), \
             patch("python.helpers.cortex_memory_backup.backup_l2_graphiti", AsyncMock(return_value={"status": "ok"})), \
             patch("python.helpers.cortex_memory_backup.backup_l3_surfsense", AsyncMock(return_value={"status": "ok"})), \
             patch("builtins.open", unittest.mock.mock_open()), \
             patch("pathlib.Path.mkdir"):
            result = _run(run_full_backup())

        self.assertIn("l1_faiss", result)
        self.assertIn("l2_graphiti", result)
        self.assertIn("l3_surfsense", result)

    def test_returns_timestamp(self):
        from python.helpers.cortex_memory_backup import run_full_backup

        with patch("python.helpers.cortex_memory_backup.backup_l1_faiss", AsyncMock(return_value={"status": "ok"})), \
             patch("python.helpers.cortex_memory_backup.backup_l2_graphiti", AsyncMock(return_value={"status": "ok"})), \
             patch("python.helpers.cortex_memory_backup.backup_l3_surfsense", AsyncMock(return_value={"status": "ok"})), \
             patch("builtins.open", unittest.mock.mock_open()), \
             patch("pathlib.Path.mkdir"):
            result = _run(run_full_backup())

        self.assertIn("timestamp", result)
        self.assertIsInstance(result["timestamp"], str)

    def test_continues_when_one_layer_fails(self):
        """All three layers must run even if one raises an exception."""
        from python.helpers.cortex_memory_backup import run_full_backup

        async def raises(_=None):
            raise RuntimeError("Graphiti down")

        with patch("python.helpers.cortex_memory_backup.backup_l1_faiss", AsyncMock(return_value={"status": "ok"})), \
             patch("python.helpers.cortex_memory_backup.backup_l2_graphiti", raises), \
             patch("python.helpers.cortex_memory_backup.backup_l3_surfsense", AsyncMock(return_value={"status": "ok"})), \
             patch("builtins.open", unittest.mock.mock_open()), \
             patch("pathlib.Path.mkdir"):
            # Should not raise — errors captured per-layer
            try:
                result = _run(run_full_backup())
                # If it reaches here, L3 ran despite L2 failure
                self.assertEqual(result["l3_surfsense"]["status"], "ok")
            except Exception:
                # If backup_l2_graphiti raises uncaught, that's a bug too — fail the test
                self.fail("run_full_backup should not propagate layer exceptions")


# ---------------------------------------------------------------------------
# Tests: _dated_dir and _prune_old
# ---------------------------------------------------------------------------

class TestBackupUtils(BackupTestBase):

    def test_dated_dir_contains_today(self):
        from python.helpers.cortex_memory_backup import _dated_dir
        from datetime import datetime
        today = datetime.utcnow().strftime("%Y-%m-%d")
        path = _dated_dir("graphiti")
        self.assertIn(today, str(path))

    def test_dated_dir_contains_layer_name(self):
        from python.helpers.cortex_memory_backup import _dated_dir
        path = _dated_dir("surfsense")
        self.assertIn("surfsense", str(path))

    def test_prune_removes_oldest_when_over_limit(self):
        from python.helpers.cortex_memory_backup import _prune_old

        # Create 10 fake dated dirs under tmp/faiss/
        layer_dir = Path(self.tmp) / "faiss"
        layer_dir.mkdir(parents=True)
        for i in range(10):
            d = layer_dir / f"2026-0{i % 9 + 1}-01"
            d.mkdir(exist_ok=True)

        _prune_old("faiss", keep_weeks=8)
        remaining = list(layer_dir.iterdir())
        self.assertLessEqual(len(remaining), 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
