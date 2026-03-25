import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class TavilyResult:
    title: str = ""
    url: str = ""
    content: str = ""
    score: float = 0.0
    answer: str = ""


class CortexTavilyClient:

    BASE_URL = "https://api.tavily.com"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        include_answer: bool = True,
        include_domains: Optional[list] = None,
        exclude_domains: Optional[list] = None,
    ) -> list:
        if not self.is_configured():
            return []
        client = await self._get_client()
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": include_answer,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        resp = await client.post(f"{self.BASE_URL}/search", json=payload)
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("answer", "")
        results = []
        for item in data.get("results", []):
            results.append(TavilyResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                score=float(item.get("score", 0.0)),
                answer=answer if not results else "",
            ))
        return results

    async def search_multi(
        self,
        queries: list,
        max_results_per_query: int = 5,
        search_depth: str = "advanced",
    ) -> dict:
        results = {}
        for query in queries:
            try:
                hits = await self.search(
                    query,
                    max_results=max_results_per_query,
                    search_depth=search_depth,
                )
                results[query] = hits
            except Exception:
                results[query] = []
        return results

    @staticmethod
    def from_agent_config(agent) -> "CortexTavilyClient":
        api_key = (
            getattr(agent.config, "cortex_tavily_api_key", "")
            or os.getenv("TAVILY_API_KEY", "")
        )
        return CortexTavilyClient(api_key=api_key)
