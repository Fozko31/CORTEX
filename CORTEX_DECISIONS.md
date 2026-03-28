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

---

## D-030 — Three-Pillar Framework: One System, Three Modes
**Date:** 2026-03-25
**Decision:** CORTEX operates as ONE system in three modes: Venture Creation (Phase C), Venture Discovery (Phase D), Venture Operations (Phase F). They share the same memory stack, CVS scoring engine, research infrastructure, and SurfSense spaces. What differs: who initiates the loop and how much human confirmation is required before execution.
**Rationale:** Building three separate systems would duplicate infrastructure and fragment memory. The unified system means Discovery candidates flow directly into Creation with no research wasted, and created ventures flow directly into Operations with full DNA context.

---

## D-031 — Phase D: Venture Discovery Replaces Old Phase D Meta-Intelligence
**Date:** 2026-03-25
**Decision:** Old Phase D (Meta-Intelligence: DSPy, self-optimization, SOUL.md) moved to Phase G (Self-Improvement Loop). Phase D is now Venture Discovery. Build order: C → D (Discovery) → E (Background Processes) → F (Operations) → G (Self-Improvement) → H (Full Autonomy).
**Rationale:** Discovery is the natural next capability after Creation. It extends Phase C infrastructure without new architectural dependencies. Self-improvement requires a proven, stable system to improve — that means waiting until Phase F delivers the Operations layer.

---

## D-032 — Venture Discovery: Interactive Parameter Session Before Autonomous Run
**Date:** 2026-03-25
**Decision:** Mode 2 (autonomous discovery) always preceded by Mode 1 (interactive parameter design session, ~10 minutes). User free-flows ideas → CORTEX iterates with quick research → crystallizes `VentureDiscoveryParameters` object. Parameters saved to disk, reused indefinitely until explicitly updated.
**Rationale:** Without tight parameters, autonomous discovery generates high-noise, low-value candidates. The 10-minute interactive session is not overhead — it multiplies the quality of every autonomous cycle that follows. Parameters define: market_domains, geography, min_cvs_score (default 45), min_ai_run_autonomy (default 50), max_capital_requirement, languages, excluded_domains.

---

## D-033 — Metrics Hierarchy: Two-Layer Architecture
**Date:** 2026-03-25
**Decision:** CORTEX operates with two metric layers simultaneously:
1. **Human-readable direction** (priority order): Profit → Automation → Growth → Exceptionalism. Hard constraints: never harm users, safety before automation, force of good.
2. **Machine-measurable KPIs** (tracked automatically in OutcomeLedger): revenue per venture/month, CVS score at creation vs 90d later, AI autonomy execution rate, discovery-to-creation conversion rate, Kelly fraction utilization, struggle detect rate trend.
**Rationale:** "Profit + growth" is too vague for machine optimization. But reducing everything to numbers loses the directional judgment needed for complex decisions. Both layers are necessary. Machine tracks KPIs, human tracks direction.

---

## D-034 — Autonomy Unlocking: Per-Decision-Type with Monitoring + Alerting
**Date:** 2026-03-25
**Decision:** Venture autonomy is unlocked per-decision-type, not per-venture globally. Process: CORTEX recommends → user observes pattern → user grants autonomy for that specific decision type → CORTEX executes autonomously + logs every decision → alert fires if deviation from established pattern exceeds threshold. `autonomy_level` field in VentureDNA tracks which decision types are autonomous.
**Rationale:** Global venture autonomy is too coarse. A venture might be safe to run pricing experiments autonomously but still require human confirmation on outreach copy. Per-decision-type unlocking matches how trust is actually earned and maintained.

---

## D-035 — Background Processes: Off-Hours Only, Session Mutex, Budget Capped
**Date:** 2026-03-25
**Decision:** All autonomous background processes run 1-6am CET by default. A session mutex prevents any background job from running while user session is active. Every job has a hard budget cap (e.g., $3.00/night for discovery). These three constraints are non-negotiable for all background processes.
**Rationale:** Off-hours avoids competing with user's active sessions for API quota. Session mutex prevents memory contamination and context confusion during active work. Budget cap prevents runaway spending from edge cases (infinite loops, bad parameters, API cost spikes).

---

## D-036 — Memory Backup: All Three Layers, Single Location, Automated
**Date:** 2026-03-25
**Decision:** All three memory layers backed up automatically:
- L1 FAISS: daily rsync → B2/OneDrive (`cortex-backups/l1_faiss/`)
- L2 Graphiti: weekly Zep export API → JSON → B2 (`cortex-backups/l2_graphiti/`)
- L3 SurfSense: daily pg_dump → compress → B2 (`cortex-backups/l3_surfsense/`)
All in single `cortex-backups/` directory. 30-day daily + 12-week weekly retention. Practically free (< $1/month storage).
**Rationale:** Memory is CORTEX's identity and competitive advantage. L1+L2+L3 together represent accumulated intelligence, temporal relationships, and session history. Loss of any layer is partial loss of identity. Automated backup is the system's lifeline.

---

## D-037 — Self-Improvement Loop: Memory Isolation Required Before Experiments
**Date:** 2026-03-25
**Decision:** Experiment runs write to `usr/memory/cortex_main_test/` namespace, NEVER to `usr/memory/cortex_main/`. Test namespace is wiped after every experiment. Implementation: `memory_ns="test"` flag in all memory write calls routes to test path. Isolation must be built (G-1) before any self-improvement experiment runs.
**Rationale:** If experimental CORTEX runs 30 test queries and writes to live memory, it contaminates production with synthetic test data. Live CORTEX then recalls test data as if real session history. This degrades real-world performance and corrupts the memory that makes CORTEX valuable. Memory isolation is a non-negotiable prerequisite for Phase G.

---

## D-038 — Self-Improvement Judge: DeepSeek Primary + Claude Spot-Check
**Date:** 2026-03-25
**Decision:** Judge pipeline for self-improvement experiments: DeepSeek V3.2 evaluates all outputs against rubric (~$0.001/evaluation). Claude Sonnet 4.6 cross-checks 10% of evaluations for calibration. Claude produces the final human-facing report.
**Rationale:** DeepSeek V3.2 at classification tasks is ~95% quality of Claude at ~7% the cost. For bulk evaluation of 30 test cases, this is the right model. Claude spot-checks prevent systematic DeepSeek errors from going undetected. Claude on the final report because the user reads it — never cut the user-facing synthesis step.

---

## D-039 — Test Suite Refresh: Monthly with Real Session Queries
**Date:** 2026-03-25
**Decision:** Self-improvement test suite refreshed monthly. Process: pull 30 real queries from past month's sessions (from SurfSense conversation space), remove duplicates, ensure coverage across query types, update rubric for new capability areas. Refresh cost: ~$0.10 (DeepSeek classification). Practically free.
**Rationale:** If test suite is never refreshed, CORTEX will overfit to the fixed 30 queries over many improvement cycles — performing better on tests but not on real user queries. Monthly refresh with actual session data keeps the test suite grounded in real usage.

---

## D-040 — DSPy: Phase G.1 for Full Loop, Early Use Possible Now
**Date:** 2026-03-25
**Decision:** DSPy (Stanford, open-source) integrated at Phase G.1 for automated prompt optimization (100+ variants searched vs 3 manual/week, same cost). But DSPy can be used NOW for standalone prompt optimization: pick one high-value prompt, write 10-15 good/bad examples, run DSPy, apply best result. No Phase G infrastructure required for early use.
**Rationale:** DSPy's full power requires a test suite + judge pipeline (Phase G). But the early standalone use case is valid and cheap — validates the approach before committing to the full infrastructure build. Good test candidate: CVS scoring prompt in venture_create, or the synthesis prompt in CortexResearchOrchestrator.

---

## D-041 — Auto-Git-Commit Before Any Autonomous File-Modifying Action
**Date:** 2026-03-25
**Decision:** Before any background process that modifies CORTEX files (experiments, prompt updates, knowledge file changes): (1) assert git is clean, (2) auto-commit with timestamp, (3) tag as `safe-YYYYMMDD-HHmm`. Runs automatically — not on user instruction. If experiment rejected: `git checkout` to tag restores files. Tags kept 90 days then cleaned.
**Rationale:** Every production-affecting change must have a restore point. The restore point must be automatic — requiring user to remember to commit is a failure mode. This is the git-branch-before-experiment pattern from karpathy/autoresearch, applied to CORTEX's self-modification safety model.
**Note:** Both sources use LangGraph. CORTEX uses Agent Zero extensions. Concepts and math port directly; orchestration logic must be rewritten for Agent Zero's hook system.

---

## D-042 — Research Cache: Venture-Type-Aware TTL + 9-Category User Display
**Date:** 2026-03-26
**Decision:** VentureDNA gets `research_expires_at` field set at creation based on venture_type:
crypto/AI tools/prediction markets=2 weeks, SaaS/marketplace=6 weeks, content/media=8 weeks,
physical/hardware/B2B=16 weeks. Cache stored in SurfSense DNA space. When cache exists, always
show status even within TTL. Display ALL 9 value categories: (1) time-sensitive facts, (2) research
gaps, (3) under-explored angles, (4) assumption challenges, (5) confidence weak spots, (6)
competitive landscape shifts, (7) potential new angles, (8) macro context shifts, (9) regulatory
status. User always gets 3 options: use cache / full refresh / targeted refresh. Incremental
refresh on expiry: user-initiated only — agent proactively alerts but never auto-runs.
**Rationale:** Maximum transparency + user control. Never block on expiry. Never hide cache use.
User can override any cached result even within TTL. Always chase maximum value.

---

## D-043 — Post-Synthesis Gap Analysis: Standing Feature of Every Synthesis
**Date:** 2026-03-26
**Decision:** After every venture synthesis (not just cached cases), the synthesis model outputs a
separate gap analysis block: (a) top angles not yet researched that could change CVS scores,
(b) "if you researched X, confidence on [dimension] would improve from Y% to ~Z%", (c) key
uncertainties resolving over time, (d) related markets worth exploring, (e) questions user could
answer that would sharpen the analysis. This runs ALWAYS — it is not optional, not gated on
user request.
**Rationale:** Synthesis model has maximum context simultaneously (full research, user goals,
CVS scores, conversation history). This is the best moment to identify what's missing. Finding
this information AFTER synthesis costs nothing extra and adds permanent value.

---

## D-044 — venture_create: prior_research Parameter for Context Injection
**Date:** 2026-03-26
**Decision:** Add `prior_research: str` parameter to venture_create tool. When agent has already
run research in the conversation, it passes the FULL synthesis JSON — not a summary. venture_create
skips Tier 1 API calls but still runs analyze_gaps on it. Quality is identical to running Tier 1
because it is literally the same data. Do NOT use description field for this — it gets truncated.
**Rationale:** When agent does extensive research in conversation then calls venture_create, the
tool currently re-runs Tier 1 independently, wasting cost and time. Context injection via dedicated
parameter solves this with zero quality sacrifice.

---

## D-045 — TTS: Kokoro Local Primary, Inworld AI Fallback
**Date:** 2026-03-26
**Decision:** Primary TTS = Kokoro (local, CPU, free, private — no data leaves machine). Latency
~10-15s on CPU acceptable for async Telegram use. Fallback = Inworld AI at $10/1M chars if
real-time latency required and cloud privacy tradeoff accepted. Do NOT use Edge TTS (Microsoft
servers). Do NOT use ElevenLabs (overkill/expensive).
**Rationale:** Privacy concern — cloud TTS sends all spoken text to provider servers including
venture strategy content. Local inference is the principled default for CORTEX's sensitive data.

---

## D-046 — STT: Deepgram + DeepSeek v3.2 Cleanup (Telegram); faster-whisper Local (Privacy Mode)
**Date:** 2026-03-26
**Decision:** For Telegram voice interface (Phase F): Deepgram Nova-2 ($0.0043/min) for
transcription + DeepSeek V3.2 for cleanup (removes false starts, filler words, word-search
attempts, formats output). For full privacy: faster-whisper running locally (no audio leaves
machine) + DeepSeek cleanup. Deepgram wins over Groq Whisper on accuracy for conversational
speech. Built-in Deepgram features (filler detection, smart formatting) reduce LLM cleanup load.
Desktop STT: keep Wispr Flow ($12/month annual) until Phase F Telegram voice is built — its
context awareness (reads active app, reformats accordingly) and command mode are not worth
DIY-ing. Re-evaluate after Phase F.
**Rationale:** Deepgram is purpose-built for STT, more accurate per dollar than Whisper for
conversational speech. faster-whisper as privacy alternative since audio is sensitive.
