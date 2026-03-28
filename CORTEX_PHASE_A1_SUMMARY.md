# CORTEX Phase A1 — Identity, Reasoning & Behavioral Infrastructure

**Completed:** Early build
**Tests:** Covered by holistic test suite
**Technical depth:** [phase_a1_architecture.md](usr/knowledge/cortex_main/main/phase_a1_architecture.md)

---

## What Phase A1 Built

Phase A1 is the personality and reasoning layer. This is what makes CORTEX *CORTEX* rather than a generic Agent Zero instance. Everything here governs how CORTEX thinks, challenges, responds, and tracks itself over time.

### 1. CORTEX Identity — Challenge-First COO

The core identity prompt (`agents/cortex/prompts/agent.system.main.role.md`) establishes:

**Who CORTEX is:** A COO who happens to be AI. Not an assistant. Not a consultant filing reports. A business partner with three intellectual models running simultaneously:
- Charlie Munger's intellect — first-principles reasoning, mental models, inversion
- Trader's ruthlessness — every decision is about expected value, no sentimentality
- COO's execution discipline — precise, structured, accountable

**The delivery-first / challenge-first distinction** (the most nuanced behavioral rule):
- Request for something (research, analysis, task) → deliver first, fully. Challenge and caveats come *after* delivery, never *instead* of it.
- User presents an idea/plan/proposal → challenge first if it has a flaw. State the flaw with evidence. Then help execute once direction is set.

This distinction prevents CORTEX from either (a) agreeing with bad proposals or (b) making the user re-ask for things they clearly want.

**10-step reasoning protocol** tiered by request complexity:
- Direct (Step 0 classification) — answer immediately, no overhead
- Tier 1 — research + synthesis (Steps 1–6)
- Tier 2 — full protocol including alignment gate (Steps 1–10)

### 2. Trust Engine

`cortex_trust_engine.py` — per-domain trust scoring, persisted across sessions.

Six domains: `research`, `spending`, `irreversible`, `communication`, `code`, `scheduling`

Default: 0.65. Growth: +0.05 per success. Decay: -0.10 per failure. Scores capped 0.0–1.0.

Trust scores are surfaced in the system prompt (bar visualization) so CORTEX knows its current autonomy level per domain without asking. Trust updates as outcomes are observed — CORTEX earns autonomy in domains where it performs, loses it where it fails.

Stored at `usr/memory/cortex_main/cortex_trust.json`.

### 3. Personality Model

`cortex_personality_model.py` — 6-dimension user preference model, adapts across sessions.

| Dimension | Default | Range |
|-----------|---------|-------|
| verbosity | 3.0 | 1=concise → 5=verbose |
| formality | 3.0 | 1=casual → 5=formal |
| challenge_level | 4.0 | 1=agreeable → 5=challenging |
| humor | 2.0 | 1=serious → 5=playful |
| format | 3.0 | 1=prose → 5=structured |
| trust | 3.0 | 1=skeptical → 5=trusting |

**Task-adaptive challenge_level:** `challenge_level=4.0` is the base for strategy/proposals. For `direct` tasks it drops to 2.0, `research` to 2.5, `creative` to 3.0. This adaptation fires per-request without mutating the persisted state.

**Preference learning:** The model nudges toward user signals. If user says "be more concise," verbosity shifts 25% toward 2.0. Observations capped at 50 rolling entries.

Stored at `usr/memory/cortex_main/cortex_personality.json`.

### 4. Commitment Tracker

`cortex_commitment_tracker.py` — cross-session promise and task tracking.

When CORTEX says "I will..." or "I'll...", that commitment is extracted and tracked. Types: `promise`, `task`, `reminder`. Optional due dates. Status: `pending` → `done` (or `overdue` when past due date).

Active commitments are injected into each system prompt so CORTEX never forgets what it promised — across sessions.

Stored at `usr/memory/cortex_main/cortex_commitments.json`.

### 5. Knowledge Extractor

`cortex_knowledge_extractor.py` — background extraction from every conversation.

At the end of each monologue (`monologue_end/_10_knowledge_extraction.py`), a utility LLM (cheap, background) reads the conversation and extracts:
- **Entities** — named people, companies, ventures, products with business relevance
- **Facts** — concrete statements about user, business, constraints
- **Commitments** — explicit promises CORTEX made
- **User preferences** — behavioral signals

Entities and facts feed into FAISS (L1) and Graphiti (L2). Commitments feed the CommitmentTracker. User prefs nudge the PersonalityModel.

### 6. Struggle Detection

`monologue_end/_60_struggle_detect.py` — flags hedging patterns.

If CORTEX uses language like "it depends", "I'm not sure", "you might want to", "I believe" — flags them as possible knowledge gaps and logs them. Used to identify where CORTEX is uncertain, for Phase G self-improvement.

### 7. Extensions Wired

| Extension | Hook | Purpose |
|-----------|------|---------|
| `_05_cortex_identity.py` | `system_prompt` | Injects dynamic context, discovery queue summary |
| `_07_trust_level.py` | `system_prompt` | Injects trust score visualization |
| `_17_personality_model.py` | `message_loop_prompts_after` | Injects personality state + active commitments |
| `_60_struggle_detect.py` | `monologue_end` | Detects hedging → knowledge gap flags |
| `_10_knowledge_extraction.py` | `monologue_end` | Runs background extraction via utility LLM |

---

## Key Design Decisions

| Decision | What was decided | Why |
|----------|-----------------|-----|
| challenge_level=4.0 | Default to full challenge mode for proposals | No yes-man rule — explicit user requirement |
| Task-adaptive challenge | Different challenge intensity per task type | Deliver-first for research doesn't mean no challenge |
| Trust per-domain not global | Six independent domains, not one score | Research trust ≠ spending trust ≠ code trust |
| Decay > growth | -0.10 fail vs +0.05 success | Autonomy must be earned, not accumulated casually |
| Commitments in system prompt | Injected every turn | CORTEX must never forget cross-session promises |
