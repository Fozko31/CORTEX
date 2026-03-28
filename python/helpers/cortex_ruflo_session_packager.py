"""
cortex_ruflo_session_packager.py — Packages Loop 3 context for a Ruflo session.

When Loop 3 triggers, this module:
1. Generates the CORTEX operational report
2. Runs Loop 5 stack research (if scheduled same day)
3. Queries Ruflo's memory for architectural context
4. Runs the inter-agent protocol session
5. Sends the human report to the user via Telegram

This is the orchestration layer for the full bi-monthly Loop 3 + Loop 5 cycle.
"""

import json
import os
from datetime import datetime
from typing import Optional


async def run_loop3_full_cycle(include_stack_research: bool = False) -> dict:
    """
    Execute the complete bi-monthly optimization cycle.
    include_stack_research: True on bi-monthly day (Loop 5 feeds into Loop 3)
    Returns: {"success": bool, "report": str, "session_id": str}
    """
    from python.helpers import cortex_operational_reporter as op_reporter
    from python.helpers import cortex_interagent_protocol as protocol

    # 1. Generate operational report
    stack_findings = None
    if include_stack_research:
        try:
            from python.helpers import cortex_stack_researcher
            stack_findings = await cortex_stack_researcher.run_full_research()
        except Exception:
            stack_findings = None

    operational_report = op_reporter.generate(period_days=60, stack_findings=stack_findings)

    # 2. Query Ruflo memory for architectural context (inject into Ruflo's system prompt via session)
    ruflo_memory_context = await _fetch_ruflo_memory_context()
    if ruflo_memory_context:
        operational_report["ruflo_architectural_context"] = ruflo_memory_context

    # 3. Run inter-agent protocol session
    session = await protocol.run_loop3_session(
        operational_report=operational_report,
        stack_findings=stack_findings,
    )

    # 4. Send human report to Telegram
    report = session.human_report
    if report:
        try:
            from python.helpers.cortex_telegram_bot import TelegramBotHandler
            bot = TelegramBotHandler()
            # Send in chunks (Telegram 4000 char limit)
            chunks = [report[i:i+3800] for i in range(0, len(report), 3800)]
            for chunk in chunks:
                await bot.send_text(chunk)
        except Exception:
            pass

    # 5. Push session record to SurfSense cortex_optimization space
    try:
        from python.helpers.cortex_surfsense_push import push_to_optimization_space
        session_summary = _build_session_summary(session, operational_report)
        await push_to_optimization_space(
            title=f"Loop3 Session: {session.session_id}",
            content=session_summary,
            tags=["loop3", "architectural_review", datetime.now().strftime("%Y-%m")],
        )
    except Exception:
        pass

    return {
        "success": True,
        "session_id": session.session_id,
        "rounds": len([m for m in session.messages if m.sender == "ruflo"]),
        "proposals_count": len(session.final_proposals),
        "report": report,
    }


async def _fetch_ruflo_memory_context() -> Optional[str]:
    """
    Query Ruflo's memory for recent architectural decisions about CORTEX.
    Returns a brief summary string to inject into the session.
    """
    try:
        from python.helpers.cortex_surfsense_client import CortexSurfSenseClient
        # This queries Ruflo's exported architectural memory (pushed to SurfSense at phase completion)
        client = CortexSurfSenseClient()
        results = await client.search(
            space="cortex_optimization",
            query="CORTEX architectural decisions design rationale",
            top_k=3,
        )
        if results:
            context_parts = [r.get("content", "")[:300] for r in results]
            return "\n---\n".join(context_parts)
    except Exception:
        pass
    return None


def _build_session_summary(session, operational_report: dict) -> str:
    """Build a summary document for SurfSense."""
    proposals = session.final_proposals
    return (
        f"Loop 3 Session: {session.session_id}\n"
        f"Date: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"Rounds: {len([m for m in session.messages if m.sender == 'ruflo'])}\n"
        f"Converged: {session.converged}\n\n"
        f"Struggle clusters: {len(operational_report.get('struggle_clusters', []))}\n"
        f"Extension failures: {len(operational_report.get('extension_failures', []))}\n"
        f"Zero-call tools: {', '.join(operational_report.get('tool_usage', {}).get('zero_call_tools', []))}\n\n"
        f"Proposals ({len(proposals)}):\n"
        + "\n".join(f"- {p.get('description', '')} [{p.get('priority', 'medium')}]" for p in proposals)
        + f"\n\nFull Report:\n{session.human_report[:2000]}"
    )


async def register_loop3_task():
    """Register bi-monthly Loop 3 trigger using Agent Zero TaskScheduler."""
    try:
        from python.helpers.task_scheduler import TaskScheduler, ScheduledTask, TaskSchedule
        scheduler = TaskScheduler.get()
        task_name = "CORTEX Loop3 Bi-monthly Review"
        if scheduler.get_task_by_name(task_name):
            return
        schedule = TaskSchedule(
            minute="0", hour="4", day="1", month="1,3,5,7,9,11",
            weekday="*", timezone="CET",
        )
        task = ScheduledTask.create(
            name=task_name,
            system_prompt="You are CORTEX running a scheduled bi-monthly architectural review (Loop 3).",
            prompt="Trigger Loop 3 architectural review: use the self_improve tool with operation='run_loop3'.",
            schedule=schedule,
        )
        await scheduler.add_task(task)
    except Exception:
        pass


async def _scheduled_loop3():
    """Scheduled Loop 3 run — called by APScheduler."""
    try:
        # Same day as Loop 5 (which runs at 3am, Loop 3 at 4am)
        await run_loop3_full_cycle(include_stack_research=True)
    except Exception:
        pass
