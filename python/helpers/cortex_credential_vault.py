"""
CORTEX Credential Vault
=======================
Fernet symmetric encryption for per-venture credentials.
Stored at: usr/memory/cortex_main/vault/{slug}_credentials.enc

Design:
- One encrypted JSON blob per venture slug
- Key: CORTEX_VAULT_KEY env var (auto-generated and persisted on first use)
- Credentials keyed by name (e.g. "gmail_primary", "stripe_live")
- Optional expires_at with 7-day warning surfaced at next interaction
- list_keys() reveals names + expiry status, never raw values
- delete() removes a credential by name without re-encrypting others

Action classes this vault supports:
    venture_ops set_credential / list_credential_keys
"""

from __future__ import annotations

import json
import os
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Fernet import — graceful degradation if cryptography not installed
# ---------------------------------------------------------------------------
try:
    from cryptography.fernet import Fernet, InvalidToken
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

    class InvalidToken(Exception):  # type: ignore
        pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VAULT_DIR = Path("usr/memory/cortex_main/vault")
_KEY_FILE = Path("usr/.vault_key")
_EXPIRY_WARN_DAYS = 7


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def _get_or_create_key() -> bytes:
    """
    Returns the Fernet key bytes.
    Priority: CORTEX_VAULT_KEY env var → persisted key file → generate new.
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError(
            "cryptography package not installed. "
            "Run: pip install cryptography"
        )

    env_key = os.environ.get("CORTEX_VAULT_KEY")
    if env_key:
        return env_key.encode()

    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()

    # Generate and persist
    key = Fernet.generate_key()
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_bytes(key)
    # Restrict permissions where possible
    try:
        os.chmod(_KEY_FILE, 0o600)
    except Exception:
        pass
    return key


def _fernet() -> "Fernet":
    return Fernet(_get_or_create_key())


# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

def _vault_path(venture_slug: str) -> Path:
    return _VAULT_DIR / f"{venture_slug}_credentials.enc"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_vault(venture_slug: str) -> dict:
    """Decrypt and return the vault dict for a venture. Returns {} if none."""
    path = _vault_path(venture_slug)
    if not path.exists():
        return {}
    try:
        raw = path.read_bytes()
        decrypted = _fernet().decrypt(raw)
        return json.loads(decrypted.decode())
    except (InvalidToken, json.JSONDecodeError, Exception):
        return {}


def _save_vault(venture_slug: str, data: dict) -> None:
    """Encrypt and persist the vault dict for a venture."""
    _VAULT_DIR.mkdir(parents=True, exist_ok=True)
    path = _vault_path(venture_slug)
    encrypted = _fernet().encrypt(json.dumps(data).encode())
    path.write_bytes(encrypted)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class CortexCredentialVault:
    """
    Per-venture credential store with Fernet encryption.

    All values are encrypted at rest. list_keys() exposes names + expiry
    state only — never raw credential values.
    """

    def __init__(self, venture_slug: str):
        self.slug = venture_slug

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def set(
        self,
        name: str,
        value: str,
        description: str = "",
        expires_at: Optional[str] = None,
    ) -> dict:
        """
        Store (or overwrite) a credential.

        Args:
            name: Identifier for this credential (e.g. "gmail_primary")
            value: The secret value (API key, password, token)
            description: Human-readable note (stored, not secret)
            expires_at: ISO 8601 datetime string, optional

        Returns:
            {"status": "ok", "name": name, "expires_at": expires_at}
        """
        if not _CRYPTO_AVAILABLE:
            return {"status": "error", "error": "cryptography package not installed"}

        vault = _load_vault(self.slug)
        vault[name] = {
            "value": value,
            "description": description,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_vault(self.slug, vault)
        return {"status": "ok", "name": name, "expires_at": expires_at}

    def delete(self, name: str) -> dict:
        """Remove a credential by name."""
        vault = _load_vault(self.slug)
        if name not in vault:
            return {"status": "not_found", "name": name}
        del vault[name]
        _save_vault(self.slug, vault)
        return {"status": "ok", "name": name}

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[str]:
        """
        Return the raw credential value (for internal tool use only).
        Returns None if not found or decryption fails.
        """
        vault = _load_vault(self.slug)
        entry = vault.get(name)
        if entry is None:
            return None
        return entry.get("value")

    def list_keys(self) -> list[dict]:
        """
        Return credential metadata (name, description, expiry state) —
        never the raw values. Safe to surface in system prompts.

        Returns list of:
            {"name": str, "description": str, "expires_at": str|None,
             "expiry_status": "ok"|"warning"|"expired"|"none"}
        """
        vault = _load_vault(self.slug)
        result = []
        now = datetime.now(timezone.utc)

        for name, entry in vault.items():
            expires_raw = entry.get("expires_at")
            expiry_status = "none"

            if expires_raw:
                try:
                    expires_dt = datetime.fromisoformat(expires_raw)
                    if expires_dt.tzinfo is None:
                        expires_dt = expires_dt.replace(tzinfo=timezone.utc)

                    if expires_dt < now:
                        expiry_status = "expired"
                    elif expires_dt < now + timedelta(days=_EXPIRY_WARN_DAYS):
                        expiry_status = "warning"
                    else:
                        expiry_status = "ok"
                except ValueError:
                    expiry_status = "unknown"

            result.append({
                "name": name,
                "description": entry.get("description", ""),
                "expires_at": expires_raw,
                "expiry_status": expiry_status,
                "updated_at": entry.get("updated_at"),
            })

        return result

    def expiring_soon(self) -> list[dict]:
        """Return credentials with expiry_status == 'warning' or 'expired'."""
        return [
            c for c in self.list_keys()
            if c["expiry_status"] in ("warning", "expired")
        ]

    def has(self, name: str) -> bool:
        """Check if a credential exists (does not decrypt)."""
        path = _vault_path(self.slug)
        if not path.exists():
            return False
        vault = _load_vault(self.slug)
        return name in vault

    # ------------------------------------------------------------------
    # Vault-level
    # ------------------------------------------------------------------

    def vault_exists(self) -> bool:
        return _vault_path(self.slug).exists()

    def delete_vault(self) -> dict:
        """Delete the entire vault for this venture (irreversible)."""
        path = _vault_path(self.slug)
        if not path.exists():
            return {"status": "not_found"}
        path.unlink()
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def for_venture(cls, venture_slug: str) -> "CortexCredentialVault":
        return cls(venture_slug)

    @classmethod
    def from_agent_config(cls, agent, venture_slug: str) -> "CortexCredentialVault":
        """Construct from agent — venture_slug is always explicit."""
        return cls(venture_slug)


# ---------------------------------------------------------------------------
# Expiry check helper — for use by venture_ops health_check
# ---------------------------------------------------------------------------

def check_all_expiring(venture_slugs: list[str]) -> list[dict]:
    """
    Scan all provided ventures for credentials expiring within 7 days.
    Returns list of {venture_slug, name, expiry_status, expires_at}.
    """
    warnings = []
    for slug in venture_slugs:
        vault = CortexCredentialVault(slug)
        for cred in vault.expiring_soon():
            warnings.append({
                "venture_slug": slug,
                **cred,
            })
    return warnings


# ---------------------------------------------------------------------------
# Standalone key generation utility
# ---------------------------------------------------------------------------

def generate_and_print_key() -> None:
    """Print a new Fernet key to stdout. Use to seed CORTEX_VAULT_KEY."""
    if not _CRYPTO_AVAILABLE:
        print("ERROR: pip install cryptography")
        return
    key = Fernet.generate_key()
    print(f"CORTEX_VAULT_KEY={key.decode()}")


if __name__ == "__main__":
    generate_and_print_key()
