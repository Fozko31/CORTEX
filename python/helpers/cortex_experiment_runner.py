"""
cortex_experiment_runner.py — Runs a single Loop 1 experiment.

For a given hypothesis:
1. Pre-experiment checkpoint (git tag + FAISS snapshot)
2. Apply proposed change to target file (temporarily)
3. Run all 20 test queries against the MODIFIED prompt/knowledge
4. Revert the change
5. Run all 20 queries against the ORIGINAL prompt/knowledge (baseline)
6. Judge both sets of outputs
7. Compute delta
8. Return ExperimentResult

Safety:
  - Mutex file prevents concurrent experiments
  - Budget cap: max N queries per run (default 20)
  - Always reverts target file even if an exception occurs
  - Never touches cloud memory (Zep, SurfSense) during experiments
"""

import asyncio
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from python.helpers.cortex_experiment_suite import SUITE, TestQuery
from python.helpers.cortex_experiment_judge import JudgeResult, evaluate, score_delta
from python.helpers.cortex_struggle_aggregator import ImprovementHypothesis

_LOCK_FILE = "cortex_experiment.lock"
_OR_BASE = "https://openrouter.ai/api/v1/chat/completions"
_EXPERIMENT_MODEL = "deepseek/deepseek-chat-v3-0324"  # cheap for bulk runs
_BUDGET_QUERIES = 20  # max test queries per run
_QUERY_TIMEOUT = 30  # seconds per query


def _lock_path() -> str:
    try:
        from python.helpers.memory import abs_db_dir
        base = abs_db_dir("cortex_main")
    except Exception:
        base = os.path.join("usr", "memory", "cortex_main")
    return os.path.join(base, _LOCK_FILE)


@dataclass
class QueryResult:
    query_id: str
    query_text: str
    baseline_response: str
    experimental_response: str
    baseline_score: float
    experimental_score: float
    delta: float
    criterion_detail: dict = field(default_factory=dict)


@dataclass
class ExperimentResult:
    experiment_id: str
    hypothesis: dict
    checkpoint_tag: str
    baseline_avg: float
    experimental_avg: float
    overall_delta: float
    queries_run: int
    query_results: list[QueryResult] = field(default_factory=list)
    improved_count: int = 0
    degraded_count: int = 0
    neutral_count: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "checkpoint_tag": self.checkpoint_tag,
            "baseline_avg": round(self.baseline_avg, 1),
            "experimental_avg": round(self.experimental_avg, 1),
            "overall_delta": round(self.overall_delta, 1),
            "queries_run": self.queries_run,
            "improved_count": self.improved_count,
            "degraded_count": self.degraded_count,
            "neutral_count": self.neutral_count,
            "error": self.error,
        }


async def run_experiment(hypothesis: ImprovementHypothesis, dry_run: bool = False) -> ExperimentResult:
    """
    Full experiment pipeline for a single hypothesis.
    dry_run=True: skips actual file modification and LLM calls (for testing).
    """
    lock_path = _lock_path()

    # Mutex: prevent concurrent experiments
    if os.path.exists(lock_path):
        return ExperimentResult(
            experiment_id=hypothesis.experiment_id,
            hypothesis=hypothesis.to_dict(),
            checkpoint_tag="",
            baseline_avg=0,
            experimental_avg=0,
            overall_delta=0,
            queries_run=0,
            error="Another experiment is already running (lock file exists).",
        )

    # Create lock
    try:
        with open(lock_path, "w") as f:
            f.write(f"{hypothesis.experiment_id}\n{time.time()}")
    except Exception:
        pass

    try:
        return await _run_experiment_locked(hypothesis, dry_run)
    finally:
        try:
            os.remove(lock_path)
        except Exception:
            pass


async def _run_experiment_locked(hypothesis: ImprovementHypothesis, dry_run: bool) -> ExperimentResult:
    exp_id = hypothesis.experiment_id
    hyp_dict = hypothesis.to_dict()

    # 1. Pre-experiment checkpoint
    checkpoint_tag = ""
    if not dry_run:
        from python.helpers import cortex_version_manager as vm
        chk = vm.pre_experiment_checkpoint(f"{exp_id}: {hypothesis.cluster_topic}")
        checkpoint_tag = chk.get("tag", "")

    # 2. Load queries (capped at budget)
    queries = SUITE[:_BUDGET_QUERIES]

    # 3. Get system prompt (baseline)
    baseline_system = _load_system_prompt(hypothesis.target_file, hypothesis.target_type)

    # 4. Apply proposed change (experimental system prompt)
    experimental_system = baseline_system
    if not dry_run:
        experimental_system = _apply_change(baseline_system, hypothesis)

    # 5. Run experimental queries
    experimental_responses = {}
    if dry_run:
        experimental_responses = {q.id: f"[dry-run experimental response for {q.id}]" for q in queries}
    else:
        experimental_responses = await _run_queries(queries, experimental_system, "experimental")

    # 6. Run baseline queries
    baseline_responses = {}
    if dry_run:
        baseline_responses = {q.id: f"[dry-run baseline response for {q.id}]" for q in queries}
    else:
        baseline_responses = await _run_queries(queries, baseline_system, "baseline")

    # 7. Judge all outputs
    query_results = []
    for q in queries:
        b_resp = baseline_responses.get(q.id, "")
        e_resp = experimental_responses.get(q.id, "")

        if dry_run:
            b_score, e_score = 50.0, 60.0
            qr = QueryResult(
                query_id=q.id, query_text=q.query,
                baseline_response=b_resp, experimental_response=e_resp,
                baseline_score=b_score, experimental_score=e_score, delta=10.0,
            )
        else:
            b_result = await evaluate(q.id, q.query, b_resp, q.rubric)
            e_result = await evaluate(q.id, q.query, e_resp, q.rubric)
            delta_info = score_delta(b_result, e_result)
            qr = QueryResult(
                query_id=q.id, query_text=q.query,
                baseline_response=b_resp, experimental_response=e_resp,
                baseline_score=b_result.overall_score, experimental_score=e_result.overall_score,
                delta=delta_info["overall_delta"], criterion_detail=delta_info,
            )

        query_results.append(qr)

    # 8. Aggregate
    baseline_avg = sum(r.baseline_score for r in query_results) / len(query_results) if query_results else 0
    experimental_avg = sum(r.experimental_score for r in query_results) / len(query_results) if query_results else 0
    improved = sum(1 for r in query_results if r.delta > 0)
    degraded = sum(1 for r in query_results if r.delta < 0)
    neutral = sum(1 for r in query_results if r.delta == 0)

    result = ExperimentResult(
        experiment_id=exp_id,
        hypothesis=hyp_dict,
        checkpoint_tag=checkpoint_tag,
        baseline_avg=baseline_avg,
        experimental_avg=experimental_avg,
        overall_delta=experimental_avg - baseline_avg,
        queries_run=len(query_results),
        query_results=query_results,
        improved_count=improved,
        degraded_count=degraded,
        neutral_count=neutral,
    )

    # 9. Log to event store
    try:
        from python.helpers import cortex_event_store as es
        es.log_experiment(
            experiment_id=exp_id,
            hypothesis=hyp_dict,
            baseline_score=baseline_avg,
            experimental_score=experimental_avg,
            applied=False,  # not applied yet — user decides
        )
    except Exception:
        pass

    return result


async def _run_queries(queries: list[TestQuery], system_prompt: str, label: str) -> dict:
    """Run all queries against the given system prompt. Returns {query_id: response}."""
    api_key = os.environ.get("API_KEY_OPENROUTER", "")
    if not api_key:
        return {q.id: f"[no API key — {label}]" for q in queries}

    results = {}
    for q in queries:
        try:
            context = f"\n\nAdditional context: {q.system_context}" if q.system_context else ""
            async with httpx.AsyncClient(timeout=_QUERY_TIMEOUT) as client:
                resp = await client.post(
                    _OR_BASE,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": _EXPERIMENT_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": q.query + context},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 800,
                    },
                )
            if resp.status_code == 200:
                results[q.id] = resp.json()["choices"][0]["message"]["content"].strip()
            else:
                results[q.id] = f"[HTTP {resp.status_code}]"
        except Exception as e:
            results[q.id] = f"[error: {str(e)[:60]}]"

    return results


def _load_system_prompt(target_file: str, target_type: str) -> str:
    """Load the target file content as the system prompt for experiments."""
    try:
        if os.path.exists(target_file):
            with open(target_file, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return "You are CORTEX, an AI business partner and COO."


def _apply_change(original: str, hypothesis: ImprovementHypothesis) -> str:
    """
    Apply a hypothesis change to the system prompt content.
    This is a simplified implementation — appends the proposed change as a new section.
    Real optimization: DSPy or targeted insertion based on section headers.
    """
    addition = (
        f"\n\n## Optimization Applied (Experiment {hypothesis.experiment_id})\n"
        f"Topic: {hypothesis.cluster_topic}\n"
        f"{hypothesis.proposed_change_summary}\n"
        f"Hypothesis: {hypothesis.hypothesis_text}\n"
    )
    return original + addition
