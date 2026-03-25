"""
CORTEX L2 Memory — Zep Cloud graph client.

Uses the official zep-cloud SDK. All episodes are ingested under a single
user_id ('cortex_main') so the knowledge graph accumulates across sessions.

Episode: any text blob → Zep extracts entities and edges asynchronously.
Search: semantic + graph traversal → returns edges/nodes/episodes.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class GraphitiResult:
    entity: str = ""
    relationship: str = ""
    related_entity: str = ""
    timestamp: str = ""
    content: str = ""
    score: float = 0.0


_ZEP_USER_ID = "cortex_main"


class CortexGraphitiClient:

    def __init__(self, api_url: str = "", api_key: str = "", user_id: str = _ZEP_USER_ID):
        # api_url kept for backward compat but Zep SDK uses its own base URL
        self.api_url = api_url
        self.api_key = api_key
        self.user_id = user_id
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from zep_cloud.client import AsyncZep
            self._client = AsyncZep(api_key=self.api_key)
        return self._client

    async def close(self):
        # AsyncZep doesn't need explicit close; kept for interface compat
        self._client = None

    async def health_check(self) -> bool:
        if not self.is_configured():
            return False
        try:
            # Try to reach Zep's API via a lightweight SDK call
            client = self._get_client()
            await client.user.get(self.user_id)
            return True
        except Exception as e:
            # 404 = user not found = API is reachable
            err_str = str(e).lower()
            if "404" in err_str or "not found" in err_str:
                return True
            return False

    async def ensure_user_exists(self) -> bool:
        """Create cortex_main user if not yet created."""
        client = self._get_client()
        try:
            await client.user.get(self.user_id)
            return True
        except Exception:
            pass
        try:
            await client.user.add(
                user_id=self.user_id,
                first_name="CORTEX",
                last_name="Agent",
            )
            return True
        except Exception:
            return False

    async def add_episode(self, text: str, source: str = "cortex", timestamp: Optional[datetime] = None):
        """
        Ingest a text episode into the Zep knowledge graph.
        Zep processes asynchronously — entities and edges appear after ~30–60s.
        """
        if not self.is_configured():
            return
        client = self._get_client()
        await self.ensure_user_exists()
        ts_str = (timestamp or datetime.now()).isoformat()
        await client.graph.add(
            user_id=self.user_id,
            type="text",
            data=text,
        )

    async def search(self, query: str, limit: int = 10) -> list:
        """
        Semantic search over the knowledge graph.
        Returns edges, nodes, and episodes — all cast to GraphitiResult.
        """
        if not self.is_configured():
            return []
        client = self._get_client()
        results = []
        try:
            # Search edges first (entity relationships — the "neurons")
            edge_resp = await client.graph.search(
                user_id=self.user_id,
                query=query,
                limit=limit,
                scope="edges",
            )
            for edge in (edge_resp.edges or []):
                src = getattr(edge, "source_node_name", "") or ""
                tgt = getattr(edge, "target_node_name", "") or ""
                fact = getattr(edge, "fact", "") or getattr(edge, "name", "") or ""
                score = float(getattr(edge, "score", 0.5) or 0.5)
                results.append(GraphitiResult(
                    entity=src,
                    relationship=getattr(edge, "name", ""),
                    related_entity=tgt,
                    content=fact or f"{src} → {tgt}",
                    score=score,
                    timestamp=str(getattr(edge, "created_at", "")),
                ))
        except Exception:
            pass

        try:
            # Also search episodes for recent context
            ep_resp = await client.graph.search(
                user_id=self.user_id,
                query=query,
                limit=max(3, limit // 2),
                scope="episodes",
            )
            for ep in (ep_resp.episodes or []):
                content = getattr(ep, "content", "") or ""
                if content:
                    score = float(getattr(ep, "score", 0.4) or 0.4)
                    results.append(GraphitiResult(
                        content=content[:400],
                        score=score,
                        timestamp=str(getattr(ep, "created_at", "")),
                    ))
        except Exception:
            pass

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def get_entity_history(self, entity: str) -> list:
        results = await self.search(query=entity, limit=20)
        return [
            {
                "fact": r.content,
                "timestamp": r.timestamp,
                "relationship": r.relationship,
            }
            for r in results
        ]

    @staticmethod
    def from_agent_config(agent) -> "CortexGraphitiClient":
        url = getattr(agent.config, "cortex_graphiti_url", "") or ""
        key = getattr(agent.config, "cortex_graphiti_api_key", "") or ""
        return CortexGraphitiClient(api_url=url, api_key=key)
