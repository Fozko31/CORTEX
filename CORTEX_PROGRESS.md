# CORTEX — Progress Tracker

**Last Updated:** 2026-03-25 (Phase C core build complete — C-1 through C-9. Pending: live test.)

---

## CURRENT STATUS SUMMARY

| Phase | Name | Status |
|-------|------|--------|
| 0 | Setup & Decision Gates | COMPLETE |
| A1 | CORTEX Identity | COMPLETE |
| A2 | Memory & Knowledge Foundation | COMPLETE + TESTED |
| B | Consciousness Layer (SurfSense + Graphiti) | COMPLETE + TESTED LIVE |
| Tool-1 | Research API Clients | COMPLETE |
| Tool-2 | Research Orchestrator + Agent Tool | COMPLETE |
| Tool-3 | GitHub MCP | COMPLETE + ENABLED |
| Tool-4 | Composio Client | COMPLETE |
| Tool-5 | Browserbase MCP | COMPLETE (disabled — no API keys yet) |
| Tool-6 | Tool Registry + Knowledge Files | COMPLETE |
| Tool-7 | Venture Pack Activation | COMPLETE |
| Umbrella-A | Runtime Wiring Confirmed | COMPLETE |
| Umbrella-B | cortex_research_tool Prompt | COMPLETE |
| Umbrella-C | search_engine Override Prompt | COMPLETE |
| Umbrella-D | Role.md — Tool Routing Table | COMPLETE |
| Umbrella-E | _15_cortex_tool_state.py Extension | COMPLETE |
| Umbrella-F | Browserbase Fallback Guidance | COMPLETE |
| Umbrella-G | cortex_tool_router.py Helper | COMPLETE |
| Test-1 | Tier 1 Research (Tavily + Exa) | PASS |
| Test-B2-B4 | SurfSense Auth + Spaces + Push | PASS — all 6 spaces live |
| Test-B5 | Zep Cloud connectivity | PASS |
| Test-Holistic | Push+Pull+Graphiti end-to-end | PASS |
| B-Opt-1 | Graphiti trivial-query gate + Zep-down chat alert | COMPLETE |
| B-Opt-2 | SurfSense: 3 spaces, 10 docs, keyword scoring, top 5 | COMPLETE |
| B-Opt-3 | SurfSense title: natural language, 220-char, keyword-rich | COMPLETE |
| B-Opt-4 | Isolation tests: Zep PASS (4 results), SurfSense PASS (push+retrieve) | COMPLETE |
| C-1 | cortex_venture_dna.py — VentureDNA + CVS (8 dim) + FailurePattern + CrossVenture | COMPLETE |
| C-2 | cortex_outcome_ledger.py — SQLite ledger + Kelly math + DecisionEvent | COMPLETE |
| C-3 | cortex_venture_discovery.py — domain-agnostic scanner, Tier1/2, gap analysis | COMPLETE |
| C-4 | venture_create.py — 9-step iterative creation flow, memory-first, SurfSense on confirm | COMPLETE |
| C-5 | venture_manage.py — list/status/health/activate/kelly/cvs | COMPLETE |
| C-6 | monologue_start/_07_venture_context.py — 200-token DNA injection per turn | COMPLETE |
| C-7 | cortex_surfsense_router.py update — venture two-space routing (DNA + ops) | COMPLETE |
| C-8 | Cross-venture synthesis — background fn in cortex_venture_dna.py | COMPLETE |
| C-9 | Prompt docs — venture_create.md, venture_manage.md, role.md updated | COMPLETE |
| C-Test | Live end-to-end: create venture, confirm, check spaces + ledger | PENDING |
| D | Authority Engine + Autonomy + Goals | NOT STARTED |
| E | Telegram Integration (mobile-first) | NOT STARTED |
| F | Voice Layer (STT/TTS, free/cheap first) | NOT STARTED |
| G | Self-optimization loop | NOT STARTED |
| H | Commercial Jarvis variant (desktop) | NOT STARTED |

---

## RUNTIME ENVIRONMENT (as of 2026-03-25)

- **Local path:** `C:\Users\Admin\CORTEX`
- **Python:** Global Python 3.12 (venv was rebuilt after dependency corruption)
- **Port:** `localhost:5000` (WEB_UI_PORT not set in usr/.env — defaults to 5000)
- **Node.js:** v22.18.0
- **Run command:** `python run_ui.py` from `C:\Users\Admin\CORTEX`
- **Agent profile:** `cortex`

### API Keys in `usr/.env`

| Key | Status |
|-----|--------|
| API_KEY_OPENROUTER | SET |
| TAVILY_API_KEY | SET |
| EXA_API_KEY | SET |
| FIRECRAWL_API_KEY | SET |
| COMPOSIO_API_KEY | SET |
| GITHUB_PERSONAL_ACCESS_TOKEN | SET |
| BROWSERBASE_API_KEY | NOT SET (deferred) |
| BROWSERBASE_PROJECT_ID | NOT SET (deferred) |
| WEB_UI_PORT | NOT SET (defaults to 5000) |

### MCP Servers in `usr/settings.json`

| Server | Status |
|--------|--------|
| GitHub MCP (`@modelcontextprotocol/server-github`) | ENABLED — `disabled: false`, PAT filled in env dict |
| Browserbase MCP (`@browserbasehq/mcp`) | DISABLED — `disabled: true`, no API keys yet |

---

## Phase 0: Setup & Decision Gates
**Status:** COMPLETE

- [x] Fork Agent Zero → github.com/Fozko31/CORTEX
- [x] Clone to `C:\Users\Admin\CORTEX`
- [x] Copy CORTEX_VISION_DISCOVERY_BRIEF.md
- [x] Copy CORTEX_PLAN.md
- [x] Create CLAUDE.md
- [x] Create CORTEX_DECISIONS.md
- [x] Create CORTEX_PROGRESS.md
- [x] Python 3.12 environment + dependencies installed
- [x] Server confirmed running — `/health` 200 OK
- [x] LLM responds with CORTEX personality
- [x] Single-session memory save + recall verified

---

## Phase A1: CORTEX Identity
**Status:** COMPLETE

- [x] `agents/cortex/agent.json`
- [x] `agents/cortex/settings.json` (memory isolation: cortex_main)
- [x] `agents/cortex/prompts/agent.system.main.role.md` (COO identity — updated in Umbrella-D)
- [x] `agents/cortex/prompts/agent.system.main.communication.md`
- [x] `agents/cortex/prompts/agent.system.tool.response.md`
- [x] `python/extensions/system_prompt/_05_cortex_identity.py`

---

## Phase A2: Memory & Knowledge Foundation
**Status:** CODE COMPLETE — Live verification pending

**Decision:** DirtyJson + JSON file persistence (no Zep/Instructor). FAISS for entity/fact storage.

- [x] `python/helpers/cortex_knowledge_extractor.py`
- [x] `python/helpers/cortex_trust_engine.py`
- [x] `python/helpers/cortex_personality_model.py` — `challenge_level` default 4.0/5
- [x] `python/helpers/cortex_commitment_tracker.py`
- [x] `python/extensions/monologue_end/_10_knowledge_extraction.py`
- [x] `python/extensions/message_loop_prompts_after/_15_temporal_memory.py`
- [x] `python/extensions/message_loop_prompts_after/_17_personality_model.py`
- [x] `python/extensions/system_prompt/_07_trust_level.py`

**Pending live verification:**
- [ ] `usr/memory/cortex_main/cortex_trust.json` created after first exchange
- [ ] `usr/memory/cortex_main/cortex_personality.json` created
- [ ] `usr/memory/cortex_main/cortex_commitments.json` created on promise

---

## Phase B: Consciousness Layer
**Status:** CODE COMPLETE — Partial live verification (2026-03-24)

**Verified (unit tests):** SurfSense health, JWT auth, spaces, document push, Zep Cloud, model router.
**Not yet tested (runtime):** surfsense_push after live chat, surfsense_pull injecting consciousness, metadata flow.

- [x] `python/helpers/cortex_model_router.py`
- [x] `python/helpers/cortex_ingestion_schema.py`
- [x] `python/helpers/cortex_surfsense_client.py`
- [x] `python/helpers/cortex_surfsense_router.py`
- [x] `python/helpers/cortex_session_summarizer.py`
- [x] `python/helpers/cortex_graphiti_client.py`
- [x] `python/helpers/cortex_self_model.py`
- [x] `python/helpers/cortex_weekly_digest.py`
- [x] `python/extensions/monologue_start/_05_self_model_load.py`
- [x] `python/extensions/message_loop_prompts_after/_20_surfsense_pull.py`
- [x] `python/extensions/monologue_end/_15_graphiti_update.py`
- [x] `python/extensions/monologue_end/_60_struggle_detect.py`
- [x] `python/extensions/process_chain_end/_10_surfsense_push.py`

**Critical fix applied:** Python httpx JSON serialization — use `json=` param not `content=json.dumps()`.

---

## Tool Stack — Phase 1: Research API Clients
**Status:** COMPLETE

Four async API clients built. All read from `usr/.env` via `from_agent_config(agent)`.

- [x] `python/helpers/cortex_tavily_client.py` — `search()`, `search_multi()`
- [x] `python/helpers/cortex_exa_client.py` — `search()`, `search_multi()`, `find_similar()`
- [x] `python/helpers/cortex_perplexity_client.py` — Tier 2 only, $0.25 soft / $0.50 hard cap, via OpenRouter
- [x] `python/helpers/cortex_firecrawl_client.py` — `scrape()`, `extract()`, `crawl()` with async poll
- [x] `requirements.txt` — added `httpx>=0.27.0`
- [x] `agents/cortex/settings.json` — added `cortex_perplexity_model`, `cortex_perplexity_soft_cap`, `cortex_perplexity_hard_cap`

---

## Tool Stack — Phase 2: Research Orchestrator + Agent Tool
**Status:** COMPLETE

- [x] `python/helpers/cortex_research_orchestrator.py`
  - Tier 1: Tavily + Exa multi-query, deduplicated, structured summary
  - Tier 2: Tier 1 findings passed as context to Perplexity, hard cap enforced
  - `ResearchOutput.context_summary` — ready-for-Claude structured text
- [x] `python/tools/cortex_research_tool.py` (Tool subclass)
  - Parses queries as JSON array, newline list, or plain string
  - Calls `CortexResearchOrchestrator.from_agent(self.agent)`

---

## Tool Stack — Phase 3: GitHub MCP
**Status:** COMPLETE + ENABLED

- [x] GitHub MCP added to `usr/settings.json` under `mcp_servers`
- [x] PAT injected into MCP env dict (from `usr/.env`)
- [x] `disabled: false` — active at startup
- [x] Confirmed at startup: `MCPClientBase (github): Tools updated. Found 26 tools.`
- **PAT type:** Fine-grained personal access token (read-only — Contents, Issues, Pull requests)

---

## Tool Stack — Phase 4: Composio Client
**Status:** COMPLETE

- [x] `python/helpers/cortex_composio_client.py`
  - `list_apps()`, `list_actions()`, `execute()`, `get_connected_accounts()`
  - `is_app_connected()`, `initiate_connection()`, `session_for_venture()`
  - Entity ID scoped per venture for isolation

---

## Tool Stack — Phase 5: Browserbase MCP
**Status:** COMPLETE (disabled — API keys not yet obtained)

- [x] Browserbase MCP added to `usr/settings.json` under `mcp_servers`
- [x] `disabled: true` — will enable when `BROWSERBASE_API_KEY` + `BROWSERBASE_PROJECT_ID` obtained
- **Purpose:** Cloud browser fallback for JS-heavy / login-gated / CAPTCHA / interactive pages

---

## Tool Stack — Phase 6: Tool Registry + Knowledge Files
**Status:** COMPLETE

- [x] `python/helpers/cortex_tool_registry.py`
  - `ToolState`: `known` / `installed` / `enabled`
  - `ToolIntegration`: `direct_api` / `mcp` / `composio`
  - `auto_detect_installed()` — reads env keys at startup
  - `build_default()` — registers 9 tools
- [x] `usr/knowledge/cortex_main/main/tools/tool_registry_core.md`
- [x] `usr/knowledge/cortex_main/main/tools/tool_registry_optional.md`
- [x] `usr/knowledge/cortex_main/main/tools/tool_selection_rules.md`
- [x] `usr/knowledge/cortex_main/main/tools/tool_install_playbooks.md`
- [x] `usr/knowledge/cortex_main/main/tools/tool_registry_venture_packs.md`
- [x] `usr/knowledge/cortex_main/main/ventures/venture_pack_definitions.md`

---

## Tool Stack — Phase 7: Venture Pack Activation
**Status:** COMPLETE

- [x] `python/helpers/cortex_venture_activation.py`
  - `activate(venture_name)` / `deactivate()`
  - 6 packs: `core`, `market_research`, `product_dev`, `content`, `operations`, `fundraising`
  - Composio entity_id scoped per venture

---

## Tool Umbrella Wiring (Phases A–G)
**Status:** ALL COMPLETE

These phases wire the tool stack into the agent's routing and prompt system.

### Umbrella-A — Runtime Wiring Confirmed
- `agent.py:get_tool()` does exact filename lookup → `python/tools/<name>.py`
- `agents/cortex/prompts/` overrides applied before global `prompts/`

### Umbrella-B — cortex_research_tool Prompt
- [x] `agents/cortex/prompts/agent.system.tool.cortex_research_tool.md`
  - Documents Tier1/Tier2, multi-query, Tavily+Exa+Perplexity, Claude synthesizes
  - Includes JSON usage example

### Umbrella-C — search_engine Override
- [x] `agents/cortex/prompts/agent.system.tool.search_engine.md`
  - CORTEX-scoped: prefer `cortex_research_tool`, use `search_engine` only as fallback

### Umbrella-D — Role.md Tool Routing Table
- [x] `agents/cortex/prompts/agent.system.main.role.md` — Step 6 updated
  - Renamed: "Plan Research and Tool Use"
  - Added routing table:
    ```
    Research — live, market, strategic, technical → cortex_research_tool
    Repo / dev → GitHub MCP (github.*)
    SaaS actions → Composio
    Page extraction → Firecrawl
    Browser — JS-heavy, login-gated, CAPTCHA → Browserbase (fallback)
    ```
  - Added: "RFC and localhost-based tool paths are not available. Never assume localhost:* availability."

### Umbrella-E — Dynamic Tool State Extension
- [x] `agents/cortex/extensions/system_prompt/_15_cortex_tool_state.py`
  - Appends live tool state (enabled/not_configured) to system prompt each turn

### Umbrella-F — Browserbase Fallback Guidance
- Covered in Umbrella-B tool prompt + Umbrella-D routing table

### Umbrella-G — Tool Router Helper
- [x] `python/helpers/cortex_tool_router.py`
  - `TaskFamily` enum: RESEARCH / REPO_DEV / SAAS_ACTION / EXTRACTION / BROWSER
  - `get_tool_states()` — reads env keys, returns enabled/not_configured per tool
  - `build_tool_state_prompt()` — LLM-friendly tool state block (1,286 chars)
  - `routing_guide_text()` — routing table as plain text

---

## Dependency Fixes Applied (2026-03-25)
**Status:** COMPLETE — Server running

These were blocking issues fixed in the current session:

| File | Problem | Fix |
|------|---------|-----|
| `python/helpers/call_llm.py` | `from langchain.prompts import ...` — monolithic package removed | Changed to `from langchain_core.prompts import ...` |
| `python/helpers/call_llm.py` | `from langchain.schema import AIMessage` | Changed to `from langchain_core.messages import AIMessage` |
| `python/helpers/document_query.py` | `from langchain.schema import SystemMessage, HumanMessage` | Changed to `from langchain_core.messages import ...` |
| `python/helpers/document_query.py` | `from langchain.text_splitter import RecursiveCharacterTextSplitter` | Changed to `from langchain_text_splitters import ...` |
| `requirements.txt` | `langchain-text-splitters` missing | Added `langchain-text-splitters>=0.0.1` |
| `requirements.txt` | `litellm` missing | Added `litellm>=1.0.0` |

**Root cause:** Requirements pinned `langchain-core==0.3.49` + `langchain-community==0.3.19` but not the monolithic `langchain` package (which stops at 0.3.28 and does not have version 0.3.49).

---

## Known Background Warnings (non-blocking)
**Status:** Identified — not fixed yet

| Warning | Source | Impact |
|---------|--------|--------|
| `Failed to pause job loop by development instance: Cannot connect to host localhost:55080` | `python/helpers/job_loop.py:26` — tries to ping dev instance if `runtime.is_development()` | Non-blocking. Fires every 60s. No effect on agent behavior. |
| `LLM consolidation analysis failed: LLM response is not a valid JSON object` | `python/helpers/memory_consolidation.py:523` — background memory dedup LLM call returns malformed JSON | Non-blocking. Consolidation skipped for that cycle. Does not affect current conversation. |
| `Task was destroyed but it is pending! ... litellm LoggingWorker` | litellm background async logging worker cleanup | Non-blocking. Cosmetic shutdown warning. |
| `RequestsDependencyWarning: urllib3 / chardet version mismatch` | requests package version mismatch | Non-blocking. Cosmetic warning only. |

---

## Test Status

| Test | Description | Status |
|------|-------------|--------|
| Test 1 | Tier 1 research — AI founder productivity tools 2026 | PASS (infrastructure). Agent routed to `cortex_research_tool`, Tier 1 fired, Tavily + Exa returned 30 sources, synthesis delivered. |
| Test 2 | Tool awareness — which tools enabled? | PENDING |
| Test 3 | Tier 2 research — Perplexity reasoning | PENDING |
| Test 4 | GitHub MCP — list/search repos | PENDING |
| Test 5 | Firecrawl — website content extraction | PENDING |
| Test 6 | Full routing chain (research + GitHub + Firecrawl + synthesis) | PENDING |
| Test 7 | Browserbase fallback awareness | PENDING |

---

## SESSION DISCOVERIES — 2026-03-25 (Ruflo + Deep Codebase Analysis)

### Ruflo MCP Framework — Enabled
Ruflo MCP server is live and configured for this project. The following capabilities were initialized:
- **Model routing:** ON — `preferCost: true` — Haiku for sub-agents on simple tasks
- **Embeddings:** ON — 384-dim, hyperbolic Poincaré ball (all-MiniLM-L6-v2)
- **Hooks:** ON — 16 hooks (PreToolUse, PostToolUse, SessionStart, SessionEnd) — learns from every edit
- **Swarm:** ON — ID `swarm-...8737lo`, hierarchical + adaptive, max 20 agents
- **Hive-mind:** ON — ID `hive-...od41tp`, byzantine consensus, queen = cortex-main
- **Memory namespace:** `cortex` — seeded with project context + vector embeddings
- **Ruflo config location:** `.claude-flow/config.json`

### Billing — Switched to Pro Subscription
- Removed `primaryApiKey` from `~/.claude.json` — Claude Code now uses OAuth Pro subscription
- No more per-token billing for coding sessions
- OpenRouter credits (for CORTEX Agent Zero runtime) are separate — managed at openrouter.ai

### Deep Analysis Findings

#### Gaps Identified (9 fixes needed before Phase C)
| # | Issue | File | Severity |
|---|-------|------|----------|
| 1 | MCP env vars not inherited from `.env` | `usr/settings.json` mcp_servers env dicts | Medium |
| 2 | Research tool silently accepts malformed JSON queries | `python/tools/cortex_research_tool.py:47-66` | Medium |
| 3 | Venture activation state not persisted across restarts | `python/helpers/cortex_venture_activation.py` | Medium |
| 4 | SurfSense push failure silently drops session knowledge | `process_chain_end/_10_surfsense_push.py` | Medium |
| 5 | SurfSense `create_space()` not idempotent | `python/helpers/cortex_surfsense_client.py` | Low |
| 6 | FAISS recall fires on trivial messages ("hi", "ok") | `message_loop_prompts_after/_15_temporal_memory.py` | Low |
| 7 | `challenge_level` 4.0 causes challenge-before-delivery (prompt design flaw) | `agents/cortex/prompts/agent.system.main.role.md` + `cortex_personality_model.py` | Medium |
| 8 | DirtyJson silently fixes LLM malformed output — agent never learns | All extraction code | Medium |
| 9 | Tool state appended to system prompt every turn (~100 tokens wasted) | `agents/cortex/extensions/system_prompt/_15_cortex_tool_state.py` | Low |

#### Architectural Improvements (beyond bugs)
- Add confidence scoring (0.0–1.0) to knowledge extraction facts — port from Jarvis vault schema
- Task-adaptive `challenge_level`: simple/factual=2.0, strategic=4.0, creative=3.0
- Delivery-first rule in reasoning protocol: deliver first, challenge after

### Source Code Available for Porting

#### From `C:\Users\Admin\omnis_workspace_VERDENT\omnis_ai\` (Python, direct port)
- `venture/dna.py` — VentureDNA: MarketIntelligence, CompetitorProfile, ICP, WebAsset, FrameworkScore
- `venture/creation_flow.py` — 5-phase state machine: INITIATION→EXPLORATION→SYNTHESIS→CRYSTALLIZATION→CONFIRMATION
- `venture/outcome_ledger.py` — OutcomeEvent, HITLLogEntry, KellySignal (SQLite-backed)
- `venture/self_optimizer.py` — TemplateVersion, OptimizationProposal, HITL gating, DSPy hookpoint
- `venture/venture_templates.py` — Archetypes: local_services, ecommerce, saas, trading, generic
- `core/autonomy_policy.py` — 5-level (0-4), ActionClass: READ/DRAFT/SCRAPE/SEND/SPEND/DEPLOY
- `modules/kelly_criterion_module.py` — Capital allocation, ProbabilityAssessment, EVCalculation
- `modules/README_NEGATIVE_KNOWLEDGE.md` — Epistemic foraging: learns from failures
- `core/h_mem.py` — H-MEM context compression
- `core/world_model.py` — SQLite schemas for user_profile, ventures, inferences
- **NOT portable:** LangGraph orchestration, FastAPI server, Next.js UI, Supabase calls

#### From Jarvis (https://github.com/vierisid/jarvis) — CONCEPTS ONLY (RSALv2 license, never copy code)
- Authority engine: 5-level decision cascade (temp grants → role overrides → context rules → numeric level → governed category)
- Vault schema: `facts` table with `confidence REAL DEFAULT 1.0`
- Approval patterns learning: auto-suggest trust elevation after N consecutive approvals
- OKR Goals: objective→key_result→milestone→task→daily_action, 0.0–1.0 score, health, escalation stages
- Content pipeline: idea→research→outline→draft→assets→review→scheduled→published
- UI reference: 10+ tabs (Dashboard, Goals, Workflows, Vault, Content, Multi-Agent, Approvals, Settings)

### Revised Phase C Scope (expanded from original plan)
Phase C now includes:
1. Port VentureDNA from Omnis + adapt for Agent Zero
2. Port 5-phase CreationFlow + adapt to Agent Zero tool system
3. Port OutcomeLedger (SQLite) + KellySignal capital allocation
4. Port AutonomyPolicy (5 levels) + adapt for Agent Zero hook system
5. Implement Authority Engine (Jarvis design, fresh Python) — 5-level cascade with audit trail
6. Add OKR Goals system (Jarvis design, fresh Python) — not in original plan, critical
7. Port SelfOptimizer + wire to OutcomeLedger (Phase D foundation)
8. Add VentureTypeTemplates (archetypes)

### Revised Roadmap
| Stage | What | Notes |
|-------|------|-------|
| **Stage 1** | 9 base fixes | Do first — clean foundation |
| **Stage 2** | Tests 2–7 + consciousness bidirectional proof | SurfSense push+pull, Graphiti, self-model |
| **Stage 3** | Port Venture Machine from Omnis + adapt for Agent Zero | 1 week |
| **Stage 4** | Port Authority Engine (Jarvis design, fresh Python) | 2-3 days |
| **Stage 5** | Add OKR Goals system (Jarvis schema, fresh Python) | 3-4 days |
| **Stage 6** | Self-optimization loop (outcome ledger → self-optimizer) | 1 week |
| **Stage 7** | Phase E: UI evaluation (Alpine.js sufficient? or React+Vite) | After Stage 6 |
| **Stage 8** | Phase F: Hardening, security audit, Fly.io deployment | Before commercial launch |

### Commercial Migration Path
Agent Zero is MIT licensed — can ship commercially as-is.
When ready for clean proprietary product: replace Agent Zero's ~300-line core agent loop with custom loop, keep all extensions/helpers/tools (already isolated), add own UI. Estimated effort: 1 week.

---

## Stage 1.5 Holistic Bug Fix (2026-03-25 — found during testing)

Critical bugs found during holistic flow test, all fixed same session:

- [x] **DeferredTask broken** — `_10_surfsense_push.py` and `_15_graphiti_update.py` used wrong constructor signature (`agent=, method=, args=, thread_group=` kwargs don't exist). They silently crashed on construction. Fixed: `DeferredTask(thread_name=...)` + `.start_task(func, *args)`
- [x] **Graphiti client wrong API** — `cortex_graphiti_client.py` used raw HTTP (`/v2/episodes`, `/v2/search`) which returned 404. Fixed: rewrote to use official `zep-cloud` SDK. Added `zep-cloud` to requirements.txt.
- [x] **Graphiti pull missing** — we pushed to Zep but never queried it. Added `_18_graphiti_pull.py` — semantic graph search injected into `extras_persistent["cortex_graph_memory"]` at every turn
- [x] **SurfSense search wrong** — documents/search endpoint doesn't find notes (our push format). Fixed `_search_space` to use title search. Also updated `_20_surfsense_pull.py` to use list_documents (which does include notes) instead of broken search endpoint.
- [x] **Credentials in git** — `agents/cortex/settings.json` was unprotected. Added to `.gitignore`.
- [x] **SurfSense search helper** — added `_extract_search_term()` and `_STOPWORDS` to `cortex_surfsense_client.py`

**Architecture clarification — L3 SurfSense role:**
SurfSense has NO vector/semantic search API for notes. Title search is ILIKE only.
- **L1 FAISS**: real-time semantic recall (entities/facts in per-session vector store) ← primary recall
- **L2 Graphiti/Zep**: temporal knowledge graph, semantic search via official SDK ← primary deep recall
- **L3 SurfSense**: document vault + cross-device persistence (push always, pull = recent docs list)

**Holistic test results (2026-03-25):**
- SurfSense B2 (auth): PASS — JWT token obtained
- SurfSense B3 (spaces): PASS — all 6 core spaces exist
- SurfSense B4 (push): PASS — doc pushed, id=38
- SurfSense pull (list): PASS — list_documents returns notes
- Graphiti health: PASS — Zep Cloud reachable via SDK
- Graphiti add_episode: PASS — episode ingested, confirmed processed
- Graphiti search: PASS — 2 results returned on semantic query

---

## Stage 1 Fix List
**Status:** COMPLETE — all 9 fixes shipped 2026-03-25

- [x] Fix 1: MCP env dict injection script → `python/helpers/cortex_env_sync.py`
- [x] Fix 2: Research tool JSON validation → `python/tools/cortex_research_tool.py` (_JSON_PARSE_ERROR sentinel)
- [x] Fix 3: Venture activation state persistence → `python/helpers/cortex_venture_activation.py` (save/load_state)
- [x] Fix 4: SurfSense push retry + exponential backoff → already existed; confirmed
- [x] Fix 5: SurfSense `create_space()` idempotency → handles HTTP 409, returns existing space
- [x] Fix 6: FAISS recall trivial-query gate → `_15_temporal_memory.py` (_TRIVIAL_PHRASES + _MIN_MESSAGE_LENGTH)
- [x] Fix 7: Delivery-first rule in `agent.system.main.role.md` → delivery-first/challenge-first distinction added
- [x] Fix 8: Task-adaptive `challenge_level` → `cortex_personality_model.py` + `_17_personality_model.py` (keyword classifier + per-turn override injection)
- [x] Fix 9: Tool state moved to `message_loop_prompts_after` → `agents/cortex/extensions/message_loop_prompts_after/_19_cortex_tool_state.py` (MD5 change-detection, ~100 token savings/turn)

---

## Phase C: Venture Machine
**Status:** NOT STARTED — Source code available in `C:\Users\Admin\omnis_workspace_VERDENT\omnis_ai\venture\`

Files to create (porting from Omnis + adding Jarvis authority engine + OKR goals):
- `python/helpers/cortex_venture_dna.py` — port from omnis `venture/dna.py`
- `python/helpers/cortex_venture_lifecycle.py` — port from omnis `venture/creation_flow.py`
- `python/helpers/cortex_outcome_ledger.py` — port from omnis `venture/outcome_ledger.py`
- `python/helpers/cortex_kelly_criterion.py` — port from omnis `modules/kelly_criterion_module.py`
- `python/helpers/cortex_authority_engine.py` — fresh Python from Jarvis authority design
- `python/helpers/cortex_goals_engine.py` — fresh Python from Jarvis OKR goals design
- `python/helpers/cortex_venture_templates.py` — port from omnis `venture/venture_templates.py`
- `python/tools/venture_create.py`
- `python/tools/venture_manage.py`
- `python/extensions/agent_init/_20_venture_loader.py`
- `python/extensions/monologue_start/_10_venture_state.py`

---

## Phase D: Meta-Intelligence
**Status:** NOT STARTED — Foundation: `cortex_self_optimizer.py` available in omnis `venture/self_optimizer.py`

---

## Phase E: UI Polish
**Status:** DEFERRED — Evaluate after Phase D
**Reference:** Jarvis UI (10+ tabs: Dashboard, Goals, Workflows, Vault, Content, Multi-Agent, Approvals, Settings)
**Target stack:** React 19 + Tailwind 4 (when ready to migrate from Agent Zero Alpine.js UI)

---

## Phase F: Hardening & Deployment
**Status:** NOT STARTED
