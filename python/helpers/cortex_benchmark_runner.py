"""
cortex_benchmark_runner.py — Loop 4: runs the 20-query test suite on a schedule.

Tracks score drift over time. Flags if any query drops >10 points from 3-month
rolling average — does not wait for monthly report in that case.

Schedule: 15th of each month, 2am CET (registered in _15_register_schedulers.py)
"""

import os
from datetime import date
from typing import Optional

import httpx

from python.helpers.cortex_experiment_suite import SUITE, TestQuery
from python.helpers.cortex_experiment_judge import evaluate

_RUN_DATE_FORMAT = "%Y-%m-%d"
_DRIFT_THRESHOLD = 10.0  # points drop that triggers immediate flag
_EXPERIMENT_MODEL = "deepseek/deepseek-chat-v3-0324"
_OR_BASE = "https://openrouter.ai/api/v1/chat/completions"


async def run_benchmark(
    query_ids: Optional[list] = None,
    dry_run: bool = False,
    system_prompt: Optional[str] = None,
) -> dict:
    """
    Run the test suite. query_ids=None means run all 20.
    Returns summary dict + drift analysis.
    """
    from python.helpers import cortex_event_store as es

    queries = SUITE if not query_ids else [q for q in SUITE if q.id in query_ids]
    run_date = date.today().isoformat()

    # Load system prompt (current live role.md)
    if system_prompt is None:
        system_prompt = _load_current_system_prompt()

    results = {}
    for q in queries:
        if dry_run:
            score = 72.0
            rubric_scores = {c.key: 1 for c in q.rubric}
        else:
            response = await _call_model(q, system_prompt)
            judge_result = await evaluate(q.id, q.query, response, q.rubric)
            score = judge_result.overall_score
            rubric_scores = {cs.key: cs.score for cs in judge_result.criterion_scores}

        results[q.id] = {"score": score, "rubric_scores": rubric_scores}

        es.log_benchmark_run(
            run_date=run_date,
            query_id=q.id,
            score=score,
            rubric_scores=rubric_scores,
            judge_model="deepseek/deepseek-chat-v3-0324" if not dry_run else "dry_run",
        )

    # Compute drift
    drift = {}
    immediate_flags = []
    for q in queries:
        d = es.get_benchmark_drift(q.id, window_days=90)
        drift[q.id] = d
        if d.get("trend") == "degrading":
            delta = results[q.id]["score"] - d.get("avg_score", results[q.id]["score"])
            if abs(delta) >= _DRIFT_THRESHOLD:
                immediate_flags.append({"query_id": q.id, "drop": round(delta, 1)})

    avg_score = sum(r["score"] for r in results.values()) / len(results) if results else 0

    summary_lines = [
        f"**Benchmark Run — {run_date}**",
        f"Queries: {len(results)} | Avg score: {avg_score:.1f}/100",
        "",
    ]

    if immediate_flags:
        summary_lines.append("ALERT — Significant score drops detected:")
        for f in immediate_flags:
            summary_lines.append(f"  - {f['query_id']}: {f['drop']:.1f} pts below rolling avg")
        summary_lines.append("")

    degrading = [qid for qid, d in drift.items() if d.get("trend") == "degrading"]
    improving = [qid for qid, d in drift.items() if d.get("trend") == "improving"]

    if degrading:
        summary_lines.append(f"Degrading queries: {', '.join(degrading)}")
    if improving:
        summary_lines.append(f"Improving queries: {', '.join(improving)}")
    if not degrading and not improving:
        summary_lines.append("All queries stable.")

    return {
        "run_date": run_date,
        "queries_run": len(results),
        "avg_score": round(avg_score, 1),
        "scores": {qid: r["score"] for qid, r in results.items()},
        "drift": drift,
        "immediate_flags": immediate_flags,
        "summary": "\n".join(summary_lines),
    }


def get_drift_summary(days: int = 90) -> dict:
    """Returns drift status for all queries."""
    from python.helpers import cortex_event_store as es
    return {q.id: es.get_benchmark_drift(q.id, window_days=days) for q in SUITE}


async def register_benchmark_task():
    """Register the monthly benchmark run via APScheduler."""
    try:
        from python.cortex.scheduler import TaskScheduler, ScheduledTask, TaskSchedule
        scheduler = TaskScheduler.get()
        task_name = "CORTEX Loop4 Monthly Benchmark"
        if scheduler.get_task_by_name(task_name):
            return
        schedule = TaskSchedule(
            minute="0", hour="2", day="15", month="*",
            weekday="*", timezone="CET",
        )
        task = ScheduledTask.create(
            name=task_name,
            callable_fn=_scheduled_benchmark,
            schedule=schedule,
        )
        await scheduler.add_task(task)
    except Exception:
        pass


async def _scheduled_benchmark():
    """Scheduled benchmark run — called by APScheduler."""
    try:
        result = await run_benchmark()
        # Send summary to Telegram
        if result.get("immediate_flags"):
            from python.helpers.cortex_telegram_bot import TelegramBotHandler
            bot = TelegramBotHandler()
            await bot.send_text(f"CORTEX Benchmark Alert\n{result['summary']}")
    except Exception:
        pass


async def _call_model(query: TestQuery, system_prompt: str) -> str:
    api_key = os.environ.get("API_KEY_OPENROUTER", "")
    if not api_key:
        return "[no API key]"
    try:
        context = f"\n\nContext: {query.system_context}" if query.system_context else ""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _OR_BASE,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": _EXPERIMENT_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query.query + context},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 600,
                },
            )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        return f"[HTTP {resp.status_code}]"
    except Exception as e:
        return f"[error: {str(e)[:60]}]"


def _load_current_system_prompt() -> str:
    role_path = "agents/cortex/prompts/agent.system.main.role.md"
    try:
        if os.path.exists(role_path):
            with open(role_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return "You are CORTEX, an AI business partner and COO."
