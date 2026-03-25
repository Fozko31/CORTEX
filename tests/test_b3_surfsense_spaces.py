import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents", "cortex", "settings.json")

EXPECTED_SPACES = [
    "cortex_user_profile",
    "cortex_conversations",
    "cortex_knowledge",
    "cortex_outcomes",
    "cortex_weekly_digest",
    "cortex_cross_venture",
]

def load_settings():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

async def get_token(client, url, username, password):
    import httpx
    resp = await client.post(
        f"{url}/auth/jwt/login",
        data={"username": username, "password": password},
    )
    resp.raise_for_status()
    return resp.json().get("access_token", "")

async def test_list_spaces():
    import httpx
    settings = load_settings()
    url = settings.get("cortex_surfsense_url", "http://localhost:8001")
    username = settings.get("cortex_surfsense_username", "")
    password = settings.get("cortex_surfsense_password", "")

    print(f"Testing space listing at: {url}/api/v1/searchspaces")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token = await get_token(client, url, username, password)
            headers = {"Authorization": f"Bearer {token}"}

            resp = await client.get(f"{url}/api/v1/searchspaces", headers=headers)
            resp.raise_for_status()
            spaces = resp.json()
            existing_names = {s.get("name", "") for s in spaces}

            print(f"  Existing spaces ({len(spaces)}): {sorted(existing_names)}")

            missing = [s for s in EXPECTED_SPACES if s not in existing_names]
            present = [s for s in EXPECTED_SPACES if s in existing_names]

            if present:
                print(f"  CORTEX spaces already present: {present}")
            if missing:
                print(f"  CORTEX spaces not yet created: {missing}")
                print("  (They will be auto-created on first CORTEX session end)")

            return True, spaces
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return False, []

async def test_create_test_space():
    import httpx
    settings = load_settings()
    url = settings.get("cortex_surfsense_url", "http://localhost:8001")
    username = settings.get("cortex_surfsense_username", "")
    password = settings.get("cortex_surfsense_password", "")

    test_space_name = "cortex-test-delete-me"
    print(f"\nTesting space creation: creating '{test_space_name}'")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token = await get_token(client, url, username, password)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            resp = await client.post(
                f"{url}/api/v1/searchspaces",
                headers=headers,
                json={"name": test_space_name, "description": "CORTEX test space — safe to delete"},
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                space_id = data.get("id")
                print(f"  Created space ID: {space_id}")
                print("PASS: Space creation works")
                return True, space_id
            elif resp.status_code == 409:
                print("  Space already exists (409) — that's fine")
                print("PASS: Space creation API works")
                return True, None
            else:
                print(f"FAIL: Status {resp.status_code}")
                print(f"  Body: {resp.text[:400]}")
                return False, None
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return False, None

async def main():
    print("=" * 50)
    print("Phase B Test 3: SurfSense Spaces")
    print("=" * 50)

    ok1, _ = await test_list_spaces()
    ok2, _ = await test_create_test_space()

    print()
    if ok1 and ok2:
        print("RESULT: PASS — Space list and create working")
        return 0
    elif ok1:
        print("RESULT: PARTIAL — List works, create failed")
        return 1
    else:
        print("RESULT: FAIL — Spaces API not working")
        return 1

if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
