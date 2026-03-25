import os
from dataclasses import dataclass, field
from typing import Optional


_SONAR_PRO_INPUT_PER_1K = 0.003
_SONAR_PRO_OUTPUT_PER_1K = 0.015
_SONAR_INPUT_PER_1K = 0.001
_SONAR_OUTPUT_PER_1K = 0.001


@dataclass
class PerplexityResult:
    content: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    citations: list = field(default_factory=list)


class PerplexityCapExceededError(Exception):
    pass


class CortexPerplexityClient:

    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
    DEFAULT_MODEL = "perplexity/sonar-pro"

    def __init__(
        self,
        api_key: str = "",
        model: str = DEFAULT_MODEL,
        soft_cap_usd: float = 0.25,
        hard_cap_usd: float = 0.50,
        tier2_only: bool = True,
    ):
        self.api_key = api_key
        self.model = model
        self.soft_cap_usd = soft_cap_usd
        self.hard_cap_usd = hard_cap_usd
        self.tier2_only = tier2_only
        self._run_cost_usd: float = 0.0
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def run_cost(self) -> float:
        return self._run_cost_usd

    def reset_run_cost(self):
        self._run_cost_usd = 0.0

    def soft_cap_warning(self) -> Optional[str]:
        if self._run_cost_usd >= self.soft_cap_usd:
            return (
                f"Perplexity soft cap ${self.soft_cap_usd:.2f} reached "
                f"(current run: ${self._run_cost_usd:.3f})"
            )
        return None

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        if "sonar-pro" in self.model:
            return (
                input_tokens / 1000 * _SONAR_PRO_INPUT_PER_1K
                + output_tokens / 1000 * _SONAR_PRO_OUTPUT_PER_1K
            )
        return (
            input_tokens / 1000 * _SONAR_INPUT_PER_1K
            + output_tokens / 1000 * _SONAR_OUTPUT_PER_1K
        )

    async def query(
        self,
        question: str,
        context: str = "",
        max_tokens: int = 1000,
        tier: str = "Tier2",
    ) -> PerplexityResult:
        if self.tier2_only and tier != "Tier2":
            raise PerplexityCapExceededError(
                "Perplexity is restricted to Tier 2 research only"
            )
        if not self.is_configured():
            raise RuntimeError("Perplexity: API_KEY_OPENROUTER not configured")
        if self._run_cost_usd >= self.hard_cap_usd:
            raise PerplexityCapExceededError(
                f"Perplexity hard cap ${self.hard_cap_usd:.2f} reached "
                f"(current run: ${self._run_cost_usd:.3f})"
            )
        content = question
        if context:
            content = f"Context from prior research:\n{context}\n\nQuestion: {question}"
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://cortex.local",
            "X-Title": "CORTEX Research",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
        }
        resp = await client.post(self.OPENROUTER_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost = self._estimate_cost(input_tokens, output_tokens)
        self._run_cost_usd += cost
        choices = data.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        return PerplexityResult(
            content=text,
            model=data.get("model", self.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            citations=data.get("citations", []),
        )

    @staticmethod
    def from_agent_config(agent) -> "CortexPerplexityClient":
        api_key = (
            getattr(agent.config, "cortex_openrouter_api_key", "")
            or os.getenv("API_KEY_OPENROUTER", "")
        )
        model = (
            getattr(agent.config, "cortex_perplexity_model", "")
            or CortexPerplexityClient.DEFAULT_MODEL
        )
        soft_cap = float(
            getattr(agent.config, "cortex_perplexity_soft_cap", 0) or 0.25
        )
        hard_cap = float(
            getattr(agent.config, "cortex_perplexity_hard_cap", 0) or 0.50
        )
        return CortexPerplexityClient(
            api_key=api_key,
            model=model,
            soft_cap_usd=soft_cap,
            hard_cap_usd=hard_cap,
        )
