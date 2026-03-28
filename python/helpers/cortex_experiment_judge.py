"""
cortex_experiment_judge.py — Evaluates LLM outputs against rubric criteria.

Primary judge: DeepSeek V3.2 (cheap, good reasoning, ~$0.001/evaluation)
Spot-check: Claude Sonnet 4.6 (10% of evaluations for calibration)

The judge does NOT know whether it's evaluating baseline or experimental.
It receives: query, rubric criteria, LLM response → scores each criterion independently.
"""

import json
import os
import random
from dataclasses import dataclass, field
from typing import Optional

import httpx

_DEEPSEEK_MODEL = "deepseek/deepseek-chat-v3-0324"
_CLAUDE_MODEL = "anthropic/claude-sonnet-4-6"
_OR_BASE = "https://openrouter.ai/api/v1/chat/completions"
_SPOT_CHECK_RATE = 0.10  # 10% of evaluations cross-checked with Claude


@dataclass
class CriterionScore:
    key: str
    score: int
    max_score: int
    rationale: str

    @property
    def pct(self) -> float:
        return (self.score / self.max_score * 100) if self.max_score else 0


@dataclass
class JudgeResult:
    query_id: str
    overall_score: float  # 0-100
    criterion_scores: list[CriterionScore] = field(default_factory=list)
    judge_model: str = _DEEPSEEK_MODEL
    spot_checked: bool = False
    spot_check_score: Optional[float] = None
    calibration_delta: Optional[float] = None  # spot_check_score - overall_score

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "overall_score": round(self.overall_score, 1),
            "criterion_scores": [
                {"key": c.key, "score": c.score, "max": c.max_score, "pct": round(c.pct, 1), "rationale": c.rationale}
                for c in self.criterion_scores
            ],
            "judge_model": self.judge_model,
            "spot_checked": self.spot_checked,
            "spot_check_score": self.spot_check_score,
            "calibration_delta": self.calibration_delta,
        }


async def evaluate(
    query_id: str,
    query_text: str,
    response_text: str,
    rubric: list,
    force_spot_check: bool = False,
) -> JudgeResult:
    """
    Evaluate a single LLM response against the query rubric.
    rubric: list of RubricCriterion objects from cortex_experiment_suite.
    """
    criterion_scores = await _judge_with_model(
        query_id, query_text, response_text, rubric, _DEEPSEEK_MODEL
    )

    max_total = sum(c.max_score for c in rubric)
    raw_total = sum(cs.score for cs in criterion_scores)
    overall = (raw_total / max_total * 100) if max_total else 0

    result = JudgeResult(
        query_id=query_id,
        overall_score=overall,
        criterion_scores=criterion_scores,
        judge_model=_DEEPSEEK_MODEL,
    )

    # Spot-check with Claude (10% of evals, or forced)
    if force_spot_check or random.random() < _SPOT_CHECK_RATE:
        spot_scores = await _judge_with_model(
            query_id, query_text, response_text, rubric, _CLAUDE_MODEL
        )
        spot_raw = sum(cs.score for cs in spot_scores)
        spot_overall = (spot_raw / max_total * 100) if max_total else 0
        result.spot_checked = True
        result.spot_check_score = round(spot_overall, 1)
        result.calibration_delta = round(spot_overall - overall, 1)

    return result


async def evaluate_batch(
    query_id: str,
    query_text: str,
    responses: dict,
    rubric: list,
) -> dict:
    """
    Evaluate multiple responses for the same query (e.g. baseline + experimental).
    responses: {"baseline": str, "experimental": str}
    Returns: {"baseline": JudgeResult, "experimental": JudgeResult}
    """
    results = {}
    for label, response_text in responses.items():
        results[label] = await evaluate(query_id, query_text, response_text, rubric)
    return results


# ─── INTERNALS ───────────────────────────────────────────────────────────────

async def _judge_with_model(
    query_id: str,
    query_text: str,
    response_text: str,
    rubric: list,
    model: str,
) -> list[CriterionScore]:
    """Call a judge model and parse rubric scores."""
    api_key = os.environ.get("API_KEY_OPENROUTER", "")
    if not api_key:
        return _fallback_scores(rubric)

    criteria_text = "\n".join(
        f'- "{c.key}" (max {c.max_score}): {c.description}'
        for c in rubric
    )

    system = (
        "You are an objective evaluator. You score AI assistant responses against rubric criteria. "
        "You are given a query and a response. Score each criterion independently and honestly. "
        "Do not consider whether the response is fluent or polite — only whether it meets each criterion. "
        "Return ONLY a JSON object."
    )

    user = (
        f"Query: {query_text}\n\n"
        f"Response to evaluate:\n{response_text}\n\n"
        f"Criteria to score:\n{criteria_text}\n\n"
        "For each criterion, return the score (integer, 0 to max_score) and a brief rationale (max 20 words).\n"
        "JSON format:\n"
        '{"scores": [{"key": "criterion_key", "score": N, "rationale": "brief reason"}, ...]}'
    )

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                _OR_BASE,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": 0.1,
                    "max_tokens": 600,
                },
            )
        if resp.status_code != 200:
            return _fallback_scores(rubric)

        raw = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)

        rubric_map = {c.key: c for c in rubric}
        scores = []
        for item in parsed.get("scores", []):
            key = item.get("key", "")
            criterion = rubric_map.get(key)
            if not criterion:
                continue
            raw_score = int(item.get("score", 0))
            scores.append(CriterionScore(
                key=key,
                score=max(0, min(criterion.max_score, raw_score)),
                max_score=criterion.max_score,
                rationale=str(item.get("rationale", ""))[:100],
            ))

        # Fill any missing criteria with 0
        scored_keys = {s.key for s in scores}
        for c in rubric:
            if c.key not in scored_keys:
                scores.append(CriterionScore(key=c.key, score=0, max_score=c.max_score, rationale="not evaluated"))

        return scores

    except Exception:
        return _fallback_scores(rubric)


def _fallback_scores(rubric: list) -> list[CriterionScore]:
    """Return all-zero scores when judge call fails."""
    return [CriterionScore(key=c.key, score=0, max_score=c.max_score, rationale="judge unavailable") for c in rubric]


def score_delta(baseline: JudgeResult, experimental: JudgeResult) -> dict:
    """Compute per-criterion and overall delta (experimental - baseline)."""
    base_map = {cs.key: cs.score for cs in baseline.criterion_scores}
    exp_map = {cs.key: cs.score for cs in experimental.criterion_scores}

    deltas = {}
    for key in set(list(base_map.keys()) + list(exp_map.keys())):
        deltas[key] = exp_map.get(key, 0) - base_map.get(key, 0)

    return {
        "overall_delta": round(experimental.overall_score - baseline.overall_score, 1),
        "criterion_deltas": deltas,
        "improved_criteria": [k for k, d in deltas.items() if d > 0],
        "degraded_criteria": [k for k, d in deltas.items() if d < 0],
        "neutral_criteria": [k for k, d in deltas.items() if d == 0],
    }
