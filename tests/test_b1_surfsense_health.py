import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents", "cortex", "settings.json")

def load_settings():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def test_surfsense_health():
    import httpx
    settings = load_settings()
    url = settings.get("cortex_surfsense_url", "http://localhost:8001")

    print(f"Testing SurfSense health at: {url}/health")
    try:
        resp = httpx.get(f"{url}/health", timeout=10.0)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            print("PASS: SurfSense backend is reachable and healthy")
            return True
        else:
            print(f"FAIL: Unexpected status {resp.status_code}")
            print(f"  Body: {resp.text[:300]}")
            return False
    except httpx.ConnectError as e:
        print(f"FAIL: Cannot connect to {url}")
        print(f"  Error: {e}")
        print("  Check: is SurfSense running? Run: docker ps")
        return False
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return False

def test_surfsense_docs():
    import httpx
    settings = load_settings()
    url = settings.get("cortex_surfsense_url", "http://localhost:8001")

    print(f"\nTesting SurfSense API docs at: {url}/docs")
    try:
        resp = httpx.get(f"{url}/docs", timeout=10.0)
        if resp.status_code == 200:
            print("PASS: Swagger UI is accessible")
            return True
        else:
            print(f"INFO: /docs returned {resp.status_code} (non-critical)")
            return True
    except Exception as e:
        print(f"INFO: /docs not accessible: {e} (non-critical)")
        return True

if __name__ == "__main__":
    print("=" * 50)
    print("Phase B Test 1: SurfSense Health Check")
    print("=" * 50)
    r1 = test_surfsense_health()
    r2 = test_surfsense_docs()
    print()
    if r1:
        print("RESULT: PASS — SurfSense backend reachable")
        sys.exit(0)
    else:
        print("RESULT: FAIL — SurfSense backend not reachable")
        sys.exit(1)
