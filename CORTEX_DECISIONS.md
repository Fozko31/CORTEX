# CORTEX — Architecture Decisions Log

**Last Updated:** 2026-03-25

All key decisions made during CORTEX development. Each entry has context, the decision made, and the rationale.

---

## D-001 — Extension System: Zero Core Modifications
**Date:** 2026-03-23
**Decision:** All CORTEX customization through Agent Zero's extension system. No modifications to Agent Zero core files.
**Rationale:** Upstream mergeability. Agent Zero is actively developed. Patching core files would create a permanent maintenance burden.

---

## D-002 — Zep + Instructor Replaced with DirtyJson + JSON Files
**Date:** 2026-03-23
**Decision:** Dropped Zep (temporal memory SDK) and Instructor (structured LLM output) for Phase A2. Replaced with DirtyJson parsing + JSON file persistence in `usr/memory/cortex_main/`.
**Rationale:** No new dependencies needed. FAISS already integrated. JSON files are transparent and inspectable. Zep moved to Phase B (Graphiti) where it adds genuine graph value.

---

## D-003 — FAISS vs SurfSense Role Split
**Date:** 2026-03-23
**Decision:** FAISS = fast local L1 (entities, facts, per-session recall). SurfSense = cross-device L3 consciousness (session summaries, cross-venture patterns). They are additive, not competing.
**Rationale:** FAISS is already integrated, <10ms latency, offline-capable. SurfSense adds the long-horizon cross-device awareness layer that FAISS cannot provide.

---

## D-004 — UI Strategy: Alpine.js First, Next.js Deferred
**Date:** 2026-03-23
**Decision:** Extend Alpine.js UI progressively through Phases A-D. Defer Next.js rewrite to optional Phase E.
**Rationale:** Alpine.js is component-based, store-driven, and already working. Rewriting to Next.js early is high-cost/low-value. Revisit after Phase D if Alpine.js hits hard limits.

---

## D-005 — Hook Mapping Corrections (Critical)
**Date:** 2026-03-23
**Decision:** Corrected extension hook assignments from the original plan:
- SurfSense context pull: `message_loop_prompts_after/_20_` (not monologue_start)
- Entity extraction: `monologue_end/_10_` (not message_loop_end)
- Venture state: `monologue_start/_10_` (confirmed)
- SurfSense push: `process_chain_end/_10_` (not monologue_end)
**Rationale:** Derived from actual code analysis of Agent Zero core (`_50_recall_memories.py` etc.), not from documentation.

---

## D-006 — SurfSense httpx JSON Serialization
**Date:** 2026-03-24
**Decision:** Use `json=payload` parameter in httpx POST calls (not `content=json.dumps(payload)`).
**Rationale:** httpx `content=` sends raw bytes without setting Content-Type: application/json. SurfSense FastAPI backend returns 422 Unprocessable Entity. Using `json=` parameter sets correct headers and serializes automatically. Confirmed working in B4 test.

---

## D-007 — Research Tier Architecture
**Date:** 2026-03-24
**Decision:** Two-tier research model:
- **Tier 1:** Tavily + Exa, multi-query, deduplicated sources → Claude synthesizes. Cost: ~$0.01-0.03/run.
- **Tier 2:** Tier 1 + Perplexity with Tier 1 findings as context input. Hard cap $0.50/run via OpenRouter.
- Claude Sonnet 4.6 is always the final synthesis engine (never replaced by Perplexity).
**Rationale:** Tier 1 covers 90%+ of research needs. Tier 2 adds deep reasoning on top of grounded sources. Cost cap prevents runaway Perplexity spend. Claude synthesizes because it's the main agent model — no context switching.

---

## D-008 — RFC Replacement: Full Tool Umbrella
**Date:** 2026-03-24
**Decision:** RFC (the old localhost-based tool execution path) was the umbrella for all tool use, not just search. The replacement is a complete tool-use umbrella covering:
1. Tool awareness/inventory (`CortexToolRegistry`)
2. Tool selection/routing (`cortex_tool_router.py`, routing table in role.md)
3. Execution adapters (4 API clients + MCP configs + Composio)
4. Specialized orchestration (research orchestrator, later others)
5. Venture-scoped activation (`CortexVentureActivation`)
**Rationale:** RFC cannot run in production (localhost:* dependency). The replacement must be fully cloud-native and API-based.

---

## D-009 — GitHub PAT Type: Fine-Grained Over Classic
**Date:** 2026-03-24
**Decision:** Use fine-grained personal access token (not classic PAT, not GitHub Copilot key).
**Rationale:** Fine-grained tokens are scoped per-repo and per-permission (Contents + Issues + Pull requests: Read-only). Classic tokens are broader and harder to audit. Copilot key is for model access (AI completions), not repository operations.

---

## D-010 — Browserbase as Fallback, Not Primary
**Date:** 2026-03-24
**Decision:** Browserbase is a cloud browser fallback, not a primary scraping tool. Routing: Firecrawl first → Browserbase only if JS-heavy / login-gated / CAPTCHA / blocked.
**Rationale:** Firecrawl handles static + semi-dynamic pages at lower cost. Browserbase handles the hard cases (interactive pages, auth walls). Complementary, not redundant.

---

## D-011 — MCP env Dict Must Be Populated Explicitly
**Date:** 2026-03-25
**Decision:** MCP subprocess env vars must be explicitly populated in `usr/settings.json` mcp_servers env dict. They are NOT inherited from `usr/.env`.
**Rationale:** MCP SDK `stdio_client()` calls `get_default_environment()` which only returns OS-level vars (PATH, APPDATA, etc.), not custom .env keys. Merge is `{**get_default_environment(), **server.env}`. Empty string in server.env overrides any inherited value. Solution: script to read PAT from .env and inject into settings.json env dict at setup time.

---

## D-012 — Port: 5000 Default, Not 50001
**Date:** 2026-03-25
**Decision:** CORTEX now runs on `localhost:5000` (the Agent Zero default). Port 50001 is no longer hardcoded.
**Context:** `run_ui.py` reads port from: `get_arg("port")` → `WEB_UI_PORT` env var → `5000` fallback. `WEB_UI_PORT` is not set in `usr/.env`, so it defaults to 5000.
**Impact:** No production code references `50001` — verified by codebase search. `test_websocket_csrf.py` references `localhost:5000` (test fixtures only, not production). Safe to remain at 5000 or set `WEB_UI_PORT=50001` in `usr/.env` to restore.

---

## D-013 — langchain Import Migration
**Date:** 2026-03-25
**Decision:** Migrate all `from langchain.*` imports to `from langchain_core.*` or `from langchain_text_splitters.*`.
**Context:** `requirements.txt` pins `langchain-core==0.3.49` and `langchain-community==0.3.19` but NOT the monolithic `langchain` package. The monolithic `langchain` stops at version 0.3.28 — version 0.3.49 does not exist. The codebase had two files using old monolithic imports.
**Files changed:**
- `python/helpers/call_llm.py` — `langchain.prompts` + `langchain.schema` → `langchain_core`
- `python/helpers/document_query.py` — `langchain.schema` + `langchain.text_splitter` → `langchain_core` + `langchain_text_splitters`
- `requirements.txt` — added `langchain-text-splitters>=0.0.1` + `litellm>=1.0.0`

---

## D-014 — Venture Pack Model
**Date:** 2026-03-24
**Decision:** 6 named packs that activate tool subsets per venture context: `core`, `market_research`, `product_dev`, `content`, `operations`, `fundraising`. One active pack at a time. Composio entity_id scoped per venture for isolation.
**Rationale:** Prevents tool bleeding between ventures. Reduces system prompt length by only advertising relevant tools. Makes context-switching explicit and auditable.

---

## D-015 — challenge_level Default: 4.0/5
**Date:** 2026-03-23
**Decision:** CORTEX personality `challenge_level` defaults to 4.0 (out of 5), meaning "challenging" not "agreeable".
**Rationale:** CORTEX is a business partner, not an assistant. It should push back on vague questions, challenge assumptions, and demand clarity. This is consistent with the COO identity.
**Observable effect:** Agent challenged the "AI founder productivity tools" question framing before researching it (Test 1 behavior was correct).

---

## D-016 — Memory Architecture Final: L1/L2/L3 Role Split
**Date:** 2026-03-25
**Decision:** Three layers with distinct roles:
- L1 FAISS: semantic embedding recall, per-turn extraction, local files → `usr/memory/cortex_main/`
- L2 Graphiti/Zep: temporal knowledge graph, semantic search via official `zep-cloud` SDK, per-turn episode ingestion
- L3 SurfSense: document vault + cross-device archival, push every 20 exchanges, pull = recent docs list (NOT semantic)
**Rationale:** SurfSense has no vector/semantic search API for notes — its semantic search is internal to its chat UI only. Semantic recall = L1+L2. L3 = archival and cross-device persistence only.
**Critical:** SurfSense push fires every 20 exchanges (not every turn). L1+L2 fire every turn — no knowledge is ever lost.

---

## D-017 — FAISS → Supabase pgvector for Cloud Deployment
**Date:** 2026-03-25
**Decision:** FAISS stays for local dev. When deploying to Fly.io, replace with Supabase pgvector. User already has Supabase account and API key.
**Rationale:** FAISS writes to local disk — not viable on ephemeral Fly.io containers. Supabase pgvector is a drop-in semantic replacement, free tier handles millions of vectors.
**Action needed:** Migration when Fly.io deployment starts (Phase H prep).

---

## D-018 — Zep Cloud: Managed Now, Self-Hosted Later
**Date:** 2026-03-25
**Decision:** Use Zep Cloud (managed) for all development and initial launch. Evaluate self-hosted Graphiti (open-source + Neo4j on Fly.io) when commercial launch requires data sovereignty.
**Rationale:** Managed is faster and zero-ops. Self-hosted adds privacy but maintenance burden. Revisit when commercial product needs data sovereignty guarantees.

---

## D-019 — Model Router: Summarization/Digest → DeepSeek V3.2
**Date:** 2026-03-25
**Decision:** Changed `summarization` and `digest` tasks from Claude Sonnet 4.6 ($3.00/$15.00 per M) to DeepSeek V3.2 ($0.26/$0.38 per M). ~92% cost reduction on background tasks.
**Rationale:** Session summaries and digests are background structured extraction — user never sees them directly. Claude Sonnet stays ONLY for user-facing final synthesis (research step). DeepSeek V3.2 delivers 95%+ quality on structured summarization at a fraction of the cost.
**Rule:** Never optimize the final synthesis step. It's the money step.

---

## D-020 — Minimax 2.7: Reserved for Phase D Multi-Agent
**Date:** 2026-03-25
**Decision:** Minimax 2.7 not integrated now. Noted as strong candidate for multi-agent tool use orchestration in Phase D when CORTEX spawns parallel venture sub-agents.
**Rationale:** Minimax 2.7's strength is agentic/tool-use capabilities. No clean fit in current single-agent architecture. Phase D (venture agents) is the right integration point.

---

## D-021 — Goal Structure: Master Goals + Per-Venture Goals
**Date:** 2026-03-25
**Decision:** Two-level goal structure:
1. CORTEX master goals: system-wide (revenue targets, leverage goals, overarching mission)
2. Per-venture goals: discovered conversationally through VentureDNA creation flow (not form-filled)
**Both levels feed into every CORTEX response.** Goals are discovered through dialogue, not typed in.
**Architecture:** Master goals in `cortex_self_model.py`. Per-venture goals in VentureDNA (Phase C). OKR system in Phase D/E connects both.
**Rationale:** User correctly identified both levels as necessary. Venture goals without master goals = no coherent direction. Master goals without venture goals = no execution context.

---

## D-022 — Positive Reinforcement Mechanism (Phase G)
**Date:** 2026-03-25
**Decision:** When user confirms value ("that worked", "we made money on that"), knowledge extractor tags this as a success signal → stored in self-model → self-model tracks which approaches/frameworks produce confirmed value → feeds back into identity framing.
**Rationale:** Creates functional behavioral adaptation without model fine-tuning. Over time, CORTEX knows what works for this specific user. This is the feedback loop that makes identity feel like genuine motivation.
**Implementation:** Extend knowledge extractor schema with `SuccessSignal` type. Store in self-model's `outcome_history`. Feed into system prompt dynamic context.

---

## D-023 — Quasi-Consciousness Architecture
**Date:** 2026-03-25
**Decision:** CORTEX's quasi-consciousness is defined by four components: (1) self-model, (2) world model (Graphiti), (3) persistent goal structure (OKR system), (4) feedback loop (success signals). All four required for the identity to feel genuinely motivated rather than instructed.
**NOT consciousness in the philosophical sense.** Functionally: domain-specific accumulated intelligence that deepens with use.
**Path:** Phase C (venture data) → Phase D (goals + authority) → Phase G (self-optimization + feedback loop) → quasi-AGI for specific ventures.

---

## D-024 — Commercial Product Strategy
**Date:** 2026-03-25
**Decision:** Personal CORTEX (full build) ≠ Commercial CORTEX (Jarvis variant).
- Personal: phone-first, Telegram/mobile, maximum autonomy, full venture machine
- Commercial: desktop-first, business partner overlay, advisory mode, dialed-down autonomy
**Ruflo:** Used via MCP for personal CORTEX orchestration. NOT a hard dependency in commercial build — core CORTEX stack (FAISS/Graphiti/SurfSense/research tools) must work independently.
**Rationale:** User doesn't want to give commercial customers the full personal competitive advantage.

---

## D-025 — Telegram as First Mobile Interface
**Date:** 2026-03-25
**Decision:** Telegram integration (Phase E) is the first mobile-first interface. WhatsApp deferred (more complex setup). Voice deferred until after Telegram works.
**Feature set:** Text in/out, image in (user photographs documents), agent sends screenshots when stuck, slash commands (/think, /status, /new), decision requests with visual context.
**Rationale:** Telegram bot API is clean and well-documented. Enables phone-first operation without building a mobile app. Free STT/TTS to be evaluated when voice is added (Phase F).

---

## D-026 — SurfSense Title Format: Natural Language, Keyword-Rich
**Date:** 2026-03-25
**Decision:** SurfSense document titles use natural language format: `{Label} {date}: {topic}`. No slugification. No 60-char cap. Cap at 220 chars (safe for any PostgreSQL TEXT/VARCHAR). Conversation docs use top 8 topics (was 3). Outcome/knowledge docs use first 180 chars of content (was 40).
**Rationale:** SurfSense never returns note body content via any REST API endpoint (confirmed by testing single-document endpoint). Title is the ONLY keyword-searchable field. Natural language titles with amounts (€29), names (SSMB), and context are dramatically more searchable than slugified 84-char titles.

---

## D-027 — SurfSense Pull: 3 Spaces, 10 Docs, Keyword Scoring, Top 5
**Date:** 2026-03-25
**Decision:** Pull from up to 3 spaces (was 2), fetch 10 docs per space (was 3), score all 30 by keyword overlap with current query, return top 5 relevant docs. If no keyword overlap, fall back to top 3 by recency.
**Rationale:** Space routing was already good (keyword + LLM classification). The gap was that within each space, docs were returned purely by recency. Keyword scoring on titles gives relevance ordering. Zero additional API cost (all REST GETs against self-hosted SurfSense). SurfSense on Fly.io will remain free-per-call (infrastructure cost only ~$5-8/month).

---

## D-028 — Venture Spaces: Two Separate Spaces Per Venture
**Date:** 2026-03-25
**Decision:** Each venture gets TWO SurfSense spaces:
- `cortex_venture_{name}_dna` — creation/evolution chat: goals, research, connected accounts, pivots
- `cortex_venture_{name}_ops` — operations chat: daily work, results, images, PDFs
**Rationale:** DNA = what the venture IS (structured, versioned). Ops = what's HAPPENING (operational log). Different retrieval semantics. Safety gate: credentials/API keys stored locally only, never pushed to SurfSense — spaces store a reference ("Stripe connected: yes") not the token itself.
**Implementation:** Phase C will wire active venture context to push tagging.

---

## D-029 — Phase C Source: omnis_workspace_VERDENT + omnis_v12_JARVIS
**Date:** 2026-03-25
**Decision:** Phase C Venture Machine ported from two sources:
1. `C:\Users\Admin\omnis_workspace_VERDENT\omnis_ai\venture\` — direct port of VentureDNA, lifecycle, outcome ledger, creation flow, productization, epistemic idle loop, feedback loop
2. `C:\Users\Admin\omnis_v12_JARVIS\omnis_ai\modules\kelly_mathematical_framework.py` — Kelly Criterion capital allocation (pure math, fully portable)
3. CVS scoring formula from `omnis_v12_JARVIS\omnis_ai\modules\omnis_fractal_productization_module.py`
**Key files in VERDENT:** dna.py, creation_flow.py, creation_prompts.py, outcome_ledger.py, productization.py, epistemic_idle_loop.py, feedback_loop.py, self_optimizer.py, venture_templates.py
**Note:** Both sources use LangGraph. CORTEX uses Agent Zero extensions. Concepts and math port directly; orchestration logic must be rewritten for Agent Zero's hook system.
