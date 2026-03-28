"""
CORTEX Signal Ingestion — Phase D, D-2
========================================

Collects raw pain signals from multiple sources:
  - Reddit (PRAW — free, rate-limited)
  - ProductHunt (GraphQL API — free)
  - G2 / Capterra / App Store reviews (Exa + Firecrawl — already have)
  - Twitter/X search (Exa — already have)

All sources return List[PainSignal]. Normalized format before entering gate pipeline.
Cost-first: free sources first, upgrade paths noted.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from python.helpers.cortex_discovery_params import PainSignal, append_signals


# ─────────────────────────────────────────────────────────────────────────────
# Reddit Source (PRAW)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_reddit_signals(
    niche: str,
    subreddits: Optional[List[str]] = None,
    limit: int = 25,
) -> List[PainSignal]:
    """
    Search Reddit for pain signals related to niche.
    Uses PRAW (free, rate-limited). Falls back to Exa if PRAW not configured.
    Returns PainSignal list with paying_evidence=True when complaint mentions payment.
    """
    client_id = os.getenv("REDDIT_CLIENT_ID", "")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
    user_agent = os.getenv("REDDIT_USER_AGENT", "CORTEX Discovery Bot 1.0")

    if client_id and client_secret:
        return await _reddit_via_praw(niche, subreddits, limit, client_id, client_secret, user_agent)
    else:
        # Fallback: use Exa to search Reddit content
        return await _reddit_via_exa(niche, limit)


async def _reddit_via_praw(
    niche: str,
    subreddits: Optional[List[str]],
    limit: int,
    client_id: str,
    client_secret: str,
    user_agent: str,
) -> List[PainSignal]:
    try:
        import praw  # type: ignore

        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

        pain_keywords = [
            "wish", "missing", "can't", "cannot", "doesn't have", "needs",
            "frustrated", "annoying", "terrible", "broken", "hate", "switching",
            "alternative", "replace", "looking for", "pays for", "subscribed",
        ]

        signals: List[PainSignal] = []

        # Determine search targets
        if subreddits:
            sub = reddit.subreddit("+".join(subreddits))
        else:
            sub = reddit.subreddit("all")

        # Search for complaints/pain
        query = f"{niche} (problem OR issue OR alternative OR missing OR wish OR hate)"

        for post in sub.search(query, sort="relevance", limit=limit):
            text = (post.title + " " + (post.selftext or ""))[:1000]
            text_lower = text.lower()

            # Only include if pain keywords present
            if not any(kw in text_lower for kw in pain_keywords):
                continue

            # Check paying evidence
            paying = any(kw in text_lower for kw in [
                "pay", "paid", "subscription", "plan", "pricing", "per month",
                "per year", "license", "cost", "fee", "invoice",
            ])

            signals.append(PainSignal(
                source="reddit",
                source_url=f"https://reddit.com{post.permalink}",
                raw_text=text[:500],
                extracted_pain=post.title[:200],
                paying_evidence=paying,
                strength=1,
            ))

        return signals

    except ImportError:
        print("[CORTEX signal_ingestion] praw not installed — falling back to Exa")
        return await _reddit_via_exa(niche, limit)
    except Exception as e:
        print(f"[CORTEX signal_ingestion] Reddit PRAW error: {e}")
        return await _reddit_via_exa(niche, limit)


async def _reddit_via_exa(niche: str, limit: int = 10) -> List[PainSignal]:
    """Exa fallback for Reddit pain mining (no PRAW credentials)."""
    try:
        exa_key = os.getenv("EXA_API_KEY", "")
        if not exa_key:
            return []

        from python.helpers.cortex_exa_client import CortexExaClient
        exa = CortexExaClient(api_key=exa_key)

        results = await exa.search(
            f"site:reddit.com {niche} problem OR issue OR alternative OR missing OR wish",
            num_results=min(limit, 10),
        )

        signals = []
        for r in results:
            text = (r.title + " " + r.text[:500]) if hasattr(r, "text") else r.title
            paying = any(kw in text.lower() for kw in ["pay", "paid", "subscription", "per month"])
            signals.append(PainSignal(
                source="reddit",
                source_url=r.url,
                raw_text=text[:500],
                extracted_pain=r.title[:200],
                paying_evidence=paying,
                strength=1,
            ))

        return signals
    except Exception as e:
        print(f"[CORTEX signal_ingestion] Reddit Exa fallback error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# ProductHunt Source (free GraphQL API)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_producthunt_signals(niche: str, limit: int = 10) -> List[PainSignal]:
    """
    Search ProductHunt for products in niche, extract pain signals from comments.
    Uses ProductHunt GraphQL API (free, requires API key in PRODUCTHUNT_API_KEY).
    Falls back to Exa search of producthunt.com if no API key.
    """
    ph_token = os.getenv("PRODUCTHUNT_API_KEY", "")
    if ph_token:
        return await _producthunt_via_api(niche, limit, ph_token)
    else:
        return await _producthunt_via_exa(niche, limit)


async def _producthunt_via_api(niche: str, limit: int, token: str) -> List[PainSignal]:
    """Direct ProductHunt GraphQL API call."""
    try:
        import aiohttp
        query = """
        query SearchPosts($query: String!, $first: Int!) {
          posts(query: $query, first: $first, order: VOTES) {
            edges {
              node {
                id
                name
                tagline
                description
                url
                commentsCount
                votesCount
              }
            }
          }
        }
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.producthunt.com/v2/api/graphql",
                json={"query": query, "variables": {"query": niche, "first": limit}},
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()

        signals = []
        posts = data.get("data", {}).get("posts", {}).get("edges", [])
        for edge in posts:
            node = edge.get("node", {})
            desc = node.get("description", "") or node.get("tagline", "")
            name = node.get("name", "")
            url = node.get("url", "")
            # Pain signal: product exists = someone had the pain
            signals.append(PainSignal(
                source="producthunt",
                source_url=url,
                raw_text=f"{name}: {desc}"[:500],
                extracted_pain=f"Market has product '{name}': {node.get('tagline', '')}",
                paying_evidence=False,
                strength=2 if node.get("votesCount", 0) > 100 else 1,
            ))

        return signals
    except Exception as e:
        print(f"[CORTEX signal_ingestion] ProductHunt API error: {e}")
        return await _producthunt_via_exa(niche, limit)


async def _producthunt_via_exa(niche: str, limit: int = 5) -> List[PainSignal]:
    """Exa fallback for ProductHunt."""
    try:
        exa_key = os.getenv("EXA_API_KEY", "")
        if not exa_key:
            return []

        from python.helpers.cortex_exa_client import CortexExaClient
        exa = CortexExaClient(api_key=exa_key)

        results = await exa.search(
            f"site:producthunt.com {niche}",
            num_results=min(limit, 5),
        )

        return [
            PainSignal(
                source="producthunt",
                source_url=r.url,
                raw_text=r.title[:300],
                extracted_pain=r.title[:200],
                paying_evidence=False,
                strength=1,
            )
            for r in results
        ]
    except Exception as e:
        print(f"[CORTEX signal_ingestion] ProductHunt Exa fallback error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# G2 / Capterra / App Store Reviews (Exa + Firecrawl)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_review_signals(
    niche: str,
    tool_name: Optional[str] = None,
    limit: int = 8,
) -> List[PainSignal]:
    """
    Fetch negative/mixed reviews from G2, Capterra, and App Store via Exa search.
    If tool_name is provided, searches reviews for that specific tool.
    Paying evidence = always True (reviewers are product users/customers).
    """
    try:
        exa_key = os.getenv("EXA_API_KEY", "")
        if not exa_key:
            return []

        from python.helpers.cortex_exa_client import CortexExaClient
        exa = CortexExaClient(api_key=exa_key)

        target = tool_name if tool_name else niche
        # Search review platforms for negative/mixed reviews
        results = await exa.search(
            f'site:g2.com OR site:capterra.com "{target}" "cons" OR "missing" OR "wish" OR "limitation"',
            num_results=min(limit, 8),
        )

        signals = []
        for r in results:
            text = r.title[:400]
            signals.append(PainSignal(
                source="g2" if "g2.com" in r.url else "capterra",
                source_url=r.url,
                raw_text=text,
                extracted_pain=f"Review complaint for '{target}': {text[:150]}",
                tool_mentioned=tool_name,
                paying_evidence=True,   # G2/Capterra reviewers are verified users
                strength=2,             # Reviews carry more weight than forum posts
            ))

        return signals
    except Exception as e:
        print(f"[CORTEX signal_ingestion] Review signals error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# "X Alternative" Search (switching intent signal)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_alternative_signals(
    tool_name: str,
    limit: int = 5,
) -> List[PainSignal]:
    """
    Search for '[tool] alternative' — this is active switching intent.
    A user searching for alternatives has already decided to leave. Strongest signal.
    """
    try:
        exa_key = os.getenv("EXA_API_KEY", "")
        if not exa_key:
            return []

        from python.helpers.cortex_exa_client import CortexExaClient
        exa = CortexExaClient(api_key=exa_key)

        results = await exa.search(
            f'"{tool_name} alternative" OR "switch from {tool_name}" OR "replace {tool_name}"',
            num_results=min(limit, 5),
        )

        return [
            PainSignal(
                source="twitter" if "twitter.com" in r.url or "x.com" in r.url else "web",
                source_url=r.url,
                raw_text=r.title[:300],
                extracted_pain=f"Active switching intent from '{tool_name}': {r.title[:150]}",
                tool_mentioned=tool_name,
                paying_evidence=True,   # Users searching alternatives are usually current (paying) users
                strength=3,             # Switching intent = strong signal
            )
            for r in results
        ]
    except Exception as e:
        print(f"[CORTEX signal_ingestion] Alternative signals error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Aggregated Source Run
# ─────────────────────────────────────────────────────────────────────────────

async def collect_all_signals(
    niche: str,
    market: str = "global",
    tool_name: Optional[str] = None,
    max_per_source: int = 8,
) -> List[PainSignal]:
    """
    Run all signal sources concurrently for a niche. Returns merged, deduped list.
    Persists signals to disk for temporal tracking.
    """
    tasks = [
        fetch_reddit_signals(niche, limit=max_per_source),
        fetch_producthunt_signals(niche, limit=max_per_source // 2),
        fetch_review_signals(niche, tool_name=tool_name, limit=max_per_source),
    ]

    if tool_name:
        tasks.append(fetch_alternative_signals(tool_name, limit=5))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_signals: List[PainSignal] = []
    for r in results:
        if isinstance(r, Exception):
            print(f"[CORTEX signal_ingestion] Source error (continuing): {r}")
        elif isinstance(r, list):
            all_signals.extend(r)

    # Persist and dedup
    merged = append_signals(niche, all_signals)

    # Count paying evidence
    paying_count = sum(1 for s in merged if s.paying_evidence)
    print(
        f"[CORTEX signal_ingestion] {niche}: {len(all_signals)} new signals "
        f"({paying_count} paying evidence) | {len(merged)} total stored"
    )

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Pain Extraction (LLM cleanup for raw signal text)
# ─────────────────────────────────────────────────────────────────────────────

async def extract_structured_pain(
    raw_signals: List[PainSignal],
    niche: str,
    agent=None,
) -> List[PainSignal]:
    """
    Run raw signals through DeepSeek to produce clean, structured pain statements.
    Upgrades paying_evidence flag if LLM detects payment mentions.
    Batched to keep cost low: one call per 10 signals.
    Cost: ~€0.001 per batch of 10.
    """
    if not raw_signals:
        return []

    from python.helpers.cortex_model_router import CortexModelRouter
    from python.cortex.dirty_json import DirtyJson

    BATCH = 10
    enriched: List[PainSignal] = []

    for i in range(0, len(raw_signals), BATCH):
        batch = raw_signals[i:i + BATCH]
        numbered = "\n".join(
            f"{j+1}. [{s.source}] {s.raw_text[:200]}"
            for j, s in enumerate(batch)
        )

        prompt = (
            f"Niche: '{niche}'\n\n"
            f"Raw signals:\n{numbered}\n\n"
            "For each signal, extract (JSON array):\n"
            "[\n"
            '  {"index": 1, "pain": "clean 1-sentence pain statement", '
            '"paying_evidence": true/false, "tool_mentioned": "tool name or null"}\n'
            "]\n"
            "paying_evidence=true only if signal mentions payment, subscription, or being a current customer."
        )

        try:
            raw = await CortexModelRouter.call_routed_model(
                "classification",
                "You are a pain signal analyst. Extract clean, specific pain statements. JSON array only.",
                prompt,
                agent,
            )
            parsed = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw
            if not isinstance(parsed, list):
                parsed = []

            for item in parsed:
                idx = int(item.get("index", 0)) - 1
                if 0 <= idx < len(batch):
                    batch[idx].extracted_pain = item.get("pain", batch[idx].extracted_pain)
                    if item.get("paying_evidence"):
                        batch[idx].paying_evidence = True
                    if item.get("tool_mentioned"):
                        batch[idx].tool_mentioned = item["tool_mentioned"]

        except Exception as e:
            print(f"[CORTEX signal_ingestion] Pain extraction error (batch {i}): {e}")

        enriched.extend(batch)

    return enriched
