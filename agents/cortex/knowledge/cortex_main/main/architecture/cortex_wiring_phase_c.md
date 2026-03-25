# CORTEX Wiring — Phase C: Venture Machine

**Built:** 2026-03-25
**Status:** Complete
**Loaded by:** FAISS at startup (auto-indexed from agents/cortex/knowledge/)

This document describes how Phase C components wire together. When CORTEX needs to modify, debug, or extend venture features, this is the reference for understanding data flow, dependencies, and integration points.

---

## Component Map

```
[User: "create a venture"]
        ↓
  [Agent Zero LLM]
        ↓ tool call
  [venture_create.py]
        ├── _start() ──────────────────────────────────────────────────────────┐
        │       ├── _pull_memory_context() → FAISS + Graphiti (existing context)│
        │       ├── _parse_brief() → DeepSeek V3.2 → {venture_type, market...} │
        │       └── _run_tier1() → CortexVentureScanner.scan_tier1()           │
        │                              ↓                                         │
        │                    CortexResearchOrchestrator                          │
        │                    (Tavily + Exa → Claude synthesizes)                │
        │                              ↓                                         │
        │                    TrendReport → analyze_gaps() → DeepSeek V3.2       │
        │                              ↓                                         │
        │                    [gap questions stored in session]                  │
        │                              ↓                                         │
        │                    → Response: "Question 1/N: ..."  ←─────────────────┘
        │
        ├── _handle_brain_picking() [per user answer]
        │       └── if confidence < 0.6 → TIER2_GATE → _trigger_tier2()
        │                                    ↓
        │                    CortexVentureScanner.scan_tier2()
        │                    (Perplexity + Tier1 context → deeper findings)
        │
        ├── _run_synthesis()
        │       ├── _build_dna_from_session()
        │       │       ├── merge Tier1 TrendReport → VentureDNA
        │       │       ├── merge Tier2 TrendReport → VentureDNA
        │       │       ├── merge user answers → key_insights + resolve open_questions
        │       │       └── _score_cvs_from_llm() → DeepSeek V3.2 → 5 CVS dimensions
        │       └── _apply_capability_lens() → DeepSeek V3.2 → 3 CORTEX Advantage scores
        │
        ├── _run_crystallization()
        │       ├── VentureDNA.recompute_research_certainty()
        │       ├── VentureDNA.render_cvs() → ASCII visual
        │       └── VentureDNA.compute_health_pulse() → VentureHealthPulse.render()
        │
        └── _confirm() [CONFIRMATION — all side effects fire here]
                ├── save_venture(dna) → disk: usr/memory/cortex_main/ventures/{name}.json
                ├── OutcomeLedger.record_venture_creation(dna) → SQLite
                ├── CortexSurfSenseClient.ensure_spaces_exist([dna_space, ops_space])
                ├── CortexGraphitiClient.add_episode(venture creation episode)
                ├── DeferredTask → _run_cross_venture_synthesis() [background]
                │       └── synthesize_cross_venture_patterns() → DeepSeek V3.2
                │           → CrossVenturePattern list
                │           → CortexSurfSenseClient.push_document(cortex_cross_venture)
                ├── agent.set_data('active_venture', id)
                └── agent.set_data('active_venture_name', name)
```

---

## Per-Turn Flow (when a venture is active)

```
[User sends message]
        ↓
  monologue_start:
    _05_self_model_load.py    → loads self-model JSON + Tier 0 SurfSense index (local, free)
    _07_venture_context.py    → load_venture(active_venture_name) from disk
                                → VentureDNA.brief_summary(200)
                                → extras_persistent["cortex_venture_context"] = block
        ↓
  message_loop_prompts_after:
    _15_temporal_memory.py    → FAISS recall → extras_persistent["cortex_knowledge"]
    _17_personality_model.py  → personality + commitments → extras_persistent
    _18_graphiti_pull.py      → Zep L2 search (trivial gate) → extras_persistent["cortex_temporal"]
    _20_surfsense_pull.py     → SurfSense L3 pull (3 spaces, keyword scoring) → extras_persistent["cortex_consciousness"]
        ↓
  [LLM sees: system prompt + venture context + memory + temporal + consciousness]
        ↓
  monologue_end:
    _10_knowledge_extraction.py  → extract entities/facts → FAISS FRAGMENTS
    _15_graphiti_update.py       → push extracted entities → Zep Cloud
    _60_struggle_detect.py       → detect hedging → flag knowledge gaps
        ↓
  process_chain_end:
    _10_surfsense_push.py        → fires every 20 exchanges only
                                   → session summary → SurfSense push
```

---

## State Persistence Map

| Data | Where stored | Written by | Read by |
|------|-------------|------------|---------|
| VentureDNA | `usr/memory/cortex_main/ventures/{name}.json` | save_venture() | load_venture(), _07_venture_context, venture_manage |
| OutcomeLedger | `usr/memory/cortex_main/cortex_ledger.db` (SQLite) | OutcomeLedger methods | venture_manage kelly/health actions |
| Active venture ID | `agent.set_data('active_venture')` | venture_create CONFIRMATION, venture_manage activate | _07_venture_context, venture_manage |
| Creation session state | `agent.set_data('venture_creation_session')` | venture_create._save_session() | venture_create._load_session() |
| SurfSense DNA space | `dna.surfsense_dna_space_name` (in VentureDNA JSON) | set in VentureDNA.__post_init__ | cortex_surfsense_router, _confirm() |
| SurfSense ops space | `dna.surfsense_ops_space_name` (in VentureDNA JSON) | set in VentureDNA.__post_init__ | cortex_surfsense_router, _confirm() |

---

## SurfSense Space Structure (Phase C)

```
cortex_conversations          ← session summaries (pre-Phase C, unchanged)
cortex_knowledge              ← extracted facts, research
cortex_outcomes               ← decisions, ROI
cortex_user_profile           ← user preferences
cortex_weekly_digest          ← weekly summaries
cortex_cross_venture          ← cross-venture patterns (NEW Phase C)
cortex_venture_{name}_dna     ← per-venture: creation, DNA, research, strategy (NEW Phase C)
cortex_venture_{name}_ops     ← per-venture: daily ops, results, images (NEW Phase C)
```

Push routing: `CortexSurfSenseRouter.route_for_push(doc)` reads `metadata.venture` and `metadata.ops_doc`. If `ops_doc=True` → ops space. Otherwise → dna space.

---

## CVS Scoring — How It's Computed

1. `_score_cvs_from_llm()` in venture_create.py sends research summary to DeepSeek V3.2
2. Returns 5 weighted dimensions (market_size, problem_severity, solution_uniqueness, implementation_ease, distribution_clarity)
3. `_apply_capability_lens()` sends venture description to DeepSeek V3.2, evaluating through CORTEX tool capabilities → returns ai_setup_autonomy, ai_run_autonomy, risk_level
4. `VentureDNA.update_cvs(**dims)` stores all 8 dimensions in `CVSScore`
5. `CVSScore.composite_cvs()` = weighted sum of 5 original dims (0-100)
6. `CVSScore.verdict()` = AUTO_PROCEED | REVIEW | CONDITIONAL | DISCARD based on thresholds
7. `VentureDNA.recompute_research_certainty()` = compute_research_certainty(source_count, tier_used, gap_count, contradiction_count)
8. `CVSScore.render()` = ASCII bar chart of all 8 dimensions

---

## Models Used in Phase C

| Step | Model | Why |
|------|-------|-----|
| Brief parsing | DeepSeek V3.2 (classification) | Cheap structured extraction |
| Gap analysis | DeepSeek V3.2 (classification) | Cheap structured extraction |
| CVS scoring | DeepSeek V3.2 (classification) | Cheap structured extraction |
| CORTEX capability lens | DeepSeek V3.2 (classification) | Cheap structured extraction |
| Iteration refinement | DeepSeek V3.2 (synthesis) | Background task |
| Cross-venture synthesis | DeepSeek V3.2 (classification) | Cheap pattern extraction |
| Tier 1 research synthesis | Claude Sonnet 4.6 | Final user-facing synthesis — NEVER optimize |
| Tier 2 research synthesis | Claude Sonnet 4.6 | Final user-facing synthesis — NEVER optimize |

---

## Key Files — If You Change X, Watch Y

| If you change... | Also check... |
|-----------------|---------------|
| `CVSScore` fields | `venture_create._score_cvs_from_llm()` prompts, `VentureDNA.to_dict/from_dict`, `render_cvs()` |
| `VentureDNA.to_dict()` | `VentureDNA.from_dict()` (must mirror), `save_venture/load_venture` |
| `_safe_space_name()` in cortex_venture_dna.py | `cortex_surfsense_router.venture_dna_space/venture_ops_space` (both call it) |
| `venture_create` session state keys | `_save_session`, `_load_session`, all `_handle_*` methods that read the dict |
| `CONFIRMATION` side effects | `_confirm()` method — all steps are there in sequence |
| `OutcomeLedger` schema (_DDL) | `record_event`, `record_hitl`, `record_decision`, `compute_kelly_signal` (SQL must match) |
| `CortexSurfSenseRouter.route_for_push()` | `ops_doc` metadata flag in any doc that should go to ops space |
| Extension ordering (`_07_` prefix) | All other monologue_start extensions — numbering determines order |

---

## Source References (Omnis → CORTEX Ports)

| CORTEX file | Ported from | Key changes |
|-------------|-------------|-------------|
| cortex_venture_dna.py | omnis_workspace_VERDENT/omnis_ai/venture/dna.py | Added CVSScore (8 dim), VentureHealthPulse, FailurePattern, CrossVenturePattern, two SurfSense spaces, disk persistence, autonomy_level as first-class field |
| cortex_outcome_ledger.py | omnis_workspace_VERDENT/omnis_ai/venture/outcome_ledger.py | Removed Omnis SurfSense sync, added DecisionEvent, CORTEX-native DB path, Kelly math inline |
| cortex_venture_discovery.py | omnis_workspace_VERDENT/omnis_ai/venture/discovery.py | Replaced Omnis LLM router with CortexModelRouter, domain-agnostic (not Etsy-specific), uses CortexResearchOrchestrator |
| venture_create.py | omnis_workspace_VERDENT/omnis_ai/venture/creation_flow.py | Extended 5-phase to 9-step, memory-first, Tier2 gate, CORTEX capability lens, Agent Zero tool interface |
| Kelly math in cortex_outcome_ledger.py | omnis_v12_JARVIS/omnis_ai/modules/kelly_mathematical_framework.py | Direct port, pure functions |
