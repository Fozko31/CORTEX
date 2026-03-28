"""
self_improve.py — Agent-callable tool for CORTEX self-optimization (Phase G).

Operations:
  trigger_analysis   — Run Loop 1: aggregate struggles → generate hypotheses → send to Telegram
  run_experiment     — Run a specific experiment by hypothesis rank or ID
  show_report        — Show the latest experiment report
  apply              — Apply an approved experiment to live files
  reject             — Reject an experiment (no changes made)
  show_versions      — List all pinned CORTEX versions
  get_version        — Get full version report for a specific version
  rollback_request   — Stage a rollback (first confirmation step)
  rollback_execute   — Execute staged rollback (second confirmation step)
  benchmark          — Run the 20-query benchmark suite
  show_status        — Overall self-improvement system status
"""

import asyncio
import json
from typing import Any, Optional

from python.cortex.tool import Tool, Response


class SelfImprove(Tool):
    async def execute(self, **kwargs) -> Response:
        operation = kwargs.get("operation", "show_status")
        params = kwargs.get("params", {})

        handlers = {
            "trigger_analysis": self._trigger_analysis,
            "run_experiment": self._run_experiment,
            "show_report": self._show_report,
            "apply": self._apply,
            "reject": self._reject,
            "show_versions": self._show_versions,
            "get_version": self._get_version,
            "rollback_request": self._rollback_request,
            "rollback_execute": self._rollback_execute,
            "benchmark": self._benchmark,
            "show_status": self._show_status,
        }

        handler = handlers.get(operation, self._show_status)
        try:
            result = await handler(params)
            return Response(message=result, break_loop=False)
        except Exception as e:
            return Response(message=f"self_improve error ({operation}): {e}", break_loop=False)

    # ─── HANDLERS ────────────────────────────────────────────────────────────

    async def _trigger_analysis(self, params: dict) -> str:
        days = int(params.get("days", 7))
        top_n = int(params.get("top_n", 3))

        from python.helpers import cortex_struggle_aggregator as agg
        hypotheses = agg.run(days=days, top_n=top_n)

        if not hypotheses:
            return "No significant struggle patterns found in the past week. CORTEX is performing within normal range."

        # Store hypotheses for later reference
        self.agent.set_data("cortex_pending_hypotheses", [h.to_dict() for h in hypotheses])

        telegram_msg = agg.format_for_telegram(hypotheses)

        # Send via Telegram if available
        try:
            from python.helpers.cortex_telegram_bot import TelegramBotHandler
            bot = TelegramBotHandler()
            await bot.send_text(telegram_msg)
        except Exception:
            pass

        return f"Analysis complete. Found {len(hypotheses)} improvement opportunities:\n\n{telegram_msg}"

    async def _run_experiment(self, params: dict) -> str:
        rank = params.get("rank")
        exp_id = params.get("experiment_id")
        dry_run = bool(params.get("dry_run", False))

        # Load pending hypotheses
        hypotheses_raw = self.agent.get_data("cortex_pending_hypotheses") or []
        if not hypotheses_raw:
            return "No pending hypotheses. Run trigger_analysis first."

        from python.helpers.cortex_struggle_aggregator import ImprovementHypothesis
        hypotheses = [ImprovementHypothesis(**h) for h in hypotheses_raw]

        # Select hypothesis
        selected = None
        if rank is not None:
            selected = next((h for h in hypotheses if h.rank == int(rank)), None)
        elif exp_id:
            selected = next((h for h in hypotheses if h.experiment_id == exp_id), None)
        else:
            selected = hypotheses[0]  # default to top

        if not selected:
            return f"Hypothesis not found (rank={rank}, id={exp_id})."

        from python.helpers.cortex_experiment_runner import run_experiment
        from python.helpers.cortex_experiment_reporter import build_report, build_telegram_summary

        result = await run_experiment(selected, dry_run=dry_run)

        # Store result for apply/reject
        self.agent.set_data(f"cortex_experiment_result_{result.experiment_id}", result.to_dict())

        # Send Telegram summary
        summary = build_telegram_summary(result)
        try:
            from python.helpers.cortex_telegram_bot import TelegramBotHandler
            bot = TelegramBotHandler()
            await bot.send_text(summary)
        except Exception:
            pass

        # Return full report
        return build_report(result)

    async def _show_report(self, params: dict) -> str:
        exp_id = params.get("experiment_id", "")

        if not exp_id:
            from python.helpers import cortex_event_store as es
            history = es.get_experiment_history(days=30)
            if not history:
                return "No experiments run in the past 30 days."
            recent = history[0]
            exp_id = recent.get("experiment_id", "")

        result_data = self.agent.get_data(f"cortex_experiment_result_{exp_id}")
        if not result_data:
            return f"No in-memory result for experiment {exp_id}. Run the experiment first."

        from python.helpers.cortex_experiment_reporter import build_report
        from python.helpers.cortex_experiment_runner import ExperimentResult, QueryResult

        # Reconstruct result object
        qrs = [QueryResult(**qr) for qr in result_data.get("query_results_raw", [])] if "query_results_raw" in result_data else []
        result = ExperimentResult(
            experiment_id=result_data["experiment_id"],
            hypothesis=result_data["hypothesis"],
            checkpoint_tag=result_data.get("checkpoint_tag", ""),
            baseline_avg=result_data["baseline_avg"],
            experimental_avg=result_data["experimental_avg"],
            overall_delta=result_data["overall_delta"],
            queries_run=result_data["queries_run"],
            query_results=qrs,
            improved_count=result_data.get("improved_count", 0),
            degraded_count=result_data.get("degraded_count", 0),
            neutral_count=result_data.get("neutral_count", 0),
        )
        return build_report(result)

    async def _apply(self, params: dict) -> str:
        exp_id = params.get("experiment_id", "")
        if not exp_id:
            return "experiment_id required."

        result_data = self.agent.get_data(f"cortex_experiment_result_{exp_id}")
        if not result_data:
            return f"No result found for {exp_id}. Run the experiment first."

        from python.helpers.cortex_experiment_applier import apply_experiment
        outcome = apply_experiment(result_data, approved_by="user")
        return outcome.get("message", "Apply failed.")

    async def _reject(self, params: dict) -> str:
        exp_id = params.get("experiment_id", "")
        reason = params.get("reason", "")
        if not exp_id:
            return "experiment_id required."

        result_data = self.agent.get_data(f"cortex_experiment_result_{exp_id}")
        if not result_data:
            return f"No result found for {exp_id}."

        from python.helpers.cortex_experiment_applier import reject_experiment
        outcome = reject_experiment(result_data, reason=reason)
        return outcome.get("message", "Reject logged.")

    async def _show_versions(self, params: dict) -> str:
        stable_only = bool(params.get("stable_only", True))
        from python.helpers import cortex_version_manager as vm
        versions = vm.list_versions(stable_only=stable_only)
        if not versions:
            return "No versions pinned yet."
        lines = ["**CORTEX Versions:**", ""]
        for v in versions[-10:]:  # last 10
            name = v.get("name") or v.get("id", "unknown")
            vtype = v.get("type", "")
            date = v.get("timestamp", "")[:10]
            lines.append(f"- `{v['id']}` — {name} ({vtype}) — {date}")
        return "\n".join(lines)

    async def _get_version(self, params: dict) -> str:
        version_id = params.get("version_id", "")
        fmt = params.get("format", "human")
        if not version_id:
            from python.helpers import cortex_version_manager as vm
            current = vm.get_current_version()
            if not current:
                return "No current version set."
            version_id = current
        from python.helpers import cortex_version_manager as vm
        return vm.get_version_report(version_id, format=fmt)

    async def _rollback_request(self, params: dict) -> str:
        tag = params.get("tag", "")
        reason = params.get("reason", "")
        failed_assumptions = params.get("failed_assumptions", "")
        if not tag or not reason:
            return "Both 'tag' and 'reason' are required for rollback."
        from python.helpers import cortex_version_manager as vm
        result = vm.rollback_request(tag, reason, failed_assumptions)
        return result.get("warning", str(result))

    async def _rollback_execute(self, params: dict) -> str:
        confirm_phrase = params.get("confirm_phrase", "")
        if not confirm_phrase:
            return "confirm_phrase required. Get it from rollback_request."
        from python.helpers import cortex_version_manager as vm
        result = vm.rollback_execute(confirm_phrase)
        return result.get("message", str(result))

    async def _benchmark(self, params: dict) -> str:
        dry_run = bool(params.get("dry_run", False))
        query_ids = params.get("query_ids", [])  # empty = run all

        from python.helpers.cortex_benchmark_runner import run_benchmark
        result = await run_benchmark(query_ids=query_ids or None, dry_run=dry_run)
        return result.get("summary", "Benchmark complete.")

    async def _show_status(self, params: dict) -> str:
        lines = ["**CORTEX Self-Optimization Status**", ""]

        # Event store
        from python.helpers import cortex_event_store as es
        db_ok = es.health_check()
        lines.append(f"Event store: {'OK' if db_ok else 'ERROR'}")

        struggles = es.get_struggle_events(days=7)
        lines.append(f"Struggles (last 7 days): {len(struggles)}")

        corrections = es.get_correction_summary(days=30)
        if corrections:
            top_correction = corrections[0]
            lines.append(f"Top correction type (30d): {top_correction.get('correction_type')} ({top_correction.get('count')}x)")

        # Experiments
        experiments = es.get_experiment_history(days=90)
        applied = sum(1 for e in experiments if e.get("applied"))
        lines.append(f"Experiments (90d): {len(experiments)} total, {applied} applied")

        # Version manager
        from python.helpers import cortex_version_manager as vm
        vm_status = vm.health_check()
        lines.append(f"Versions pinned: {vm_status.get('stable_versions', 0)}")
        current = vm_status.get("current")
        if current:
            lines.append(f"Current version: {current}")
        if vm_status.get("pending_rollback"):
            lines.append("WARNING: Pending rollback request exists.")

        # Benchmark drift
        try:
            from python.helpers import cortex_benchmark_runner as br
            drift = br.get_drift_summary()
            degrading = [q for q, d in drift.items() if d.get("trend") == "degrading"]
            if degrading:
                lines.append(f"Degrading queries: {', '.join(degrading)}")
            else:
                lines.append("Benchmark drift: stable (no degrading queries)")
        except Exception:
            lines.append("Benchmark: no data yet")

        return "\n".join(lines)
