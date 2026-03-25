import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents", "cortex", "settings.json")

def load_settings():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

async def test_jwt_login():
    import httpx
    settings = load_settings()
    url = settings.get("cortex_surfsense_url", "http://localhost:8001")
    username = settings.get("cortex_surfsense_username", "")
    password = settings.get("cortex_surfsense_password", "")

    print(f"Testing JWT login at: {url}/auth/jwt/login")
    print(f"  Username: {username or '(not set)'}")
    print(f"  Password: {'(set)' if password else '(not set)'}")

    if not username or username == "SET_YOUR_EMAIL_HERE":
        print("FAIL: cortex_surfsense_username not set in agents/cortex/settings.json")
        return False, None
    if not password or password == "SET_YOUR_SURFSENSE_JWT_PASSWORD_HERE":
        print("FAIL: cortex_surfsense_password not set in agents/cortex/settings.json")
        return False, None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/auth/jwt/login",
                data={"username": username, "password": password},
            )
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token", "")
                if token:
                    print(f"  Token (first 40 chars): {token[:40]}...")
                    print("PASS: JWT login successful, access_token received")
                    return True, token
                else:
                    print(f"FAIL: Response 200 but no access_token in body")
                    print(f"  Body: {resp.text[:300]}")
                    return False, None
            elif resp.status_code == 400:
                print(f"FAIL: 400 Bad Request — wrong credentials or bad form data")
                print(f"  Body: {resp.text[:300]}")
                return False, None
            elif resp.status_code == 422:
                print(f"FAIL: 422 Validation error — check username/password field names")
                print(f"  Body: {resp.text[:300]}")
                return False, None
            else:
                print(f"FAIL: Status {resp.status_code}")
                print(f"  Body: {resp.text[:300]}")
                return False, None
    except httpx.ConnectError as e:
        print(f"FAIL: Cannot connect to {url}")
        print(f"  Error: {e}")
        print("  Run test_b1_surfsense_health.py first")
        return False, None
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return False, None

async def test_authenticated_request(token: str):
    import httpx
    settings = load_settings()
    url = settings.get("cortex_surfsense_url", "http://localhost:8001")

    print(f"\nTesting authenticated request: GET {url}/api/v1/searchspaces")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{url}/api/v1/searchspaces",
                headers={"Authorization": f"Bearer {token}"},
            )
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                spaces = resp.json()
                print(f"  Found {len(spaces)} existing spaces")
                print("PASS: Authenticated API call successful")
                return True
            else:
                print(f"FAIL: Status {resp.status_code}")
                print(f"  Body: {resp.text[:300]}")
                return False
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return False

async def main():
    print("=" * 50)
    print("Phase B Test 2: SurfSense Authentication")
    print("=" * 50)

    ok, token = await test_jwt_login()
    if ok and token:
        await test_authenticated_request(token)
        print("\nRESULT: PASS — JWT auth working")
        return 0
    else:
        print("\nRESULT: FAIL — JWT auth failed")
        return 1

if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
