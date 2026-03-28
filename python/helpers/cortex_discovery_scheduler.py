"""
CORTEX Discovery Scheduler -- Phase D, D-10 (fixed Phase E)
=============================================================

Registers a periodic autonomous discovery task that:
1. Loads VentureDiscoveryParameters (niche targets + settings)
2. Runs run_discovery() for each target niche (fast mode by default)
3. Results auto-queue via the orchestrator (D-8)

Schedule: Daily at 03:00 UTC (off-peak).
Guard: Only runs if CORTEX_DISCOVERY_AUTO=1 env var is set.
Cost guard: max_cost_eur=0.10 per niche (fast mode ~EUR 0.025).

Uses Agent Zero's TaskScheduler (in-process, cross-platform, persisted to
usr/scheduler/tasks.json). Previous D-10 version wrote to Unix system crontab
which is a no-op on Windows -- fixed here.
"""

from __future__ import annotations

import os
import asyncio
from typing import Optional


_TASK_NAME = "CORTEX Discovery Loop"
_registered = False


async def register_discovery_task(agent=None) -> None:
    """
    Register the daily discovery loop task once per process via TaskScheduler.
    Safe to call multiple times — uses a module-level guard.
    Only activates if CORTEX_DISCOVERY_AUTO=1 env var is set.
    """
    global _registered
    if _registered:
        return

    if not os.getenv("CORTEX_DISCOVERY_AUTO", "").strip():
        return

    try:
        from python.helpers.task_scheduler import TaskScheduler, ScheduledTask, TaskSchedule

        scheduler = TaskScheduler.get()

        if scheduler.get_task_by_name(_TASK_NAME):
            _registered = True
            return

        schedule = TaskSchedule(
            minute="0",
            hour="3",
            day="*",
            month="*",
            weekday="*",
            timezone="UTC",
        )

        task = ScheduledTask.create(
            name=_TASK_NAME,
            system_prompt=(
                "You are CORTEX running the autonomous discovery loop. "
                "Your job is to scan configured target niches for venture opportunities "
                "in fast mode and queue high-scoring candidates for review."
            ),
            prompt=(
                "Run the autonomous discovery loop now. "
                "Use the venture_discover tool with mode='autonomous'. "
                "This scans all configured target niches in fast mode."
            ),
            schedule=schedule,
        )

        await scheduler.add_task(task)
        _registered = True
        print(f"[CORTEX discovery_scheduler] Registered daily discovery task at 03:00 UTC")

    except Exception as e:
        print(f"[CORTEX discovery_scheduler] Could not register task: {e}")


async def run_discovery_loop(agent=None, max_niches: int = 5) -> None:
    """
    Run one pass of the autonomous discovery loop.
    Called by the scheduled cron task or manually via the agent.

    Loads target niches from VentureDiscoveryParameters and runs
    run_discovery (fast mode) for each, up to max_niches.
    """
    from python.helpers.cortex_discovery_params import VentureDiscoveryParameters
    from python.helpers.cortex_discovery_orchestrator import run_discovery

    try:
        params = VentureDiscoveryParameters.load() or VentureDiscoveryParameters()
    except Exception:
        params = VentureDiscoveryParameters()

    target_niches = getattr(params, "target_niches", []) or []
    if not target_niches:
        print("[CORTEX discovery_scheduler] No target niches configured — skipping loop")
        return

    market = getattr(params, "geography", "global") or "global"
    niches_to_run = target_niches[:max_niches]

    print(
        f"[CORTEX discovery_scheduler] Starting loop: "
        f"{len(niches_to_run)} niches | market={market}"
    )

    for i, niche in enumerate(niches_to_run, 1):
        print(f"[CORTEX discovery_scheduler] [{i}/{len(niches_to_run)}] '{niche}'")
        try:
            result = await run_discovery(
                niche=niche,
                market=market,
                params=params,
                agent=agent,
                skip_influencers=True,   # fast mode for autonomous loop
                max_cost_eur=0.10,
            )
            print(
                f"[CORTEX discovery_scheduler] '{niche}': "
                f"{result.outcome} | score={result.final_score or 0:.1f}"
            )
        except Exception as e:
            print(f"[CORTEX discovery_scheduler] '{niche}' error: {e}")

    print("[CORTEX discovery_scheduler] Loop complete")
