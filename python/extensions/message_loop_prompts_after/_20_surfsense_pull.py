from python.helpers.extension import Extension
from agent import LoopData


class CortexSurfSensePull(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        try:
            surfsense_url = getattr(agent.config, "cortex_surfsense_url", "") or ""
            if not surfsense_url:
                return

            query = ""
            if loop_data.user_message:
                query = loop_data.user_message.output_text()
            if not query or not query.strip():
                return

            routing_index = agent.get_data("cortex_space_index") or {}

            from python.helpers.cortex_surfsense_router import CortexSurfSenseRouter
            target_spaces = await CortexSurfSenseRouter.route_for_search_smart(query, agent, routing_index)

            if not target_spaces:
                return

            tier1_context = _build_tier1_context(routing_index, target_spaces)
            if tier1_context and not _needs_deeper_search(query):
                loop_data.extras_persistent["cortex_consciousness"] = (
                    "## CORTEX Consciousness (Tier 1 - Space Summaries)\n" + tier1_context
                )
                return

            from python.helpers.cortex_surfsense_client import CortexSurfSenseClient
            client = CortexSurfSenseClient.from_agent_config(agent)
            if not client:
                return

            try:
                is_healthy = await client.health_check()
                if not is_healthy:
                    return

                # SurfSense semantic search only works for imported documents, not notes.
                # Notes (our primary push format) are discoverable via list endpoint.
                # Strategy: fetch 10 recent docs per space, score by keyword overlap with
                # the query, return top 5 relevant docs across all spaces.
                scored = []
                for space_name in target_spaces[:3]:  # top 3 spaces, scored and merged
                    try:
                        space_docs = await client.list_documents(space_name, limit=10)
                        for d in space_docs:
                            score = _score_doc_relevance(query, d)
                            scored.append((score, space_name, d))
                    except Exception:
                        pass

                if not scored:
                    return

                # Sort by relevance score desc; use recency order (list order) as tiebreaker
                scored.sort(key=lambda x: x[0], reverse=True)
                # If nothing scored above 0 (no keyword overlap), fall back to top 3 by recency
                top_docs = scored[:5] if scored[0][0] > 0 else scored[:3]

                max_tokens = getattr(agent.config, "cortex_pull_max_tokens", 2000) or 2000
                lines = []
                total_chars = 0
                for _score, space_name, d in top_docs:
                    title = d.get("title", "")
                    content_raw = d.get("content", "")
                    content = content_raw if isinstance(content_raw, str) else ""
                    entry = f"### [{space_name}] {title}\n{content[:300]}\n"
                    if total_chars + len(entry) > max_tokens:
                        break
                    lines.append(entry)
                    total_chars += len(entry)

                if lines:
                    loop_data.extras_persistent["cortex_consciousness"] = (
                        "## CORTEX Consciousness (SurfSense L3 — recent docs)\n"
                        + "\n".join(lines)
                    )

            finally:
                await client.close()

        except Exception as e:
            from python.helpers import errors
            agent.context.log.log(
                type="warning",
                heading="CORTEX SurfSense pull failed",
                content=errors.format_error(e),
            )


def _build_tier1_context(routing_index: dict, spaces: list) -> str:
    parts = []
    for space_name in spaces:
        info = routing_index.get("spaces", {}).get(space_name, {})
        doc_count = info.get("doc_count", 0)
        last_updated = info.get("last_updated", "never")
        if doc_count > 0:
            parts.append(f"- {space_name}: {doc_count} docs, last updated {last_updated}")
    return "\n".join(parts) if parts else ""


def _needs_deeper_search(query: str) -> bool:
    q = query.lower()
    shallow_indicators = ["hi", "hello", "thanks", "ok", "yes", "no", "sure"]
    for indicator in shallow_indicators:
        if q.strip() == indicator:
            return False
    return True


_SS_STOPWORDS = frozenset({
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "for", "of",
    "and", "or", "but", "with", "by", "from", "as", "be", "this", "that",
    "what", "how", "do", "did", "was", "are", "you", "me", "my", "we",
    "our", "can", "could", "would", "should", "have", "has", "had",
})


def _tokenize_query(text: str) -> list:
    import re
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    return [w for w in words if w not in _SS_STOPWORDS]


def _score_doc_relevance(query: str, doc: dict) -> float:
    """Score a document by keyword overlap with the query (0.0–1.0)."""
    tokens = _tokenize_query(query)
    if not tokens:
        return 0.0
    title = (doc.get("title") or "").lower()
    content = (doc.get("content") or "")[:400].lower()
    combined = f"{title} {content}"
    matches = sum(1 for tok in tokens if tok in combined)
    return matches / len(tokens)


def _is_deep_dive_request(query: str) -> bool:
    q = query.lower()
    deep_keywords = [
        "deep dive", "analyze document", "check surfsense",
        "look it up in detail", "search everything", "full analysis",
        "research in depth", "what do we have on",
    ]
    return any(kw in q for kw in deep_keywords)


def _format_search_results(results: list, max_chars: int) -> str:
    parts = []
    total_chars = 0
    for r in results:
        entry = f"### [{r.space_name}] {r.title}\n{r.content}\n"
        if total_chars + len(entry) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 100:
                parts.append(entry[:remaining] + "...")
            break
        parts.append(entry)
        total_chars += len(entry)
    return "\n".join(parts) if parts else "No relevant results found."
