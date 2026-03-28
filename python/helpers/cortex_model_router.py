import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional
from python.cortex.memory import get_agent_memory_subdir, abs_db_dir


@dataclass
class ModelSpec:
    slug: str
    provider: str
    input_cost_per_m: float
    output_cost_per_m: float
    fallback_slug: Optional[str] = None
    fallback_provider: Optional[str] = None


TASK_MODELS = {
    "extraction": ModelSpec(
        slug="google/gemini-3.1-flash-lite-preview",
        provider="openrouter",
        input_cost_per_m=0.25,
        output_cost_per_m=1.50,
        fallback_slug="google/gemini-3-flash-preview",
        fallback_provider="openrouter",
    ),
    "classification": ModelSpec(
        slug="deepseek/deepseek-v3.2",
        provider="openrouter",
        input_cost_per_m=0.26,
        output_cost_per_m=0.38,
        fallback_slug="qwen/qwen3.5-flash-02-23",
        fallback_provider="openrouter",
    ),
    "summarization": ModelSpec(
        # DeepSeek V3.2: ~10x cheaper than Sonnet, sufficient for session summaries.
        # Claude Sonnet stays for user-facing synthesis (research final step) — never routed here.
        slug="deepseek/deepseek-v3.2",
        provider="openrouter",
        input_cost_per_m=0.26,
        output_cost_per_m=0.38,
        fallback_slug="google/gemini-3.1-flash-lite-preview",
        fallback_provider="openrouter",
    ),
    "digest": ModelSpec(
        # Weekly digest / consolidation — DeepSeek handles structured summarization well.
        slug="deepseek/deepseek-v3.2",
        provider="openrouter",
        input_cost_per_m=0.26,
        output_cost_per_m=0.38,
        fallback_slug="google/gemini-3.1-flash-lite-preview",
        fallback_provider="openrouter",
    ),
}


class CortexModelRouter:

    @staticmethod
    def get_model_for_task(task: str) -> ModelSpec:
        return TASK_MODELS.get(task, TASK_MODELS["extraction"])

    @staticmethod
    async def call_routed_model(task: str, system: str, message: str, agent) -> str:
        spec = CortexModelRouter.get_model_for_task(task)

        if task in ("extraction",):
            try:
                response = await agent.call_utility_model(
                    system=system, message=message, background=True
                )
                CortexModelRouter.track_usage(agent, task, len(message) // 4, len(response) // 4, spec)
                return response
            except Exception:
                pass

        if task == "summarization":
            try:
                response = await agent.call_utility_model(
                    system=system, message=message, background=True
                )
                CortexModelRouter.track_usage(agent, task, len(message) // 4, len(response) // 4, spec)
                return response
            except Exception:
                pass

        try:
            response = await CortexModelRouter._call_direct(spec, system, message, agent)
            CortexModelRouter.track_usage(agent, task, len(message) // 4, len(response) // 4, spec)
            return response
        except Exception:
            if spec.fallback_slug:
                fallback = ModelSpec(
                    slug=spec.fallback_slug,
                    provider=spec.fallback_provider or spec.provider,
                    input_cost_per_m=spec.input_cost_per_m,
                    output_cost_per_m=spec.output_cost_per_m,
                )
                response = await CortexModelRouter._call_direct(fallback, system, message, agent)
                CortexModelRouter.track_usage(agent, task, len(message) // 4, len(response) // 4, fallback)
                return response
            raise

    @staticmethod
    async def _call_direct(spec: ModelSpec, system: str, message: str, agent) -> str:
        from litellm import acompletion

        api_key = os.environ.get("API_KEY_OPENROUTER") or os.environ.get("OPENROUTER_API_KEY", "")
        model_name = f"openrouter/{spec.slug}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ]
        response = await acompletion(
            model=model_name,
            messages=messages,
            api_key=api_key,
            extra_headers={
                "HTTP-Referer": "https://agent-zero.ai/",
                "X-Title": "CORTEX",
            },
            timeout=60,
        )
        return response.choices[0].message.content or ""

    @staticmethod
    def track_usage(agent, task: str, input_tokens: int, output_tokens: int, spec: ModelSpec):
        try:
            cost = (input_tokens * spec.input_cost_per_m + output_tokens * spec.output_cost_per_m) / 1_000_000
            log_path = CortexModelRouter._cost_log_path(agent)
            log_data = CortexModelRouter._load_cost_log(log_path)

            today = date.today().isoformat()
            if today not in log_data:
                log_data[today] = {"total_cost": 0.0, "calls": []}

            log_data[today]["calls"].append({
                "task": task,
                "model": spec.slug,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": round(cost, 6),
                "timestamp": datetime.now().isoformat(),
            })
            log_data[today]["total_cost"] = round(
                log_data[today]["total_cost"] + cost, 6
            )

            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def get_daily_cost(agent) -> float:
        try:
            log_path = CortexModelRouter._cost_log_path(agent)
            log_data = CortexModelRouter._load_cost_log(log_path)
            today = date.today().isoformat()
            return log_data.get(today, {}).get("total_cost", 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def is_within_budget(agent) -> bool:
        limit = getattr(agent.config, "cortex_daily_cost_limit", 5.0) or 5.0
        return CortexModelRouter.get_daily_cost(agent) < limit

    @staticmethod
    def _cost_log_path(agent) -> str:
        base = abs_db_dir(get_agent_memory_subdir(agent))
        return os.path.join(base, "cortex_cost_log.json")

    @staticmethod
    def _load_cost_log(path: str) -> dict:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
