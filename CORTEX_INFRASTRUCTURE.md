# CORTEX Infrastructure Registry

**ALWAYS UPDATE THIS FILE** when ports, services, or config locations change.

Last updated: 2026-03-24

---

## Running Services

| Service | Container / Process | Host Port | Internal Port | Status |
|---|---|---|---|---|
| **CORTEX** | Python (Windows, no Docker) | **50001** | — | Manual start |
| **SurfSense Backend** | `surfsense-backend-1` (Docker) | **8001** | 8000 | Auto (Docker) |
| **SurfSense Frontend** | `surfsense-frontend-1` (Docker) | **3001** | 3000 | Auto (Docker) |
| **SurfSense Electric** | `surfsense-electric-1` (Docker) | **5133** | — | Auto (Docker) |
| **SurfSense Redis** | `surfsense-redis-1` (Docker) | internal | 6379 | Auto (Docker) |
| **SurfSense DB** | `surfsense-db-1` (Docker) | internal | 5432 | Auto (Docker) |
| **Zep Cloud** | External SaaS | — | — | Always on |

---

## Service URLs

| Service | URL | Notes |
|---|---|---|
| CORTEX UI | http://localhost:50001 | Start with `python run_ui.py` |
| SurfSense Backend API | http://localhost:8001 | Swagger at `/docs` |
| SurfSense Frontend | http://localhost:3001 | User-facing web app |
| Zep Cloud API | https://api.getzep.com | External, requires API key |
| Zep Cloud Dashboard | https://app.getzep.com | Browser login |

---

## Networking Rules

| From | To | Correct URL |
|---|---|---|
| CORTEX (Python on Windows) | SurfSense Docker | `http://localhost:8001` |
| CORTEX (Python on Windows) | Zep Cloud | `https://api.getzep.com` |
| Inside Docker container | Windows host | `http://host.docker.internal:PORT` |
| Browser (user) | CORTEX | `http://localhost:50001` |
| Browser (user) | SurfSense | `http://localhost:3001` |

**Rule:** `host.docker.internal` is ONLY valid from inside a Docker container. CORTEX runs as Python on Windows, so it always uses `localhost`.

---

## Configuration Files

| File | Purpose | Contains |
|---|---|---|
| `agents/cortex/settings.json` | CORTEX agent runtime config | SurfSense URL, Zep API key, routing settings |
| `agents/cortex/agent.json` | CORTEX agent profile definition | Model selections, persona |
| `usr/secrets.env` | Server secrets | `RFC_PASSWORD`, auth tokens |
| `C:\Users\Admin\surfsense-local\surfsense.env.txt` | SurfSense Docker secrets | DB password, JWT secret, API keys — **DO NOT COMMIT** |

---

## settings.json Keys (agents/cortex/settings.json)

| Key | Description | Example Value |
|---|---|---|
| `agent_memory_subdir` | Memory isolation directory | `cortex_main` |
| `agent_knowledge_subdir` | Knowledge isolation directory | `cortex_main` |
| `cortex_surfsense_url` | SurfSense backend base URL | `http://localhost:8001` |
| `cortex_surfsense_username` | SurfSense login email | your email |
| `cortex_surfsense_password` | SurfSense login password | your password |
| `cortex_surfsense_api_key` | Cached JWT token (auto-refreshed) | JWT string |
| `cortex_graphiti_url` | Zep Cloud API URL | `https://api.getzep.com` |
| `cortex_graphiti_api_key` | Zep Cloud API key | from app.getzep.com |
| `cortex_push_interval_exchanges` | How many exchanges before push | `20` |
| `cortex_daily_cost_limit` | Max USD/day on model calls | `5.0` |
| `cortex_proactive_level` | Retrieval aggressiveness | `low` / `medium` / `high` |
| `cortex_pull_max_tokens` | Max tokens for Tier 1-2 context | `2000` |
| `cortex_pull_tier3_max_tokens` | Max tokens for Tier 3 deep pull | `8000` |

---

## Start / Stop Commands

### Start CORTEX
```
cd C:\Users\Admin\CORTEX
python run_ui.py
```
CORTEX runs at http://localhost:50001. Stop with `Ctrl+C`.

### Check SurfSense Docker status
```
docker ps
```
Look for `surfsense-backend-1`, `surfsense-frontend-1`, etc.

### Start SurfSense (if not running)
```
cd C:\Users\Admin\surfsense-local
docker compose up -d
```

### Stop SurfSense
```
cd C:\Users\Admin\surfsense-local
docker compose down
```

### Restart a single SurfSense container
```
docker restart surfsense-backend-1
```

---

## Data Directories

| Path | Contents |
|---|---|
| `usr/memory/cortex_main/` | CORTEX FAISS memory, JSON models (trust, personality, commitments, self-model) |
| `usr/knowledge/cortex_main/` | CORTEX knowledge fragments |
| `usr/memory/default/` | Default agent memory (separate from CORTEX) |
| `logs/` | CORTEX server HTML log files |
| `server.log` | CORTEX server text log |

---

## SurfSense Spaces (managed by CORTEX)

The 6 core SurfSense spaces defined in `cortex_surfsense_router.py` → `CORE_SPACES`:

| Space Name | Category Routing | Contents |
|---|---|---|
| `cortex_user_profile` | `user_preference` | User preferences, personality, trust |
| `cortex_conversations` | `conversation` | Per-session conversation summaries |
| `cortex_knowledge` | `business_fact`, `research` | Facts, research, general knowledge |
| `cortex_outcomes` | `decision`, `outcome` | Decisions, results, commitments, ROI |
| `cortex_weekly_digest` | (scheduled) | Weekly digest summaries, trends |
| `cortex_cross_venture` | (scheduled) | Cross-venture patterns and lessons |

Additional venture-specific spaces are created dynamically as `cortex_venture_{name}` when venture metadata is present.

---

## SurfSense API Endpoints Used by CORTEX

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/auth/jwt/login` | Get Bearer token (form: `username`, `password`) |
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/searchspaces` | List spaces |
| `POST` | `/api/v1/searchspaces` | Create space (body: `{"name": "...", "description": "..."}`) |
| `POST` | `/api/v1/search-spaces/{id}/notes` | Push document (body: `{"title": "...", "source_markdown": "..."}`) |
| `GET` | `/api/v1/documents` | List documents (params: `search_space_id`, `page_size`) — returns `{"items": [...]}` |
| `GET` | `/api/v1/documents/search` | Filter documents by **title** only (not semantic) |

**Note:** SurfSense has no semantic REST search API. Semantic retrieval only works via the chat/threads interface.

---

## Phase B Test Scripts

Located in `tests/`:

| Script | What it tests | Run with |
|---|---|---|
| `test_b1_surfsense_health.py` | SurfSense backend reachable | `python tests\test_b1_surfsense_health.py` |
| `test_b2_surfsense_auth.py` | JWT login + token received | `python tests\test_b2_surfsense_auth.py` |
| `test_b3_surfsense_spaces.py` | Spaces list + create test space | `python tests\test_b3_surfsense_spaces.py` |
| `test_b4_surfsense_push.py` | Push test document + verify | `python tests\test_b4_surfsense_push.py` |
| `test_b5_zep_health.py` | Zep Cloud API reachable + key valid | `python tests\test_b5_zep_health.py` |
| `test_b6_model_router.py` | Model routing logic (no LLM calls) | `python tests\test_b6_model_router.py` |
