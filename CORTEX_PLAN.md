# CORTEX — Refined Implementation Plan (Code-Verified)

**Status:** Plan Finalized — Ready to Build  
**Date:** 2026-03-23  
**Foundation:** Agent Zero fork (`C:\Users\Admin\CORTEX`)  
**Reference:** `C:\Users\Admin\CORTEX-Ruflo` (OMNIS + research docs — DO NOT MODIFY)  
**Verified Against:** Actual Agent Zero source code (all paths, interfaces, hooks confirmed)

---

## 1. Architecture Overview

CORTEX is built **entirely through Agent Zero's extension system** — no core modifications needed. All customization flows through 24 async hook points, per-profile agent configs, and the existing tool/MCP infrastructure.

### System Layers

```
[Agent Zero Core — Unmodified]
  Agent Loop & LLM Router | FAISS Memory | Built-in Tools | MCP Client+Server | Alpine.js UI | Scheduler

[CORTEX Extensions Layer]
  Identity (_05_) | Memory/Knowledge (monologue_end, prompts_after) | SurfSense (process_chain_end) | Venture (agent_init, monologue_start) | Meta-Intelligence (tool_execute_after)

[Venture Profiles (agents/)]
  agents/cortex/ | agents/venture_etsy_lunar/ | agents/venture_saas_x/

[External Services]
  Zep/Graphiti (Temporal KG) | SurfSense (Consciousness) | Composio (Tool Integrations) | Ruflo (Swarm Coordination)
```

---

## 2. Critical Corrections from Code Analysis

### 2a. `_context.md` / `agent.json` Context Field

| What the old plan assumed | What the code actually does |
|---|---|
| VentureDNA stored in `_context.md`, injected into the venture agent's own system prompt | `_context.md` is backward-compat for `agent.json`'s `context` field. It is read by the **parent/calling agent** via `call_subordinate` tool. It is **NOT** injected into the subordinate's own system prompt. |

**Correct pattern:**
- `agent.json` → `context` + `description` describe the venture **to the orchestrator**
- `prompts/agent.system.main.role.md` → Defines the venture agent's **own identity and VentureDNA**
- `settings.json` → Override model, memory subdir, knowledge subdir, MCP servers per venture

### 2b. Extension Hook Mapping Corrections

| Feature | Correct Hook | Reason |
|---|---|---|
| SurfSense context pull | `message_loop_prompts_after/_20_` | Where recall actually happens (see `_50_recall_memories.py`) |
| Entity/fact extraction | `monologue_end/_10_` | Fires once after full response |
| Venture state loading | `monologue_start/_10_` | Fires once at conversation start |
| SurfSense push | `process_chain_end/_10_` | End of chain; `data` kwarg is empty, must read from `self.agent` |

### 2c. UI Strategy

**Extend Alpine.js** progressively during Phases A-D. Next.js deferred to optional Phase E only if Alpine.js hits hard limits. The Alpine.js UI is component-based, store-driven, with auto-discovered API endpoints.

---

## 3. Extension Interface Reference

```python
from python.helpers.extension import Extension

class MyCortexExtension(Extension):
    async def execute(self, **kwargs) -> None:
        # self.agent → Agent instance
        # Modify state via: mutate kwargs in-place, self.agent.set_data(), self.agent.context.*
        pass
```

**File naming:** `_NN_description.py` — execution order is alphabetical. Gaps of 5-10 between numbers.

---

## 4. Venture-as-Agent Architecture

```
agents/venture_etsy_lunar/
├── agent.json                  # For orchestrator: when to call this agent
├── settings.json               # agent_memory_subdir, agent_knowledge_subdir, mcp_servers
├── prompts/
│   ├── agent.system.main.role.md    # Venture's own identity (VentureDNA)
│   └── agent.system.main.communication.md
├── extensions/                 # Optional per-venture hooks
└── knowledge/                  # Preloaded into its own FAISS index
```

**Isolation:** `agent_memory_subdir` → separate FAISS at `usr/memory/<name>/`. `agent_knowledge_subdir` → separate knowledge at `usr/knowledge/<name>/`.

---

## 5. Phase Plan

### Phase 0: Setup, Verification & Decision Gates

**PowerShell Commands:**
```powershell
cd C:\Users\Admin\CORTEX
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
New-Item -ItemType Directory -Force -Path usr
Set-Content -Path usr/.env -Value "API_KEY_OPENROUTER=YOUR_KEY"
python run_ui.py --port 50001
```

**Verify in UI:**
1. Settings → Agent: chat model = `openrouter` / `anthropic/claude-sonnet-4.6`
2. Settings → Agent: utility model = `openrouter` / `google/gemini-3-flash-preview`
3. Settings → Agent: embedding = `huggingface` / `sentence-transformers/all-MiniLM-L6-v2`
4. Chat test: "Hello, who are you?"
5. Memory test: save + recall across chats

**Decisions:** Zep for temporal memory (start simple), Extend Alpine.js UI, Corrected hook mappings.

---

### Phase A1: CORTEX Identity

**Files:**
- `agents/cortex/agent.json` — profile definition
- `agents/cortex/settings.json` — `{"agent_memory_subdir": "cortex_main"}`
- `agents/cortex/prompts/agent.system.main.role.md` — COO personality, bilingual, structured response format
- `agents/cortex/prompts/agent.system.main.communication.md` — enhanced thinking process
- `agents/cortex/prompts/agent.system.tool.response.md` — response formatting
- `python/extensions/system_prompt/_05_cortex_identity.py` — dynamic context injection (trust, ventures, commitments)

**Verify:** Set profile to "cortex" in settings. 10-turn conversation. Memory at `usr/memory/cortex_main/`.

---

### Phase A2: Memory & Knowledge Foundation

**Status:** CODE COMPLETE 2026-03-24

**Decision:** Zep and Instructor replaced with DirtyJson + JSON file persistence. No new dependencies. FAISS used for entity/fact storage (fast local recall). JSON files in `usr/memory/cortex_main/` for structured singletons (trust, personality, commitments).

**Helpers built:**
- `python/helpers/cortex_knowledge_extractor.py` — utility LLM extraction → entities, facts, commitments, user prefs via DirtyJson
- `python/helpers/cortex_trust_engine.py` — per-domain trust scores (6 domains, 0.0–1.0), JSON persistence
- `python/helpers/cortex_personality_model.py` — 6-dimension personality model, nudge-based updates, JSON persistence
- `python/helpers/cortex_commitment_tracker.py` — promise/task/reminder tracking with overdue detection, JSON persistence

**Extensions built:**
- `python/extensions/monologue_end/_10_knowledge_extraction.py` — background extraction after each turn; entities/facts → FAISS FRAGMENTS; updates personality + commitment files
- `python/extensions/message_loop_prompts_after/_15_temporal_memory.py` — FAISS recall → `extras_persistent["cortex_knowledge"]`
- `python/extensions/message_loop_prompts_after/_17_personality_model.py` — loads personality + commitments → `extras_persistent`; updates `agent.set_data`
- `python/extensions/system_prompt/_07_trust_level.py` — refreshes trust from file → `agent.set_data` after `_05_` runs

**Updated:**
- `python/extensions/system_prompt/_05_cortex_identity.py` — `_ensure_data_loaded()` lazy-loads all data from files on first call

**Profile check fix (critical):** All extensions use `agent.config.profile` (not `agent_profile`) — corrected from code analysis of `_15_load_profile_settings.py`.

**SurfSense relationship:** FAISS is the correct local storage. SurfSense (Phase B) is ADDITIVE — push higher-level events, not a replacement for entity/fact FAISS storage.

**No new deps needed.**

---

### Phase B: Consciousness Layer (SurfSense + Graphiti)

**Status:** CODE COMPLETE 2026-03-24

**Vision:** Three-layer memory architecture. SurfSense = quasi-consciousness (two-way street, meta-layered, cross-device, multi-source). Graphiti = temporal knowledge graph (entity relationships over time). FAISS stays as fast local layer. All three serve different purposes and all three are required.

**SurfSense facts (confirmed from live API analysis):**
- Backend port: **8929**. Frontend: **3929**. No conflict with CORTEX (50001).
- Auth: JWT Bearer (`POST /auth/jwt/login` → token)
- Push content: `POST /api/v1/documents` with `search_space_id`
- Pull/search: `GET /api/v1/documents/search`
- Search spaces are **flat** (no native nesting) — CORTEX designs its own meta-layer
- No SDK — use `httpx` directly

**Cost-Optimized Model Routing (verified OpenRouter slugs 2026-03-24):**

| Task | Model | Slug | Input $/M | Output $/M |
|---|---|---|---|---|
| Knowledge extraction | Gemini 3.1 Flash Lite | `google/gemini-3.1-flash-lite-preview` | $0.25 | $1.50 |
| Classification/routing | DeepSeek V3.2 | `deepseek/deepseek-v3.2` | $0.26 | $0.38 |
| Session summarization | Claude Sonnet 4.6 | `anthropic/claude-sonnet-4.6` | $3.00 | $15.00 |
| Weekly digest | Claude Sonnet 4.6 | `anthropic/claude-sonnet-4.6` | $3.00 | $15.00 |

Background cost per session: ~$0.003-0.005 (down from ~$0.15 without routing).

**Smart Search Space Structure (CORTEX-designed meta-layer):**
```
cortex_user_profile      ← preferences, personality evolution, trust history
cortex_conversations     ← session summaries pushed after each conversation
cortex_knowledge         ← extracted facts, research, general intelligence
cortex_outcomes          ← decisions made, ROI tracked, results logged
cortex_weekly_digest     ← scheduler-generated weekly summaries
cortex_cross_venture     ← patterns/lessons across all ventures
cortex_venture_[name]    ← one space per active venture
```

**4-Tier Retrieval Architecture:**
- Tier 0: Space Routing Index (local JSON, ~200 tokens) — FREE, always loaded
- Tier 1: Space Summaries (~500 tokens each, local cache) — FREE, on demand
- Tier 2: Semantic search in 1-3 spaces via SurfSense API — ~$0.001
- Tier 3: Full document retrieval — ~$0.01 (only for explicit "deep dive" requests)

**Standardized Ingestion Schema (non-negotiable, homogeneous):**
All documents use: `{title, content, metadata: {source, venture, category, confidence, temporal, summary_level, tags, session_id, entity_refs}}`
Title format: `[category]_[YYYY-MM-DD]_[topic-slug]`

**Meta-Awareness Self-Model (AGI foundation):**
CORTEX maintains `cortex_self_model.json` with: capability_registry, knowledge_map, knowledge_gaps, learning_trajectory, performance_history. Loaded at session start, updated after each push. Injected into system prompt so CORTEX knows its own capabilities and limitations.

**Push triggers:** Session end + every 20 exchanges (safety net). Graceful degradation with local queue if SurfSense unreachable.

**Three memory layers:**
| Layer | Technology | What it stores | Latency |
|---|---|---|---|
| L1 | FAISS | Fast local entities/facts, per-session recall | <10ms |
| L2 | Graphiti (Zep) | Temporal graph: entity→relationship→time chains | ~50ms |
| L3 | SurfSense | Cross-device consciousness, 25+ connectors, weekly summaries | ~200ms |

**Helpers built:**
- `python/helpers/cortex_model_router.py` — task→model mapping, OpenRouter slugs, cost tracking, direct litellm calls
- `python/helpers/cortex_ingestion_schema.py` — schema validation, title generation, content classification via DeepSeek V3.2
- `python/helpers/cortex_surfsense_client.py` — JWT auth, push, search, space management, offline queue, citation extraction
- `python/helpers/cortex_surfsense_router.py` — Tier 0 index, keyword + LLM-based routing for push and search
- `python/helpers/cortex_session_summarizer.py` — Claude Sonnet 4.6 session→structured summary with outcomes/knowledge
- `python/helpers/cortex_graphiti_client.py` — Zep/Graphiti wrapper for temporal graph (add_episode, search, entity_history)
- `python/helpers/cortex_self_model.py` — self-knowledge: capabilities, knowledge map, gaps, learning trajectory
- `python/helpers/cortex_weekly_digest.py` — periodic consolidation, cross-venture analysis, index refresh

**Extensions built:**
- `python/extensions/monologue_start/_05_self_model_load.py` — loads self-model + Tier 0 index at session start
- `python/extensions/message_loop_prompts_after/_20_surfsense_pull.py` — 4-tier retrieval → inject `extras_persistent["cortex_consciousness"]`
- `python/extensions/monologue_end/_15_graphiti_update.py` — forward extracted entities to Graphiti L2
- `python/extensions/monologue_end/_60_struggle_detect.py` — detect hedging/uncertainty → flag knowledge gaps
- `python/extensions/process_chain_end/_10_surfsense_push.py` — session end → summarize → route → push to SurfSense L3

**Updated:**
- `agents/cortex/settings.json` — added SurfSense/Graphiti/routing settings
- `python/extensions/system_prompt/_05_cortex_identity.py` — injects self-model summary into system prompt

**Local Docker setup (dev):**
```bash
# WSL2 or Linux machine:
git clone https://github.com/MODSetter/SurfSense && cd SurfSense && docker compose up
# Backend: http://localhost:8929   Frontend: http://localhost:3929
```

**Fly.io production:**
- `cortex-agent.fly.dev` ← CORTEX (Agent Zero fork)
- `cortex-surfsense.fly.dev` ← SurfSense (FastAPI + Next.js + PostgreSQL)
- `cortex-omnis.fly.dev` ← Ruflo/Omnis
- Private networking via `.internal` addresses (zero latency between services)

**Settings:** `cortex_surfsense_url`, `cortex_surfsense_username`, `cortex_surfsense_password`, `cortex_graphiti_url`, `cortex_graphiti_api_key`, `cortex_push_interval_exchanges`, `cortex_daily_cost_limit`, `cortex_proactive_level`, `cortex_pull_max_tokens`, `cortex_pull_tier3_max_tokens`

---

### Phase C: Venture Machine

**Status:** IN PROGRESS (2026-03-25)

**Source references (DO NOT MODIFY):**
- `C:\Users\Admin\omnis_workspace_VERDENT\omnis_ai\venture\` — VentureDNA, creation_flow, outcome_ledger, discovery, epistemic_idle_loop, etc.
- `C:\Users\Admin\omnis_v12_JARVIS\omnis_ai\modules\kelly_mathematical_framework.py` — Kelly Criterion math
- `C:\Users\Admin\omnis_v12_JARVIS\omnis_ai\modules\omnis_fractal_productization_module.py` — CVS scoring
- NOTE: Both sources use LangGraph. CORTEX runs LangGraph INSIDE Agent Zero tool calls as a Python library — Agent Zero is the conversational shell, LangGraph is the execution engine. No rewrite of orchestration needed; just port concepts + math and wrap in Agent Zero tool interface.

---

#### C Architecture: Key Design Decisions

**LangGraph inside Agent Zero tools (approved):**
- Agent Zero tool calls `venture_create.py` → tool instantiates + runs a LangGraph state machine
- LangGraph handles the multi-turn iterative state (INITIATION → EXPLORATION → SYNTHESIS → CRYSTALLIZATION → CONFIRMATION)
- Agent Zero handles all user conversation, memory, and routing
- Phase H transition: replace Agent Zero wrapper with direct FastAPI/Telegram interface, keep LangGraph + memory stack unchanged

**Two SurfSense spaces per venture:**
- `cortex_venture_{name}_dna` — creation chat, goals, research, pivots, DNA evolution
- `cortex_venture_{name}_ops` — daily ops, results, images, PDFs, operational log
- Credentials NEVER pushed to SurfSense — spaces store a reference (`Stripe: connected`) not the token

**CVS Scoring (extended — 8 dimensions, each 0-100):**
| Dimension | Weight | Notes |
|-----------|--------|-------|
| Market Size | 0.25 | TAM + growth rate |
| Problem Severity | 0.30 | Pain depth + frequency |
| Solution Uniqueness | 0.20 | Defensibility + moat |
| Implementation Ease | 0.15 | Time + complexity |
| Distribution Clarity | 0.10 | Go-to-market path |
| Risk Level | unweighted | Time investment + money investment combined |
| AI Setup Autonomy | unweighted | How much CORTEX can build/configure without user |
| AI Run Autonomy | unweighted | How much CORTEX can operate/optimize without user |

All 8 dimensions scored 0-100. Composite CVS = weighted sum of top 5. New 3 dimensions displayed separately as "CORTEX Advantage" metrics. Thresholds: auto≥75, review≥60, discard<35.

**Research certainty score:** Computed from actual research depth (source count, tier used, contradictions found, coverage gaps) — not synthetic.

**Deep iterative creation flow:**
1. Pull L1/L2/L3 memory first (existing context about user, market, related ventures)
2. INITIATION — quick probe: market, problem, user's unique edge
3. Tier 1 research → summarize → identify gaps
4. Brain-picking: ask user targeted gap-filling questions
5. Tier 2 for remaining gaps (auto-triggered when gap confidence < 0.6)
6. SYNTHESIS — draft VentureDNA with CVS + confidence scores
7. Iterate: show user, get feedback, re-research specific weak points
8. CRYSTALLIZATION — finalize DNA, compute all scores, visual output
9. CONFIRMATION — user approves → commit to ledger → create SurfSense spaces → push to Graphiti

User can say "use tier 2" at any point to force deep research. CORTEX auto-selects tier based on gap confidence.

**CORTEX capability lens:** During creation, CORTEX explicitly evaluates the venture through its own tool set (research automation, code generation, SaaS integrations, scraping, scheduling) — computes AI Setup/Run Autonomy scores from this analysis.

**Cross-venture synthesis:** After creation/update of any venture, background job synthesizes patterns across all ventures → push to `cortex_cross_venture` SurfSense space + Graphiti episode.

**Venture health pulse:** Computed summary per active venture:
- DNA completeness %
- CVS score + confidence
- Open decisions count
- Revenue / outcomes logged
- Last activity timestamp
- Next recommended action (CORTEX-generated)

**FailurePattern schema:** Dormant in Phase C — schema defined, no data written. Activates in Phase G epistemic flywheel.

---

#### C Build Order (dependency-ordered)

**Step C-1: VentureDNA models** — `python/helpers/cortex_venture_dna.py`
- Pydantic models: VentureDNA, MarketIntelligence, CompetitorProfile, ICP, WebAsset, IngestedDocument, FrameworkScore, ResearchSnapshot, VentureHealthPulse, FailurePattern (dormant)
- CVS scoring engine with all 8 dimensions
- Visual score renderer (ASCII art / text table for terminal + UI)
- Research certainty calculator
- Cross-venture synthesis schema

**Step C-2: Outcome Ledger** — `python/helpers/cortex_outcome_ledger.py`
- OutcomeEvent, HITLLogEntry, KellySignal models
- SQLite backend (local dev), Supabase-ready interface
- Decision capture → OutcomeLedger on every `venture_create` confirmation
- Kelly Criterion math ported from `kelly_mathematical_framework.py`

**Step C-3: Venture Discovery** — `python/helpers/cortex_venture_discovery.py`
- Trend/SEO scanner using `CortexResearchOrchestrator` (Tier 1 default, Tier 2 on demand)
- Pre-research cost gate for Tier 2 (estimate tokens × price → user confirmation if >$0.10)
- Keyword insights, trend reports, competitor profiles

**Step C-4: Creation Tool** — `python/tools/venture_create.py`
- LangGraph state machine: INITIATION → EXPLORATION → SYNTHESIS → CRYSTALLIZATION → CONFIRMATION
- Memory-first: pull L1/L2/L3 before first research call
- Research tier auto-selection (gap confidence < 0.6 → Tier 2)
- Manual tier override via conversation ("use tier 2" works)
- CORTEX capability lens scoring during SYNTHESIS
- SurfSense two-space creation on CONFIRMATION
- Graphiti episode push on CONFIRMATION
- Cross-venture synthesis trigger on CONFIRMATION
- OutcomeLedger commit on CONFIRMATION

**Step C-5: Venture Manage Tool** — `python/tools/venture_manage.py`
- `venture list` — all ventures with health pulse summary
- `venture status <name>` — full VentureDNA + CVS breakdown + visual
- `venture update <name>` — re-run creation flow for specific dimensions
- `venture health` — health pulse for active venture
- `venture activate <name>` — set active venture context

**Step C-6: Context Injection Extension** — `python/extensions/monologue_start/_07_venture_context.py`
- When a venture is active (`agent.get_data("active_venture")`), load VentureDNA
- Inject 200-token DNA summary into `extras_persistent["cortex_venture_context"]`
- Runs every monologue start → always current, zero drift

**Step C-7: SurfSense Router Update** — `python/helpers/cortex_surfsense_router.py`
- Add venture DNA + ops spaces to `CORE_SPACES`
- Add routing rules: venture-tagged docs → `cortex_venture_{name}_dna` or `cortex_venture_{name}_ops`
- Ensure `ensure_spaces_exist()` creates venture spaces on activation

**Step C-8: Cross-Venture Synthesis** — background function in `cortex_venture_dna.py`
- Called after any venture creation/update
- Reads all venture DNA files, extracts cross-venture patterns via DeepSeek V3.2
- Pushes synthesis doc to `cortex_cross_venture` SurfSense space
- Pushes Graphiti episode with cross-venture pattern tags

**Step C-9: Venture Prompt Docs** — `agents/cortex/prompts/`
- `agent.system.tool.venture_create.md` — tool documentation
- `agent.system.tool.venture_manage.md` — tool documentation
- Update `agent.system.main.role.md` — add venture context to COO identity

---

#### C Verification Tests

- C-T1: `venture_create` — run full creation flow for a test venture end-to-end
- C-T2: Confirm two SurfSense spaces created (`cortex_venture_test_dna` + `cortex_venture_test_ops`)
- C-T3: Venture context injection — restart CORTEX, confirm DNA summary appears in system prompt
- C-T4: Venture health pulse output — readable, computed correctly
- C-T5: Tier 2 auto-trigger — set gap confidence threshold, confirm Tier 2 fires
- C-T6: OutcomeLedger — decision captured on CONFIRMATION, persisted to SQLite
- C-T7: Cross-venture synthesis — create 2 ventures, confirm `cortex_cross_venture` doc pushed

---

### Phase D: Venture Discovery

**Status:** PLANNED — after Phase C live tests pass

**What it is:** A discovery engine that proactively finds venture opportunities aligned with user-defined parameters. Same infrastructure as Phase C (CVS scoring, CortexResearchOrchestrator, SurfSense, OutcomeLedger) — extended, not duplicated.

**Two modes (one engine):**

**Mode 1 — Interactive Parameter Session (~10 min with user):**
User free-flows ideas → CORTEX does lightweight research using cortex tooling → iterates back-and-forth → crystallizes a `VentureDiscoveryParameters` object → saved to disk → used by Mode 2. Without this session, Mode 2 is blind. 10 minutes of parameter design = 5-10x better autonomous discovery quality.

**Mode 2 — Autonomous Discovery (background, parameter-driven):**
Runs research cycles using parameters from Mode 1. Each candidate → DeepSeek CVS pre-score → gate (score ≥ min_cvs_score) → user review queue. Runs off-hours only (1-6am CET). Hard budget cap per night (default $3.00).

**VentureDiscoveryParameters:** market_domains, geography, min_cvs_score (default 45), min_ai_run_autonomy (default 50), max_capital_requirement, languages, excluded_domains, revenue_target_monthly, autonomy_preference.

**Build order (D-1 → D-7):**

**D-1: Dataclasses** — `python/helpers/cortex_discovery_params.py`
- VentureDiscoveryParameters, VentureCandidate, DiscoveryQueue dataclasses + persistence

**D-2: Discovery Engine** — `python/helpers/cortex_discovery_engine.py`
- Interactive session runner + autonomous cycle runner + candidate scoring via DeepSeek V3.2

**D-3: Tool** — `python/tools/venture_discover.py`
- Actions: discover, run [n], queue, review <id>, accept <id>, reject <id>, params, update_params
- `accept` → calls `venture_create start` with pre-loaded research context (no research wasted)

**D-4: Context Extension** — `python/extensions/monologue_start/_08_discovery_context.py`
- If queue non-empty: inject queue length + top candidate preview into system prompt

**D-5: Tool Docs** — `agents/cortex/prompts/agent.system.tool.venture_discover.md`

**D-6: Role Update** — add venture_discover to Step 6 tool routing table in role.md

**D-7: Scheduler** — register nightly Mode 2 in `_15_register_schedulers.py`

**Storage:** `usr/memory/cortex_main/discovery/` → params.json, queue.json, rejected.json, accepted.json

**Cost per night:** ~$0.03-0.07/cycle × 30 cycles = ~$1.00-2.10. Budget cap hard-coded at $3.00.

**Verification tests:** D-T1 through D-T7 (params saved, queue populated, CVS gate works, accept→create flow, scheduler fires, budget enforced, dedup works)

**Architecture docs (build at Phase D completion):**
- `agents/cortex/knowledge/cortex_main/main/architecture/cortex_wiring_phase_d.md`
- `agents/cortex/knowledge/cortex_main/main/architecture/cortex_architecture_phase_d.json`

---

### Phase E: Background Processes (NEVER STOP Protocol)

**Status:** PLANNED — after Phase D

**What it is:** Activates and hardens all background autonomous processes. Connects existing but dormant components (proactive engine, weekly digest, scheduler). Adds memory backup automation and auto-git-commit safety.

**NEVER STOP protocol:** Once started, background processes run without checking in. Loop until manually stopped or budget exhausted. Never interrupt active sessions.

**Components:**
- E-1: Scheduler hardening (off-hours constraint, session mutex, budget enforcement, failure logging)
- E-2: Proactive engine activation (`cortex_proactive_engine.py` already built)
- E-3: Weekly digest activation (`cortex_weekly_digest.py` already built)
- E-4: Memory backup automation:
  - L1 FAISS: daily rsync → B2/OneDrive
  - L2 Graphiti: weekly Zep export API → JSON → B2
  - L3 SurfSense: daily pg_dump → B2/OneDrive
  - Single `cortex-backups/` directory, 30-day retention
- E-5: Auto-git-commit safety before any file-modifying background job

**Off-hours schedule (default):**
- 2:00am CET daily: autonomous discovery
- 3:00am CET daily: L1+L3 backup
- 1:00am CET daily: proactive engine check
- 2:00am CET Sunday: weekly digest
- 3:30am CET Sunday: L2 Graphiti export

**Monthly cost:** ~$47-65 (discovery dominates at ~$45-63). Reduce default cycles to control cost.

---

### Phase F: Venture Operations

**Status:** PLANNED — after Phase E

**What it is:** Per-venture autonomy unlocking. CORTEX executes specific decision types autonomously for ventures that have proven themselves through monitored recommendations.

**Autonomy is per-decision-type, not per-venture globally.** User monitors CORTEX's recommendations over time, recognizes patterns ("it always decides X correctly in situation Y"), then explicitly grants autonomy for that decision type via `venture_manage`.

**Alert system:** If CORTEX deviates significantly from established decision pattern → immediate alert to user with full context.

**`autonomy_level` field in VentureDNA:** tracks which decision types are autonomous vs confirmation-required per venture.

---

### Phase G: CORTEX Self-Improvement (Epistemic Flywheel)

**Status:** PLANNED — after Phase F

**What it is:** Weekly cycle: analyze struggle_detect failures → cluster → hypothesize → isolated experiments → objective judge → human approval gate → apply winning changes.

**autoresearch pattern applied to CORTEX prompts and knowledge** (not ML weights).

**What gets experimented on:** prompts, knowledge files, model routing assignments (in G). Python code (in H+).

**Key components:**
- G-1: Memory isolation (`usr/memory/cortex_main_test/` namespace — never touches live memory)
- G-2: Auto-git-commit safety before experiments
- G-3: Test suite (30-40 representative queries + rubric, designed with user)
- G-4: Judge pipeline (DeepSeek V3.2 primary + Claude spot-check)
- G-5: Experiment runner (isolated, budget-capped, session-mutex)
- G-6: Struggle detect aggregation → hypothesis generator
- G-7: Objective report generator (no advocacy, before/after comparison)
- G-8: Human confirmation gate + apply mechanism
- G.1: DSPy integration (automated prompt search — 100+ variants vs 3 manual/week, same cost)

**Test suite refresh:** Monthly. Pull 30 real queries from past month's sessions. Anti-overfit measure.

**Judge stack:** DeepSeek V3.2 (primary, cheap) + Claude Sonnet 4.6 (10% spot-check calibration)

**Cost per experiment:** ~$0.50-0.90. 3 experiments/week = ~$6-11/month.

**DSPy early use (before Phase G):** Possible now for standalone prompt optimization. Pick one prompt, write 10-15 examples, run DSPy, apply best result. No G infrastructure needed.

---

### Phase H: Full Autonomy (Remove Agent Zero Wrapper)

**Status:** PLANNED — after Phase G validated

Replace Agent Zero conversational shell with direct FastAPI/Telegram interface. Keep LangGraph + memory stack unchanged. FAISS → Supabase pgvector for Fly.io deployment.

---

### Phase I: Commercial / Jarvis Variant

Desktop-first advisory mode. Less autonomy, more structured interaction. Commercial product for broader market.

---

### Phase J: UI Polish (if needed)

Evaluate after Phase E. If Alpine.js is sufficient: skip. If not: Next.js frontend connecting to same backend.

---

## 6. Cost Model

| Phase | Monthly | Breakdown |
|---|---|---|
| Development (0-D) | $60-150 | LLM $2-5/day via OpenRouter |
| Production (F+) | $200-350 | LLM $5-10/day, Fly.io $15-25, Composio $0-29 |

---

## 7. Session Continuity

| File | Purpose |
|---|---|
| `CORTEX_PLAN.md` | Master reference (this file) |
| `CORTEX_DECISIONS.md` | Architecture decisions log |
| `CORTEX_PROGRESS.md` | Phase tracking |
| `CLAUDE.md` | Session bootstrap |

**Start prompt:** "Read CORTEX_PLAN.md and CORTEX_PROGRESS.md. Current phase: [X]. Last completed: [Y]."
