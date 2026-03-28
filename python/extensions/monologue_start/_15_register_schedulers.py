from python.cortex.extension import Extension


class CortexRegisterSchedulers(Extension):
    async def execute(self, **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
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
        # All loops use Agent Zero TaskScheduler (not APScheduler directly).
        # TaskScheduler tasks prompt CORTEX to run the tool — autonomous loop.

        # Loop 1: weekly self-improvement (Saturday 1am CET)
        try:
            from python.cortex.scheduler import TaskScheduler, ScheduledTask, TaskSchedule
            scheduler = TaskScheduler.get()
            task_name = "CORTEX Loop1 Weekly Self-Improvement"
            if not scheduler.get_task_by_name(task_name):
                schedule = TaskSchedule(
                    minute="0", hour="1", day="*", month="*",
                    weekday="6",  # Saturday
                    timezone="CET",
                )
                task = ScheduledTask.create(
                    name=task_name,
                    system_prompt="You are CORTEX running the weekly self-improvement loop (Loop 1).",
                    prompt=(
                        "Run the weekly self-improvement analysis: use the self_improve tool "
                        "with operation='trigger_analysis'. Then for each hypothesis returned, "
                        "run operation='run_experiment'. Show the report and wait for approval "
                        "before applying."
                    ),
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
                    system_prompt="You are CORTEX running the monthly outcome attribution loop (Loop 2).",
                    prompt=(
                        "Run monthly outcome signal processing: call run_monthly_signal_processing() "
                        "from cortex_optimization_signal and report results via Telegram."
                    ),
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
                    system_prompt="You are CORTEX running the bi-monthly technology stack research (Loop 5).",
                    prompt=(
                        "Run stack research: call run_full_research() from cortex_stack_researcher, "
                        "then call run_full_evaluation() from cortex_stack_evaluator with the findings. "
                        "Report any REPLACE_NOW or INVESTIGATE items via Telegram."
                    ),
                    schedule=schedule,
                )
                await scheduler.add_task(task)
        except Exception:
            pass
