import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExaResult:
    id: str = ""
    title: str = ""
    url: str = ""
    content: str = ""
    score: float = 0.0
    author: str = ""
    published_date: str = ""


class CortexExaClient:

    BASE_URL = "https://api.exa.ai"

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

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def search(
        self,
        query: str,
        num_results: int = 5,
        search_type: str = "neural",
        use_autoprompt: bool = True,
        include_text: bool = True,
        text_max_chars: int = 2000,
        start_published_date: Optional[str] = None,
        include_domains: Optional[list] = None,
        exclude_domains: Optional[list] = None,
    ) -> list:
        if not self.is_configured():
            return []
        client = await self._get_client()
        payload = {
            "query": query,
            "numResults": num_results,
            "type": search_type,
            "useAutoprompt": use_autoprompt,
        }
        if include_text:
            payload["contents"] = {"text": {"maxCharacters": text_max_chars}}
        if start_published_date:
            payload["startPublishedDate"] = start_published_date
        if include_domains:
            payload["includeDomains"] = include_domains
        if exclude_domains:
            payload["excludeDomains"] = exclude_domains
        resp = await client.post(
            f"{self.BASE_URL}/search",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", []):
            content = ""
            text_field = item.get("text")
            if isinstance(text_field, str):
                content = text_field
            results.append(ExaResult(
                id=item.get("id", ""),
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=content,
                score=float(item.get("score", 0.0)),
                author=item.get("author", ""),
                published_date=item.get("publishedDate", ""),
            ))
        return results

    async def search_multi(
        self,
        queries: list,
        num_results_per_query: int = 5,
        search_type: str = "neural",
    ) -> dict:
        results = {}
        for query in queries:
            try:
                hits = await self.search(
                    query,
                    num_results=num_results_per_query,
                    search_type=search_type,
                )
                results[query] = hits
            except Exception:
                results[query] = []
        return results

    async def find_similar(
        self,
        url: str,
        num_results: int = 5,
        include_text: bool = True,
    ) -> list:
        if not self.is_configured():
            return []
        client = await self._get_client()
        payload = {
            "url": url,
            "numResults": num_results,
        }
        if include_text:
            payload["contents"] = {"text": True}
        resp = await client.post(
            f"{self.BASE_URL}/findSimilar",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", []):
            content = ""
            text_field = item.get("text")
            if isinstance(text_field, str):
                content = text_field
            results.append(ExaResult(
                id=item.get("id", ""),
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=content,
                score=float(item.get("score", 0.0)),
                author=item.get("author", ""),
                published_date=item.get("publishedDate", ""),
            ))
        return results

    @staticmethod
    def from_agent_config(agent) -> "CortexExaClient":
        api_key = (
            getattr(agent.config, "cortex_exa_api_key", "")
            or os.getenv("EXA_API_KEY", "")
        )
        return CortexExaClient(api_key=api_key)
