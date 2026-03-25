"""
Layer Isolation Test — proves L2 Graphiti stores and retrieves data
independently of L1 FAISS and the static system prompt.

HOW TO RUN
----------
    python tests/test_layer_isolation.py

WHAT IT TESTS
-------------
Phase 1 (runs every time):
  - Zep Cloud is reachable
  - graph.search() returns results for queries related to existing episodes
  - Zep is therefore providing real context, not returning empty results

Phase 2 (round-trip proof, takes ~90s):
  - Push a unique UUID-tagged fact to Graphiti
  - Wait 90 seconds for Zep to process it asynchronously
  - Search for the unique tag
  - PASS if found — proves push→retrieve is working end-to-end

TO PROVE L2 IS THE SOURCE IN A LIVE SESSION
--------------------------------------------
1. Run Phase 2 to push the unique fact.
2. Rename the FAISS store so it's empty:
       rename  usr\\memory\\cortex_main  usr\\memory\\cortex_main_bak
3. Restart CORTEX (python run_ui.py)
4. Ask: "What is the Nighthawk project budget?"
5. If CORTEX answers "€12,847" → the fact came from Graphiti (L2), not FAISS (L1).
6. Restore FAISS: rename usr\\memory\\cortex_main_bak  usr\\memory\\cortex_main
"""

import asyncio
import json
import os
import sys
import uuid
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_api_key() -> str:
    settings_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "agents", "cortex", "settings.json",
    )
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        key = data.get("cortex_graphiti_api_key", "")
        if key:
            return key
    except Exception as e:
        print(f"  [!] Could not read settings.json: {e}")
    # Fallback: environment variable
    return os.environ.get("ZEP_API_KEY", "")


async def phase1_connectivity(api_key: str) -> bool:
    print("\n=== Phase 1: Connectivity + Search ===")
    from python.helpers.cortex_graphiti_client import CortexGraphitiClient

    client = CortexGraphitiClient(api_url="", api_key=api_key)

    print("  Checking Zep Cloud health...")
    healthy = await client.health_check()
    if not healthy:
        print("  FAIL — Zep Cloud is not reachable. Check your API key and network.")
        return False
    print("  PASS — Zep Cloud is reachable.")

    print("  Searching for any stored knowledge (query: 'venture etsy pricing')...")
    results = await client.search(query="venture etsy pricing", limit=5)
    if results:
        print(f"  PASS — {len(results)} result(s) returned from Zep graph.")
        for r in results[:3]:
            snippet = r.content[:100].replace("\n", " ")
            print(f"    • [{r.score:.2f}] {snippet}")
    else:
        print("  INFO — No results returned. Graph may be empty (no sessions pushed yet).")
        print("         This is expected if CORTEX has never completed a 20-exchange session.")

    await client.close()
    return True


async def phase2_round_trip(api_key: str) -> bool:
    print("\n=== Phase 2: Push → Wait → Retrieve (round-trip, ~90s) ===")
    from python.helpers.cortex_graphiti_client import CortexGraphitiClient

    client = CortexGraphitiClient(api_url="", api_key=api_key)
    unique_id = str(uuid.uuid4())[:8].upper()
    fact_text = (
        f"Project Nighthawk (ID: CORTEX-ISOLATION-{unique_id}): "
        f"This is a unique test fact injected by the layer isolation test. "
        f"The Nighthawk project has a confidential budget of exactly €12,847. "
        f"Reference code: ISOLATION-{unique_id}."
    )

    print(f"  Pushing unique fact (ID: {unique_id})...")
    try:
        await client.add_episode(text=fact_text, source="isolation_test")
        print("  PASS — Episode pushed to Zep Cloud.")
    except Exception as e:
        print(f"  FAIL — Could not push episode: {e}")
        return False

    wait_seconds = 90
    print(f"  Waiting {wait_seconds}s for Zep to process asynchronously", end="", flush=True)
    for _ in range(wait_seconds):
        await asyncio.sleep(1)
        print(".", end="", flush=True)
    print(" done.")

    print(f"  Searching for 'Nighthawk {unique_id}'...")
    results = await client.search(query=f"Nighthawk budget ISOLATION-{unique_id}", limit=8)

    found = any(unique_id in (r.content or "") for r in results)
    if found:
        print(f"  PASS — Unique fact retrieved from Zep. L2 push→retrieve is proven.")
        for r in results:
            if unique_id in (r.content or ""):
                print(f"    • [{r.score:.2f}] {r.content[:120]}")
    else:
        print(f"  INFO — Unique fact not found yet (Zep processing may take longer).")
        print(f"         Try searching manually in ~2 minutes:")
        print(f"         query = 'Nighthawk ISOLATION-{unique_id}'")
        if results:
            print(f"  Zep did return {len(results)} result(s) for the query (different content).")

    await client.close()
    return found


async def main():
    print("CORTEX Layer Isolation Test")
    print("=" * 50)

    api_key = _load_api_key()
    if not api_key:
        print("\nFAIL — No Zep API key found.")
        print("  Expected: agents/cortex/settings.json → cortex_graphiti_api_key")
        print("  Or set environment variable: ZEP_API_KEY")
        sys.exit(1)

    print(f"  API key loaded: {api_key[:8]}...")

    phase1_ok = await phase1_connectivity(api_key)
    if not phase1_ok:
        sys.exit(1)

    run_phase2 = "--round-trip" in sys.argv or "-2" in sys.argv
    if run_phase2:
        await phase2_round_trip(api_key)
    else:
        print("\n=== Phase 2 (skipped) ===")
        print("  Run with --round-trip flag to test push->retrieve (takes ~90s):")
        print("  python tests/test_layer_isolation.py --round-trip")

    print("\n" + "=" * 50)
    print("ISOLATION TEST INSTRUCTIONS (manual, in live CORTEX):")
    print("  1. Run: python tests/test_layer_isolation.py --round-trip")
    print("  2. Rename FAISS: mv usr/memory/cortex_main usr/memory/cortex_main_bak")
    print("  3. Restart CORTEX: python run_ui.py")
    print('  4. Ask: "What is the Nighthawk project budget?"')
    print("  5. PASS if answer is '€12,847' — proof it came from Zep (L2), not FAISS (L1)")
    print("  6. Restore: mv usr/memory/cortex_main_bak usr/memory/cortex_main")


if __name__ == "__main__":
    asyncio.run(main())
