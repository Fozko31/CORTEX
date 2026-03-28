"""
CORTEX Watchdog -- Phase E
==========================

Cross-platform process monitor for CORTEX. Runs run_ui.py as a subprocess
and restarts it automatically on any exit (crash or clean shutdown).

Usage:
    python cortex_watchdog.py          # uses python run_ui.py
    python cortex_watchdog.py --dry-run  # print config, don't start

Purpose:
    Built for commercial desktop packaging — users who run CORTEX locally
    on Windows/Mac/Linux without a cloud layer (Fly.io etc). On Fly.io,
    restart.policy="always" in fly.toml replaces this entirely.

Config (environment variables):
    CORTEX_WATCHDOG_MAX_RESTARTS_PER_HOUR  -- default 10
    CORTEX_WATCHDOG_RESTART_DELAY          -- seconds between restarts, default 5
    CORTEX_WATCHDOG_LOG                    -- log file path, default usr/memory/cortex_main/watchdog.log
"""

from __future__ import annotations

import os
import sys
import time
import subprocess
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import deque


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_RESTARTS_PER_HOUR = int(os.getenv("CORTEX_WATCHDOG_MAX_RESTARTS_PER_HOUR", "10"))
RESTART_DELAY = int(os.getenv("CORTEX_WATCHDOG_RESTART_DELAY", "5"))
LOG_PATH = os.getenv(
    "CORTEX_WATCHDOG_LOG",
    os.path.join("usr", "memory", "cortex_main", "watchdog.log"),
)

CORTEX_DIR = Path(__file__).parent
TARGET = [sys.executable, str(CORTEX_DIR / "run_ui.py")]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _ensure_log_dir():
    log_dir = Path(LOG_PATH).parent
    log_dir.mkdir(parents=True, exist_ok=True)


def _log(msg: str):
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        _ensure_log_dir()
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Watchdog loop
# ---------------------------------------------------------------------------

def run():
    _log(f"CORTEX Watchdog started. Target: {' '.join(TARGET)}")
    _log(f"Config: max_restarts_per_hour={MAX_RESTARTS_PER_HOUR}, restart_delay={RESTART_DELAY}s")

    restart_times: deque[datetime] = deque()
    restart_count = 0

    while True:
        _log(f"Starting CORTEX (restart #{restart_count})...")

        try:
            proc = subprocess.Popen(TARGET, cwd=str(CORTEX_DIR))
            exit_code = proc.wait()
        except KeyboardInterrupt:
            _log("Watchdog interrupted by user. Shutting down.")
            try:
                proc.terminate()
            except Exception:
                pass
            sys.exit(0)
        except Exception as e:
            _log(f"Failed to start CORTEX: {e}")
            exit_code = -1

        now = datetime.utcnow()
        restart_times.append(now)

        # Prune restart timestamps older than 1 hour
        cutoff = now - timedelta(hours=1)
        while restart_times and restart_times[0] < cutoff:
            restart_times.popleft()

        restarts_this_hour = len(restart_times)
        _log(
            f"CORTEX exited (code={exit_code}). "
            f"Restarts in last hour: {restarts_this_hour}/{MAX_RESTARTS_PER_HOUR}"
        )

        if restarts_this_hour >= MAX_RESTARTS_PER_HOUR:
            _log(
                f"WARNING: {MAX_RESTARTS_PER_HOUR} restarts in the last hour. "
                f"Possible crash loop. Waiting 60s before next attempt."
            )
            time.sleep(60)
        else:
            _log(f"Restarting in {RESTART_DELAY}s...")
            time.sleep(RESTART_DELAY)

        restart_count += 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CORTEX process watchdog")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print configuration and exit without starting CORTEX",
    )
    args = parser.parse_args()

    if args.dry_run:
        print(f"Target:                  {' '.join(TARGET)}")
        print(f"Max restarts/hour:       {MAX_RESTARTS_PER_HOUR}")
        print(f"Restart delay:           {RESTART_DELAY}s")
        print(f"Log path:                {LOG_PATH}")
        print(f"CORTEX dir:              {CORTEX_DIR}")
        return

    run()


if __name__ == "__main__":
    main()
