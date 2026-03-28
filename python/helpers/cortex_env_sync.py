"""
CORTEX MCP Env Sync Utility
============================
Reads API keys from usr/.env and syncs them into the mcp_servers env dicts
inside usr/settings.json. Run manually whenever you add or rotate a key:

    python python/helpers/cortex_env_sync.py

Safe to run multiple times — only updates empty or placeholder values,
never overwrites a value already present in settings.json.

Supported MCP env mappings:
    github       → GITHUB_PERSONAL_ACCESS_TOKEN
    browserbase  → BROWSERBASE_API_KEY, BROWSERBASE_PROJECT_ID
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]          # c:\Users\Admin\CORTEX
ENV_FILE = ROOT / "usr" / ".env"
SETTINGS_FILE = ROOT / "usr" / "settings.json"

# Keys each MCP server needs, mapped to the .env variable name
MCP_KEY_MAP: dict[str, dict[str, str]] = {
    "github": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_PERSONAL_ACCESS_TOKEN",
    },
    "browserbase": {
        "BROWSERBASE_API_KEY": "BROWSERBASE_API_KEY",
        "BROWSERBASE_PROJECT_ID": "BROWSERBASE_PROJECT_ID",
    },
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE pairs from a .env file. Ignores comments and blanks."""
    env: dict[str, str] = {}
    if not path.exists():
        print(f"[env-sync] WARNING: .env not found at {path}")
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)$', line)
        if match:
            key, val = match.group(1), match.group(2).strip().strip('"').strip("'")
            env[key] = val
    return env


def sync(dry_run: bool = False) -> None:
    env = load_env(ENV_FILE)

    settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    mcp_raw: str = settings.get("mcp_servers", "{}")
    mcp_cfg: dict = json.loads(mcp_raw)
    servers: dict = mcp_cfg.get("mcpServers", {})

    changed = False
    for server_name, key_map in MCP_KEY_MAP.items():
        if server_name not in servers:
            continue
        server_env: dict = servers[server_name].setdefault("env", {})
        for settings_key, env_key in key_map.items():
            env_val = env.get(env_key, "")
            current = server_env.get(settings_key, "")
            if env_val and not current:
                print(f"[env-sync] {server_name}: set {settings_key} from .env")
                server_env[settings_key] = env_val
                changed = True
            elif not env_val and not current:
                print(f"[env-sync] {server_name}: {settings_key} missing in both .env and settings (skipped)")
            else:
                print(f"[env-sync] {server_name}: {settings_key} already set — not overwriting")

    if changed and not dry_run:
        settings["mcp_servers"] = json.dumps(mcp_cfg)
        SETTINGS_FILE.write_text(
            json.dumps(settings, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )
        print("[env-sync] settings.json updated.")
    elif changed and dry_run:
        print("[env-sync] DRY RUN — no changes written.")
    else:
        print("[env-sync] Nothing to update.")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sync(dry_run=dry)
