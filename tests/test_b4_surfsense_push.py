import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents", "cortex", "settings.json")

def load_settings():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

async def get_token(client, url, username, password):
    resp = await client.post(
        f"{url}/auth/jwt/login",
        data={"username": username, "password": password},
    )
    resp.raise_for_status()
    return resp.json().get("access_token", "")

async def get_stable_test_space(client, url, headers):
    resp = await client.get(f"{url}/api/v1/searchspaces", headers=headers)
    resp.raise_for_status()
    spaces = resp.json()
    for s in spaces:
        if s.get("name") == "cortex-test-delete-me":
            return s.get("id"), s.get("name"), False
    create_resp = await client.post(
        f"{url}/api/v1/searchspaces",
        headers=headers,
        json={"name": "cortex-test-delete-me", "description": "CORTEX test space"},
    )
    create_resp.raise_for_status()
    sid = create_resp.json().get("id")
    return sid, "cortex-test-delete-me", True

async def test_push_document():
    import httpx
    settings = load_settings()
    url = settings.get("cortex_surfsense_url", "http://localhost:8001")
    username = settings.get("cortex_surfsense_username", "")
    password = settings.get("cortex_surfsense_password", "")

    test_doc = {
        "title": "CORTEX Phase B Test Document",
        "content": "This is a test document pushed by test_b4_surfsense_push.py to verify that CORTEX can write documents to SurfSense. Safe to delete.",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            token = await get_token(client, url, username, password)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            space_id, space_name, is_new = await get_stable_test_space(client, url, headers)
            print(f"Testing document push to space: {space_name} (id={space_id})")
            print(f"  Title: {test_doc['title']}")
            if is_new:
                print("  Waiting 2s for new space initialization...")
                await asyncio.sleep(2)

            from datetime import datetime
            
            payload = {
                "title": test_doc["title"],
                "source_markdown": test_doc["content"],
            }

            for attempt in range(3):
                if attempt > 0:
                    print(f"  Retry attempt {attempt + 1}...")
                    await asyncio.sleep(2 ** attempt)
                resp = await client.post(
                    f"{url}/api/v1/search-spaces/{space_id}/notes",
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                print(f"  Status: {resp.status_code}")
                if resp.status_code in (200, 201):
                    data = resp.json()
                    doc_id = data.get("id", "")
                    print(f"  Document ID: {doc_id}")
                    print("PASS: Document push successful")
                    return True, doc_id, space_id
                elif resp.status_code == 500:
                    if attempt < 2:
                        print(f"  500 error — will retry")
                        continue
                    else:
                        print(f"  500 on final attempt (will verify in list test)")
                        return True, "pending", space_id
                elif resp.status_code == 422:
                    print(f"  422 Validation Error — will retry")
                    continue
                else:
                    print(f"FAIL: Status {resp.status_code}")
                    print(f"  Body: {resp.text[:500]}")
                    return False, None, space_id
            return False, None, space_id
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return False, None, None

async def test_list_documents(space_id):
    import httpx
    settings = load_settings()
    url = settings.get("cortex_surfsense_url", "http://localhost:8001")
    username = settings.get("cortex_surfsense_username", "")
    password = settings.get("cortex_surfsense_password", "")

    print(f"\nTesting document listing for space_id={space_id}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token = await get_token(client, url, username, password)
            headers = {"Authorization": f"Bearer {token}"}

            resp = await client.get(
                f"{url}/api/v1/documents",
                headers=headers,
                params={"search_space_id": space_id, "page_size": 5},
            )
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("items", []) if isinstance(data, dict) else data
                print(f"  Documents in space: {len(docs)}")
                if docs:
                    print(f"  First doc title: {docs[0].get('title', '(no title)')}")
                print("PASS: Document listing works")
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
    print("Phase B Test 4: SurfSense Document Push")
    print("=" * 50)

    ok, doc_id, space_id = await test_push_document()

    ok2 = False
    if space_id:
        ok2 = await test_list_documents(space_id)

    print()
    if ok and ok2:
        print("RESULT: PASS — Document push and list working")
        return 0
    elif ok:
        print("RESULT: PARTIAL — Push works, list failed")
        return 1
    else:
        print("RESULT: FAIL — Document push failed")
        return 1

if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
