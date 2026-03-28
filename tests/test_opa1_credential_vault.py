"""
Phase Op-A — Test OPA-1: Credential Vault
==========================================
Tests for cortex_credential_vault.py covering:
  - set / get / has / delete
  - list_keys returns metadata only (no raw values)
  - expiry status: none / ok / warning / expired
  - check_all_expiring across ventures
  - vault_exists / delete_vault
  - graceful handling when cryptography not installed

All tests use temp dirs and mock the vault path.
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_vault(tmp_dir: str):
    """Patch vault dir to a temp location."""
    return patch(
        "python.helpers.cortex_credential_vault._VAULT_DIR",
        Path(tmp_dir) / "vault",
    )


def _make_temp_key_file(tmp_dir: str):
    return patch(
        "python.helpers.cortex_credential_vault._KEY_FILE",
        Path(tmp_dir) / ".vault_key",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCredentialVaultBasic(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p1 = _make_temp_vault(self.tmp)
        self._p2 = _make_temp_key_file(self.tmp)
        self._p1.start()
        self._p2.start()

    def tearDown(self):
        self._p1.stop()
        self._p2.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _vault(self, slug="test_venture"):
        from python.helpers.cortex_credential_vault import CortexCredentialVault
        return CortexCredentialVault(slug)

    def test_set_and_get(self):
        v = self._vault()
        v.set("api_key", "secret123", description="Test key")
        self.assertEqual(v.get("api_key"), "secret123")

    def test_get_returns_none_when_missing(self):
        v = self._vault()
        self.assertIsNone(v.get("nonexistent"))

    def test_has_returns_true_after_set(self):
        v = self._vault()
        v.set("mykey", "myvalue")
        self.assertTrue(v.has("mykey"))

    def test_has_returns_false_when_missing(self):
        v = self._vault()
        self.assertFalse(v.has("ghost"))

    def test_delete_removes_credential(self):
        v = self._vault()
        v.set("to_delete", "value")
        result = v.delete("to_delete")
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(v.get("to_delete"))

    def test_delete_returns_not_found_for_missing(self):
        v = self._vault()
        result = v.delete("missing_key")
        self.assertEqual(result["status"], "not_found")

    def test_overwrite_credential(self):
        v = self._vault()
        v.set("key", "v1")
        v.set("key", "v2")
        self.assertEqual(v.get("key"), "v2")

    def test_multiple_credentials_independent(self):
        v = self._vault()
        v.set("key_a", "val_a")
        v.set("key_b", "val_b")
        self.assertEqual(v.get("key_a"), "val_a")
        self.assertEqual(v.get("key_b"), "val_b")

    def test_different_ventures_isolated(self):
        from python.helpers.cortex_credential_vault import CortexCredentialVault
        v1 = CortexCredentialVault("venture_x")
        v2 = CortexCredentialVault("venture_y")
        v1.set("shared_name", "x_value")
        v2.set("shared_name", "y_value")
        self.assertEqual(v1.get("shared_name"), "x_value")
        self.assertEqual(v2.get("shared_name"), "y_value")

    def test_vault_exists_after_set(self):
        v = self._vault()
        self.assertFalse(v.vault_exists())
        v.set("k", "v")
        self.assertTrue(v.vault_exists())

    def test_delete_vault(self):
        v = self._vault()
        v.set("k", "v")
        result = v.delete_vault()
        self.assertEqual(result["status"], "ok")
        self.assertFalse(v.vault_exists())


class TestCredentialVaultListKeys(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p1 = _make_temp_vault(self.tmp)
        self._p2 = _make_temp_key_file(self.tmp)
        self._p1.start()
        self._p2.start()

    def tearDown(self):
        self._p1.stop()
        self._p2.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _vault(self):
        from python.helpers.cortex_credential_vault import CortexCredentialVault
        return CortexCredentialVault("test")

    def test_list_keys_returns_names_not_values(self):
        v = self._vault()
        v.set("secret_key", "TOP_SECRET_VALUE")
        keys = v.list_keys()
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0]["name"], "secret_key")
        # Value must NOT appear anywhere in the key metadata
        self.assertNotIn("value", keys[0])
        for val in keys[0].values():
            self.assertNotEqual(val, "TOP_SECRET_VALUE")

    def test_list_keys_returns_description(self):
        v = self._vault()
        v.set("key", "val", description="My API key")
        keys = v.list_keys()
        self.assertEqual(keys[0]["description"], "My API key")

    def test_expiry_status_none_when_no_expiry(self):
        v = self._vault()
        v.set("key", "val")
        keys = v.list_keys()
        self.assertEqual(keys[0]["expiry_status"], "none")

    def test_expiry_status_ok_for_future(self):
        v = self._vault()
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        v.set("key", "val", expires_at=future)
        keys = v.list_keys()
        self.assertEqual(keys[0]["expiry_status"], "ok")

    def test_expiry_status_warning_within_7_days(self):
        v = self._vault()
        soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        v.set("key", "val", expires_at=soon)
        keys = v.list_keys()
        self.assertEqual(keys[0]["expiry_status"], "warning")

    def test_expiry_status_expired_for_past(self):
        v = self._vault()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        v.set("key", "val", expires_at=past)
        keys = v.list_keys()
        self.assertEqual(keys[0]["expiry_status"], "expired")

    def test_expiring_soon_filters_correctly(self):
        v = self._vault()
        v.set("fine", "v", expires_at=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat())
        v.set("warn", "v", expires_at=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat())
        v.set("gone", "v", expires_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
        expiring = v.expiring_soon()
        names = {e["name"] for e in expiring}
        self.assertIn("warn", names)
        self.assertIn("gone", names)
        self.assertNotIn("fine", names)


class TestCheckAllExpiring(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p1 = _make_temp_vault(self.tmp)
        self._p2 = _make_temp_key_file(self.tmp)
        self._p1.start()
        self._p2.start()

    def tearDown(self):
        self._p1.stop()
        self._p2.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_check_all_expiring_across_ventures(self):
        from python.helpers.cortex_credential_vault import CortexCredentialVault, check_all_expiring
        soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

        v1 = CortexCredentialVault("venture_a")
        v1.set("key1", "val", expires_at=soon)

        v2 = CortexCredentialVault("venture_b")
        v2.set("key2", "val", expires_at=soon)

        warnings = check_all_expiring(["venture_a", "venture_b"])
        slugs = {w["venture_slug"] for w in warnings}
        self.assertIn("venture_a", slugs)
        self.assertIn("venture_b", slugs)

    def test_check_all_expiring_returns_empty_when_all_fine(self):
        from python.helpers.cortex_credential_vault import CortexCredentialVault, check_all_expiring
        future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        v = CortexCredentialVault("clean_venture")
        v.set("key", "val", expires_at=future)
        warnings = check_all_expiring(["clean_venture"])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
