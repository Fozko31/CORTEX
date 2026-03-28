# CORTEX Phase B — Consciousness: SurfSense + Graphiti

**Completed:** Early build (both services LIVE)
**Tests:** Covered by `tests/test_b1_surfsense_health.py` through `test_b5_zep_health.py`
**Technical depth:** [phase_b_architecture.md](usr/knowledge/cortex_main/main/phase_b_architecture.md)

---

## What Phase B Built

Phase B turns CORTEX from a session-bound agent into one that has continuity across devices, sessions, and time. Phase A2 gives CORTEX local memory — Phase B gives it *consciousness*.

The distinction: A2 memory resets when the machine changes or the agent restarts in a new context. B memory persists in the cloud, is device-independent, and carries temporal meaning — not just "what was stored" but "what was stored *when*, and how it changed over time."

### 1. L3 SurfSense — Cross-Device Consciousness

SurfSense is a self-hosted knowledge management platform with an API. CORTEX uses it as its semantic document store — structured knowledge that can be searched, retrieved, and injected across any session on any device.

**Six permanent spaces:**

| Space | What it stores |
|-------|---------------|
| `cortex_main` | Core knowledge: decisions, outcomes, session summaries |
| `cortex_research` | Research findings from Tier 1/2 runs |
| `cortex_ops` | Operational knowledge, procedure documentation |
| `cortex_ventures` | Cross-venture patterns and portfolio insights |
| `{slug}_dna` | Per-venture DNA and strategy (created when venture confirmed) |
| `{slug}_ops` | Per-venture operational playbooks (created when playbook published) |

CORTEX pushes to SurfSense at session end (`process_chain_end/_10_surfsense_push.py`) and pulls from it at message start (`message_loop_prompts_after/_20_surfsense_pull.py`).

**JWT authentication with token caching:** SurfSense tokens expire after ~1 hour. The client caches tokens and only re-authenticates when the token is within 100s of expiry.

**Ingestion schema:** Documents pushed to SurfSense follow a standard schema with title, content, and metadata. Titles are structured as `{Category} {date}: {topic}` — critical because SurfSense exposes only the title as a keyword-searchable field via the API.

### 2. L2 Graphiti (Zep Cloud) — Temporal Knowledge Graph

Graphiti (via Zep Cloud) is the temporal graph layer. Where SurfSense stores documents, Graphiti stores *entities, relationships, and the time at which those relationships held true*.

**What this enables:**
- "What did we know about X venture last month?" — Graphiti can answer this
- Entity relationship tracking across sessions (CORTEX → knows → User preference X, added 2026-01-15)
- Semantic + graph traversal search — not just keyword matching

**Single user: `cortex_main`** — all episodes ingested under one user ID so the knowledge graph accumulates as a unified whole across all ventures and sessions.

**Episode ingestion:** At `monologue_end/_15_graphiti_update.py`, entities and facts extracted by Phase A1's knowledge extractor are forwarded to Graphiti as text episodes. Zep asynchronously extracts entity/relationship edges.

### 3. Session Summarizer

`cortex_session_summarizer.py` — produces structured summaries at session end.

Uses DeepSeek V3.2 (via model router) rather than Claude Sonnet — 10x cheaper for session summarization with no quality loss. Output: summary narrative, topic keywords, outcomes (decisions/commitments/action items), knowledge extracted, venture refs, session mood.

The summary is pushed to SurfSense `cortex_main` space as the session's document. This is what lets CORTEX recall what was discussed in previous sessions.

### 4. SurfSense Router

`cortex_surfsense_router.py` — smart 4-tier retrieval with space routing.

Rather than searching all spaces for every query, the router identifies which spaces are relevant based on query keywords and routes accordingly:

| Space | Search when |
|-------|------------|
| `cortex_user_profile` | preference, personality, trust, like, dislike |
| `cortex_conversations` | said, discussed, previously, mentioned |
| `cortex_knowledge` | fact, know, learned, research |
| `cortex_outcomes` | decided, decision, outcome, roi |
| `cortex_weekly_digest` | week, summary, overview, trend |
| `cortex_cross_venture` | across ventures, pattern, synergy |

For venture-specific queries, the router adds `{slug}_dna` and `{slug}_ops` spaces automatically.

### 5. Pull → Synthesize → Inject Loop

The full consciousness loop that fires on every message:

```
User message arrives
  ↓
_15_temporal_memory.py → FAISS recall (L1, local, <10ms)
  ↓
_18_graphiti_pull.py → Graphiti entity search (L2, temporal graph)
  ↓
_20_surfsense_pull.py → SurfSense 4-tier retrieval (L3, semantic documents)
  ↓
All results injected as context → LLM call
  ↓
Monologue end:
  _10_knowledge_extraction.py → extract entities/facts/commitments
  _15_graphiti_update.py → forward to Zep
  _50_memorize_fragments.py → write to FAISS
  ↓
Process chain end:
  _10_surfsense_push.py → session summary → SurfSense
```

---

## Key Design Decisions

| Decision | What was decided | Why |
|----------|-----------------|-----|
| SurfSense as L3 (not Notion/Obsidian) | Self-hosted, API-accessible, semantic search | Proprietary control, no vendor lock-in, local deployment |
| Zep Cloud for Graphiti | Official SDK, managed temporal graph | Building temporal graph from scratch would take weeks |
| Single Zep user ID (`cortex_main`) | Unified graph, all ventures and sessions in one | Cross-venture entity relationships require unified graph |
| Session summaries in `cortex_main` space | High-frequency writes need dedicated space | Keeps research and operational spaces clean |
| Space routing over full-scan | Only search relevant spaces | SurfSense API cost scales with search scope |
| Structured title format | `{Category} {date}: {topic}` | Title is SurfSense's only keyword-searchable field |
| DeepSeek for summarization | ~10x cheaper than Claude for this task | Cost optimization; summaries don't require Sonnet quality |
