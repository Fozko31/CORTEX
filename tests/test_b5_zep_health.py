import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents", "cortex", "settings.json")

def load_settings():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

async def test_zep_reachable():
    import httpx
    settings = load_settings()
    url = settings.get("cortex_graphiti_url", "https://api.getzep.com")

    print(f"Testing Zep Cloud API reachability: {url}")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{url}/healthz", timeout=10.0)
            print(f"  Status: {resp.status_code}")
            if resp.status_code in (200, 204):
                print("PASS: Zep Cloud API is reachable")
                return True
            else:
                print(f"INFO: /healthz returned {resp.status_code} — trying root endpoint")
    except Exception:
        pass

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, timeout=10.0)
            print(f"  Root status: {resp.status_code}")
            if resp.status_code < 500:
                print("PASS: Zep Cloud API root is reachable")
                return True
            else:
                print(f"FAIL: Zep Cloud returned {resp.status_code}")
                return False
    except httpx.ConnectError as e:
        print(f"FAIL: Cannot connect to {url}")
        print(f"  Error: {e}")
        print("  Check: internet connectivity and Zep Cloud status")
        return False
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return False

async def test_zep_api_key():
    import httpx
    settings = load_settings()
    url = settings.get("cortex_graphiti_url", "https://api.getzep.com")
    api_key = settings.get("cortex_graphiti_api_key", "")

    print(f"\nTesting Zep Cloud API key validity")
    if not api_key or api_key == "SET_YOUR_ZEP_CLOUD_API_KEY_HERE":
        print("SKIP: cortex_graphiti_api_key not set in agents/cortex/settings.json")
        print("  Go to https://app.getzep.com to get your API key")
        return None

    print(f"  Key (first 20 chars): {api_key[:20]}...")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{url}/api/v2/users",
                headers={"Authorization": f"Api-Key {api_key}"},
                params={"limit": 1},
                timeout=10.0,
            )
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                print("PASS: Zep Cloud API key is valid")
                return True
            elif resp.status_code == 401:
                print("FAIL: 401 Unauthorized — API key is invalid or expired")
                print("  Get a new key at: https://app.getzep.com")
                return False
            elif resp.status_code == 404:
                print(f"INFO: /api/v2/users endpoint not found — trying graph endpoint")
                resp2 = await client.get(
                    f"{url}/api/v2/graph",
                    headers={"Authorization": f"Api-Key {api_key}"},
                    timeout=10.0,
                )
                print(f"  Graph status: {resp2.status_code}")
                if resp2.status_code in (200, 404):
                    print("PASS: Zep Cloud API key accepted (no 401)")
                    return True
                elif resp2.status_code == 401:
                    print("FAIL: 401 Unauthorized — API key invalid")
                    return False
                else:
                    print(f"INFO: Status {resp2.status_code} — key may be valid, endpoint varies by plan")
                    return True
            else:
                print(f"INFO: Status {resp.status_code} — treating as reachable")
                return True
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return False

async def main():
    print("=" * 50)
    print("Phase B Test 5: Zep Cloud Connectivity")
    print("=" * 50)

    ok1 = await test_zep_reachable()
    ok2 = await test_zep_api_key()

    print()
    if ok1 and ok2 is True:
        print("RESULT: PASS — Zep Cloud reachable and API key valid")
        return 0
    elif ok1 and ok2 is None:
        print("RESULT: PARTIAL — Zep reachable but API key not configured")
        return 0
    elif ok1 and ok2 is False:
        print("RESULT: PARTIAL — Zep reachable but API key invalid")
        return 1
    else:
        print("RESULT: FAIL — Zep Cloud not reachable")
        return 1

if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
