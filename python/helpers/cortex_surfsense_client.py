import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional
from python.helpers.memory import get_agent_memory_subdir, abs_db_dir


@dataclass
class SearchResult:
    document_id: str = ""
    space_name: str = ""
    title: str = ""
    content: str = ""
    score: float = 0.0
    metadata: dict = field(default_factory=dict)


class CortexSurfSenseClient:

    def __init__(self, base_url: str, username: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._token: Optional[str] = None
        self._token_ts: float = 0
        self._space_cache: dict = {}
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def authenticate(self) -> str:
        if self._token and (time.time() - self._token_ts) < 3500:
            return self._token
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/auth/jwt/login",
            data={"username": self.username, "password": self.password},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get("access_token", "")
        self._token_ts = time.time()
        return self._token

    async def _headers(self) -> dict:
        token = await self.authenticate()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get(f"{self.base_url}/health", timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def list_spaces(self) -> list:
        client = await self._get_client()
        headers = await self._headers()
        resp = await client.get(f"{self.base_url}/api/v1/searchspaces", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def create_space(self, name: str, description: str = "") -> dict:
        client = await self._get_client()
        headers = await self._headers()
        resp = await client.post(
            f"{self.base_url}/api/v1/searchspaces",
            headers=headers,
            json={"name": name, "description": description or f"CORTEX space: {name}"},
        )
        if resp.status_code == 409:
            # Space already exists — idempotent: return the existing space
            spaces = await self.list_spaces()
            for s in spaces:
                if s.get("name") == name:
                    return s
            return {"name": name}  # fallback if list fails
        resp.raise_for_status()
        return resp.json()

    async def get_space_id(self, space_name: str) -> Optional[int]:
        if space_name in self._space_cache:
            return self._space_cache[space_name]
        spaces = await self.list_spaces()
        for s in spaces:
            sname = s.get("name", "")
            sid = s.get("id")
            self._space_cache[sname] = sid
            if sname == space_name:
                return sid
        return None

    async def ensure_spaces_exist(self, space_names: list) -> dict:
        existing = await self.list_spaces()
        existing_names = {s.get("name", "") for s in existing}
        for s in existing:
            self._space_cache[s.get("name", "")] = s.get("id")

        created = {}
        for name in space_names:
            if name not in existing_names:
                try:
                    result = await self.create_space(name)
                    sid = result.get("id")
                    self._space_cache[name] = sid
                    created[name] = sid
                    await asyncio.sleep(1.5)
                except Exception:
                    pass
        return created

    async def push_document(self, space_name: str, document: dict) -> str:
        space_id = await self.get_space_id(space_name)
        if space_id is None:
            await self.ensure_spaces_exist([space_name])
            space_id = await self.get_space_id(space_name)
            if space_id is None:
                raise ValueError(f"Could not find or create space: {space_name}")

        client = await self._get_client()
        headers = await self._headers()

        meta = document.get("metadata", {})
        metadata_header = _build_metadata_header(meta)
        full_content = f"{metadata_header}\n\n{document.get('content', '')}"

        payload = {
            "title": document.get("title", "untitled"),
            "source_markdown": full_content,
        }

        for attempt in range(3):
            try:
                resp = await client.post(
                    f"{self.base_url}/api/v1/search-spaces/{space_id}/notes",
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
                return str(data.get("id", ""))
            except Exception as e:
                if attempt < 2 and _is_retryable(e):
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

    async def search(
        self,
        query: str,
        space_names: list,
        limit: int = 5,
    ) -> list:
        results = []
        for space_name in space_names:
            space_id = await self.get_space_id(space_name)
            if space_id is None:
                continue
            try:
                hits = await self._search_space(query, space_id, space_name, limit)
                results.extend(hits)
            except Exception:
                pass

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def _search_space(
        self, query: str, space_id: int, space_name: str, limit: int
    ) -> list:
        """
        Search a space using SurfSense's title-search endpoint.
        SurfSense does not expose a semantic/vector search API — its semantic
        search is internal to its chat UI only. We use the title ILIKE endpoint
        with the first meaningful word(s) of the query. For semantic recall use
        L1 (FAISS) or L2 (Graphiti) — those are the right layers for that.
        """
        client = await self._get_client()
        headers = await self._headers()

        # Extract best search term from query (first 3 non-stopword tokens)
        search_term = _extract_search_term(query)
        if not search_term:
            return []

        resp = await client.get(
            f"{self.base_url}/api/v1/documents/search",
            headers=headers,
            params={
                "title": search_term,
                "search_space_id": space_id,
                "page_size": limit,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        results = []
        for item in items[:limit]:
            content_raw = item.get("content", "")
            content_str = content_raw if isinstance(content_raw, str) else json.dumps(content_raw)
            results.append(SearchResult(
                document_id=str(item.get("id", "")),
                space_name=space_name,
                title=item.get("title", ""),
                content=content_str[:2000],
                score=0.6,  # title match — moderate confidence
                metadata=item.get("document_metadata", {}),
            ))
        return results

    async def list_documents(self, space_name: str, limit: int = 20) -> list:
        space_id = await self.get_space_id(space_name)
        if space_id is None:
            return []
        client = await self._get_client()
        headers = await self._headers()
        resp = await client.get(
            f"{self.base_url}/api/v1/documents",
            headers=headers,
            params={"search_space_id": space_id, "page_size": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", []) if isinstance(data, dict) else data

    @staticmethod
    def from_agent_config(agent) -> Optional["CortexSurfSenseClient"]:
        url = getattr(agent.config, "cortex_surfsense_url", "") or ""
        if not url:
            return None
        username = getattr(agent.config, "cortex_surfsense_username", "") or ""
        password = getattr(agent.config, "cortex_surfsense_password", "") or ""
        return CortexSurfSenseClient(base_url=url, username=username, password=password)

    @staticmethod
    def queue_path(agent) -> str:
        base = abs_db_dir(get_agent_memory_subdir(agent))
        return os.path.join(base, "cortex_push_queue.json")

    @staticmethod
    def load_queue(agent) -> list:
        path = CortexSurfSenseClient.queue_path(agent)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    @staticmethod
    def save_queue(agent, queue: list):
        path = CortexSurfSenseClient.queue_path(agent)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(queue, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def enqueue(agent, space_name: str, document: dict):
        queue = CortexSurfSenseClient.load_queue(agent)
        queue.append({"space_name": space_name, "document": document})
        CortexSurfSenseClient.save_queue(agent, queue)

    async def drain_queue(self, agent):
        queue = CortexSurfSenseClient.load_queue(agent)
        if not queue:
            return
        remaining = []
        for item in queue:
            try:
                await self.push_document(item["space_name"], item["document"])
            except Exception:
                remaining.append(item)
        CortexSurfSenseClient.save_queue(agent, remaining)


_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "to", "of", "in",
    "on", "at", "by", "for", "with", "about", "from", "as", "into",
    "what", "how", "when", "where", "why", "who", "which", "that", "this",
    "i", "we", "you", "it", "they", "me", "us", "him", "her", "them",
    "my", "our", "your", "its", "their", "and", "or", "but", "not",
    "hi", "hello", "ok", "okay", "yes", "no", "please", "thanks",
})


def _extract_search_term(query: str, max_words: int = 3) -> str:
    """Extract the most meaningful words from a query for title search."""
    words = query.lower().split()
    meaningful = [w.strip(".,!?;:\"'") for w in words if w.strip(".,!?;:\"'") not in _STOPWORDS and len(w) > 2]
    if not meaningful:
        # Fall back to first non-trivial word
        meaningful = [w for w in words if len(w) > 2]
    return " ".join(meaningful[:max_words]) if meaningful else ""


def _build_metadata_header(meta: dict) -> str:
    parts = ["---"]

    category = meta.get("category", "research")
    parts.append(f"category: {category}")

    confidence = meta.get("confidence", 0.8)
    parts.append(f"confidence: {confidence:.2f}")

    venture = meta.get("venture")
    if venture:
        parts.append(f"venture: {venture}")

    summary_level = meta.get("summary_level", "extracted")
    parts.append(f"summary_level: {summary_level}")

    tags = meta.get("tags", [])
    if tags:
        parts.append(f"tags: {', '.join(tags)}")

    session_id = meta.get("session_id")
    if session_id:
        parts.append(f"session: {session_id}")

    source = meta.get("source", "cortex_extraction")
    parts.append(f"source: {source}")

    temporal = meta.get("temporal")
    if temporal:
        parts.append(f"created: {temporal[:10]}")

    parts.append("---")
    return "\n".join(parts)


def parse_metadata_header(text: str) -> dict:
    meta = {}
    if not text or "---" not in text:
        return meta
    try:
        lines = text.split("\n")
        in_header = False
        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                if not in_header:
                    in_header = True
                    continue
                else:
                    break
            if in_header and ":" in stripped:
                key, _, value = stripped.partition(":")
                meta[key.strip()] = value.strip()
    except Exception:
        pass
    return meta


def _is_retryable(exc) -> bool:
    try:
        import httpx
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500
    except Exception:
        pass
    return False
