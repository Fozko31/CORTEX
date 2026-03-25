import asyncio
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FirecrawlResult:
    url: str = ""
    markdown: str = ""
    title: str = ""
    description: str = ""
    metadata: dict = field(default_factory=dict)
    success: bool = False


class CortexFirecrawlClient:

    BASE_URL = "https://api.firecrawl.dev/v1"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def scrape(
        self,
        url: str,
        formats: Optional[list] = None,
    ) -> FirecrawlResult:
        if not self.is_configured():
            return FirecrawlResult(url=url)
        client = await self._get_client()
        payload = {
            "url": url,
            "formats": formats or ["markdown"],
        }
        resp = await client.post(
            f"{self.BASE_URL}/scrape",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        inner = data.get("data", {})
        meta = inner.get("metadata", {})
        return FirecrawlResult(
            url=url,
            markdown=inner.get("markdown", ""),
            title=meta.get("title", ""),
            description=meta.get("description", ""),
            metadata=meta,
            success=data.get("success", False),
        )

    async def extract(
        self,
        urls: list,
        prompt: str = "",
        schema: Optional[dict] = None,
    ) -> dict:
        if not self.is_configured():
            return {}
        client = await self._get_client()
        payload: dict = {"urls": urls}
        if prompt:
            payload["prompt"] = prompt
        if schema:
            payload["schema"] = schema
        resp = await client.post(
            f"{self.BASE_URL}/extract",
            headers=self._headers(),
            json=payload,
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def crawl(
        self,
        url: str,
        max_pages: int = 5,
        formats: Optional[list] = None,
    ) -> list:
        if not self.is_configured():
            return []
        client = await self._get_client()
        payload = {
            "url": url,
            "limit": max_pages,
            "scrapeOptions": {"formats": formats or ["markdown"]},
        }
        resp = await client.post(
            f"{self.BASE_URL}/crawl",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        job_id = data.get("id", "")
        if not job_id:
            return []
        return await self._poll_crawl(job_id)

    async def _poll_crawl(self, job_id: str, max_wait: int = 120) -> list:
        client = await self._get_client()
        waited = 0
        while waited < max_wait:
            await asyncio.sleep(3)
            waited += 3
            resp = await client.get(
                f"{self.BASE_URL}/crawl/{job_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")
            if status == "completed":
                results = []
                for item in data.get("data", []):
                    meta = item.get("metadata", {})
                    results.append(FirecrawlResult(
                        url=item.get("url", ""),
                        markdown=item.get("markdown", ""),
                        title=meta.get("title", ""),
                        description=meta.get("description", ""),
                        metadata=meta,
                        success=True,
                    ))
                return results
            if status in ("failed", "cancelled"):
                return []
        return []

    @staticmethod
    def from_agent_config(agent) -> "CortexFirecrawlClient":
        api_key = (
            getattr(agent.config, "cortex_firecrawl_api_key", "")
            or os.getenv("FIRECRAWL_API_KEY", "")
        )
        return CortexFirecrawlClient(api_key=api_key)
