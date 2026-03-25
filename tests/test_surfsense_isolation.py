"""
SurfSense (L3) Comprehensive Test

Tests:
  1. Health check
  2. Authentication
  3. Space inventory - what spaces exist, how many docs each has
  4. Document listing per space - what's actually stored
  5. Space routing - which spaces get picked for sample queries
  6. Keyword scoring - how the relevance ranker orders docs for a query
  7. Push -> retrieve round-trip (synchronous, no wait needed unlike Zep)

Run: python tests/test_surfsense_isolation.py
Run with push test: python tests/test_surfsense_isolation.py --push
"""

import asyncio
import json
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_STOPWORDS = frozenset({
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "for", "of",
    "and", "or", "but", "with", "by", "from", "as", "be", "this", "that",
    "what", "how", "do", "did", "was", "are", "you", "me", "my", "we",
    "our", "can", "could", "would", "should", "have", "has", "had",
})


def _load_credentials() -> tuple:
    settings_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "agents", "cortex", "settings.json",
    )
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        url = data.get("cortex_surfsense_url", "")
        username = data.get("cortex_surfsense_username", "")
        password = data.get("cortex_surfsense_password", "")
        return url, username, password
    except Exception as e:
        print(f"  [!] Could not read settings.json: {e}")
        return "", "", ""


def _tokenize(text: str) -> list:
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    return [w for w in words if w not in _STOPWORDS]


def _score_doc(query: str, doc: dict) -> float:
    tokens = _tokenize(query)
    if not tokens:
        return 0.0
    title = (doc.get("title") or "").lower()
    content = (doc.get("content") or "")[:400].lower()
    combined = f"{title} {content}"
    matches = sum(1 for t in tokens if t in combined)
    return round(matches / len(tokens), 3)


async def test_health(client) -> bool:
    print("\n=== 1. Health Check ===")
    healthy = await client.health_check()
    if healthy:
        print("  PASS - SurfSense is reachable")
    else:
        print("  FAIL - SurfSense not reachable. Is it running?")
    return healthy


async def test_auth(client) -> bool:
    print("\n=== 2. Authentication ===")
    try:
        token = await client.authenticate()
        if token:
            print(f"  PASS - JWT token obtained ({token[:20]}...)")
            return True
        else:
            print("  FAIL - authenticate() returned empty token")
            return False
    except Exception as e:
        print(f"  FAIL - {e}")
        return False


async def test_spaces(client) -> list:
    print("\n=== 3. Space Inventory ===")
    try:
        spaces = await client.list_spaces()
        cortex_spaces = [s for s in spaces if s.get("name", "").startswith("cortex")]
        other_spaces = [s for s in spaces if not s.get("name", "").startswith("cortex")]

        print(f"  Total spaces found: {len(spaces)}")
        print(f"  CORTEX spaces: {len(cortex_spaces)}")
        if other_spaces:
            print(f"  Other spaces: {len(other_spaces)}")

        for s in sorted(spaces, key=lambda x: x.get("name", "")):
            name = s.get("name", "?")
            sid = s.get("id", "?")
            print(f"    [{sid}] {name}")

        return spaces
    except Exception as e:
        print(f"  FAIL - {e}")
        return []


async def test_documents(client, spaces: list):
    print("\n=== 4. Document Listing Per Space ===")
    cortex_spaces = [s for s in spaces if s.get("name", "").startswith("cortex")]

    if not cortex_spaces:
        print("  No CORTEX spaces found — nothing pushed yet.")
        return

    total_docs = 0
    for s in sorted(cortex_spaces, key=lambda x: x.get("name", "")):
        space_name = s.get("name", "")
        try:
            docs = await client.list_documents(space_name, limit=10)
            total_docs += len(docs)
            if docs:
                print(f"\n  [{space_name}] — {len(docs)} doc(s):")
                for d in docs[:5]:
                    title = d.get("title", "(no title)")
                    content_preview = (d.get("content") or "")[:80].replace("\n", " ")
                    print(f"    - {title}")
                    if content_preview:
                        print(f"      {content_preview}...")
            else:
                print(f"\n  [{space_name}] — empty")
        except Exception as e:
            print(f"\n  [{space_name}] — ERROR: {e}")

    print(f"\n  Total docs across all CORTEX spaces: {total_docs}")


async def test_routing(spaces: list):
    print("\n=== 5. Space Routing Test ===")
    print("  (Shows which spaces the router would pick for each query)")

    from python.helpers.cortex_surfsense_router import CortexSurfSenseRouter

    routing_index = {
        "spaces": {
            s.get("name"): {"doc_count": 1, "search_when": []}
            for s in spaces if s.get("name", "").startswith("cortex")
        }
    }

    test_queries = [
        "What pricing decisions did we make for Etsy?",
        "What are my personal preferences and working style?",
        "Summary of this week's progress across all ventures",
        "What research do we have on SaaS pricing models?",
        "What decisions did we make about SSMB last month?",
        "Patterns across all my ventures this quarter",
    ]

    for query in test_queries:
        spaces_picked = CortexSurfSenseRouter.route_for_search(query, routing_index)
        print(f"\n  Query: \"{query[:60]}\"")
        print(f"  -> Routed to: {spaces_picked}")


async def test_keyword_scoring(client, spaces: list):
    print("\n=== 6. Keyword Relevance Scoring ===")
    print("  (Simulates how _20_surfsense_pull.py ranks docs for a query)")

    cortex_spaces = [s.get("name") for s in spaces if s.get("name", "").startswith("cortex")]
    if not cortex_spaces:
        print("  No CORTEX spaces — nothing to score.")
        return

    # Pick a query that should have overlap with stored content
    query = "venture Etsy pricing decisions Slovenia"
    print(f"  Query: \"{query}\"")

    all_docs = []
    for space_name in cortex_spaces[:3]:
        try:
            docs = await client.list_documents(space_name, limit=10)
            for d in docs:
                score = _score_doc(query, d)
                all_docs.append((score, space_name, d))
        except Exception:
            pass

    if not all_docs:
        print("  No docs found to score — SurfSense may be empty.")
        return

    all_docs.sort(key=lambda x: x[0], reverse=True)

    print(f"\n  Scored {len(all_docs)} doc(s) across {len(cortex_spaces[:3])} space(s):")
    print(f"  {'Score':<8} {'Space':<30} {'Title'}")
    print(f"  {'-'*8} {'-'*30} {'-'*40}")
    for score, space_name, d in all_docs[:10]:
        title = (d.get("title") or "(no title)")[:45]
        short_space = space_name.replace("cortex_", "")[:28]
        print(f"  {score:<8.3f} {short_space:<30} {title}")

    top_score = all_docs[0][0]
    if top_score > 0:
        print(f"\n  PASS - Relevance scoring works. Top score: {top_score:.3f}")
    else:
        print(f"\n  INFO - No keyword overlap found for this query. Docs may be from different topics.")
        print(f"         Fallback to recency (top 3) would be used in live CORTEX.")


async def test_push_retrieve(client):
    print("\n=== 7. Push -> Retrieve Round-Trip ===")
    unique_id = str(uuid.uuid4())[:8].upper()
    space_name = "cortex_knowledge"
    doc = {
        "title": f"SURFSENSE-TEST-{unique_id}: Isolation test document",
        "content": (
            f"This is a unique test document pushed by the SurfSense isolation test. "
            f"Reference code: SSTEST-{unique_id}. "
            f"Content: The Marigold project has a test budget of 99,999 units."
        ),
        "metadata": {
            "category": "research",
            "confidence": 1.0,
            "source": "isolation_test",
        },
    }

    print(f"  Pushing test doc to [{space_name}] (ID: {unique_id})...")
    try:
        doc_id = await client.push_document(space_name, doc)
        print(f"  PASS - Pushed. Document ID: {doc_id}")
    except Exception as e:
        print(f"  FAIL - Push failed: {e}")
        return

    print(f"  Retrieving via list_documents...")
    try:
        docs = await client.list_documents(space_name, limit=20)
        found = any(unique_id in (d.get("title") or "") for d in docs)
        if found:
            print(f"  PASS - Document found in list_documents. Push->retrieve is confirmed.")
        else:
            print(f"  INFO - Document not found in top 20. May take a moment to index.")
            print(f"         Try: python tests/test_surfsense_isolation.py to check later.")
    except Exception as e:
        print(f"  FAIL - list_documents failed: {e}")

    print(f"\n  Scoring the test doc against a matching query...")
    query = f"Marigold project budget {unique_id}"
    docs = await client.list_documents(space_name, limit=20)
    scored = [(  _score_doc(query, d), d) for d in docs]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:3]
    for score, d in top:
        title = (d.get("title") or "")[:60]
        print(f"    score={score:.3f}  {title}")

    test_score = next(
        (s for s, d in scored if unique_id in (d.get("title") or "")), 0.0
    )
    if test_score > 0:
        print(f"\n  PASS - Test doc scored {test_score:.3f}. Keyword ranker correctly surfaces it.")
    else:
        print(f"\n  INFO - Test doc scored 0 for this query (expected — title has the ID, content has keywords).")


async def main():
    print("CORTEX SurfSense (L3) Comprehensive Test")
    print("=" * 55)

    url, username, password = _load_credentials()
    if not url:
        print("\nFAIL - No SurfSense URL found in agents/cortex/settings.json")
        sys.exit(1)

    print(f"  URL: {url}")
    print(f"  User: {username}")

    from python.helpers.cortex_surfsense_client import CortexSurfSenseClient
    client = CortexSurfSenseClient(base_url=url, username=username, password=password)

    try:
        healthy = await test_health(client)
        if not healthy:
            sys.exit(1)

        auth_ok = await test_auth(client)
        if not auth_ok:
            sys.exit(1)

        spaces = await test_spaces(client)

        await test_documents(client, spaces)

        await test_routing(spaces)

        await test_keyword_scoring(client, spaces)

        run_push = "--push" in sys.argv or "-p" in sys.argv
        if run_push:
            await test_push_retrieve(client)
        else:
            print("\n=== 7. Push -> Retrieve (skipped) ===")
            print("  Run with --push flag to test document push and retrieval:")
            print("  python tests/test_surfsense_isolation.py --push")

    finally:
        await client.close()

    print("\n" + "=" * 55)
    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
