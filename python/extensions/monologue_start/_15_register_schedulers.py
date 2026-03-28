from python.cortex.extension import Extension
from python.cortex.config import CortexConfig


# ---------------------------------------------------------------------------
# Scheduled callables — APScheduler calls these directly (no agent context)
# ---------------------------------------------------------------------------

async def _loop1_self_improvement() -> None:
    """Loop 1: Weekly self-improvement — aggregate struggles + send hypotheses to Telegram."""
    try:
        from python.helpers import cortex_struggle_aggregator as agg
        hypotheses = agg.run(days=7, top_n=3)
        if hypotheses:
            telegram_msg = agg.format_for_telegram(hypotheses)
            try:
                from python.helpers.cortex_telegram_bot import TelegramBotHandler
                await TelegramBotHandler().send_text(telegram_msg)
            except Exception:
                pass
    except Exception:
        pass


async def _loop2_outcome_signals() -> None:
    """Loop 2: Monthly outcome signal processing."""
    try:
        from python.helpers.cortex_optimization_signal import run_monthly_signal_processing
        await run_monthly_signal_processing(agent=None)
    except Exception:
        pass


async def _loop5_stack_research() -> None:
    """Loop 5: Bi-monthly stack research + evaluation."""
    try:
        from python.helpers.cortex_stack_researcher import run_full_research
        from python.helpers.cortex_stack_evaluator import run_full_evaluation
        findings = await run_full_research()
        results = await run_full_evaluation(findings)
        flagged = [r for r in results.get("evaluations", [])
                   if r.get("decision") in ("REPLACE_NOW", "INVESTIGATE")]
        if flagged:
            msg = "CORTEX Stack Research Alert\n" + "\n".join(
                f"• {r['component']}: {r['decision']}" for r in flagged
            )
            try:
                from python.helpers.cortex_telegram_bot import TelegramBotHandler
                await TelegramBotHandler().send_text(msg)
            except Exception:
                pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Extension
# ---------------------------------------------------------------------------

class CortexRegisterSchedulers(Extension):
    async def execute(self, **kwargs) -> None:
        agent = self.agent
        profile = CortexConfig.from_agent_config(agent.config).profile
        if not profile.startswith("cortex"):
            return

        try:
            from python.helpers.cortex_weekly_digest import register_weekly_digest_task
            await register_weekly_digest_task()
        except Exception:
            pass

        try:
            from python.helpers.cortex_proactive_engine import register_proactive_task
            await register_proactive_task()
        except Exception:
            pass

        try:
            from python.helpers.cortex_discovery_scheduler import register_discovery_task
            await register_discovery_task(agent)
        except Exception:
            pass

        try:
            from python.helpers.cortex_memory_backup import register_backup_task
            await register_backup_task()
        except Exception:
            pass

        # ── Phase G: Self-Optimization Loops ──────────────────────────────

        # Loop 1: weekly self-improvement (Saturday 1am CET)
        try:
            from python.cortex.scheduler import TaskScheduler, ScheduledTask, TaskSchedule
            scheduler = TaskScheduler.get()
            task_name = "CORTEX Loop1 Weekly Self-Improvement"
            if not scheduler.get_task_by_name(task_name):
                schedule = TaskSchedule(
                    minute="0", hour="1", day="*", month="*",
                    weekday="6", timezone="CET",
                )
                task = ScheduledTask.create(
                    name=task_name,
                    callable_fn=_loop1_self_improvement,
                    schedule=schedule,
                )
                await scheduler.add_task(task)
        except Exception:
            pass

        # Loop 2: monthly outcome signal processing (20th of month, 3am CET)
        try:
            from python.cortex.scheduler import TaskScheduler, ScheduledTask, TaskSchedule
            scheduler = TaskScheduler.get()
            task_name = "CORTEX Loop2 Monthly Outcome Signals"
            if not scheduler.get_task_by_name(task_name):
                schedule = TaskSchedule(
                    minute="0", hour="3", day="20", month="*",
                    weekday="*", timezone="CET",
                )
                task = ScheduledTask.create(
                    name=task_name,
                    callable_fn=_loop2_outcome_signals,
                    schedule=schedule,
                )
                await scheduler.add_task(task)
        except Exception:
            pass

        # Loop 3+5: bi-monthly architectural review (1st of odd months, 4am CET)
        try:
            from python.helpers.cortex_ruflo_session_packager import register_loop3_task
            await register_loop3_task()
        except Exception:
            pass

        # Loop 4: monthly benchmark (15th of month, 2am CET)
        try:
            from python.helpers.cortex_benchmark_runner import register_benchmark_task
            await register_benchmark_task()
        except Exception:
            pass

        # Loop 5: bi-monthly stack research (1st of odd months, 3am CET)
        try:
            from python.cortex.scheduler import TaskScheduler, ScheduledTask, TaskSchedule
            scheduler = TaskScheduler.get()
            task_name = "CORTEX Loop5 Bi-monthly Stack Research"
            if not scheduler.get_task_by_name(task_name):
                schedule = TaskSchedule(
                    minute="0", hour="3", day="1", month="1,3,5,7,9,11",
                    weekday="*", timezone="CET",
                )
                task = ScheduledTask.create(
                    name=task_name,
                    callable_fn=_loop5_stack_research,
                    schedule=schedule,
                )
                await scheduler.add_task(task)
        except Exception:
            pass
