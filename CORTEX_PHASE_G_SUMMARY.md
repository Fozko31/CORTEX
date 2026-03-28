# Phase G: Self-Optimization System — Build Summary

**Status:** COMPLETE
**Completed:** 2026-03-27
**Tests:** 62/62 passing (46 isolated + 16 holistic)
**New files:** 25 helpers/tools/extensions
**Modified files:** 4

---

## What Was Built

Phase G gives CORTEX the ability to observe its own performance, run controlled experiments on itself, and improve over time — without breaking memory, breaking production, or acting without user approval.

Five optimization loops operate on different time horizons:

| Loop | Frequency | What it does |
|------|-----------|-------------|
| 1 | Weekly (Sat 1am CET) | Detects struggle patterns → generates hypotheses → runs experiments → reports |
| 2 | Monthly (20th, 3am CET) | Ingests venture outcomes → attributes to CORTEX/user/external → generates optimization signals |
| 3 | Bi-monthly (1st odd months, 4am CET) | CORTEX+Ruflo architectural review → structured JSON protocol → human report |
| 4 | Monthly (15th, 2am CET) | Runs 20-query benchmark suite → flags drift > 10 points → notifies via Telegram |
| 5 | Bi-monthly (1st odd months, 3am CET) | Researches all 17 stack components → risk/benefit matrix → Replace Now / Investigate / Monitor |

---

## Key Design Decisions

**SQLite for raw events.** All raw events (struggles, tool calls, corrections, latency, benchmark runs) go to `usr/memory/cortex_main/cortex_event_store.db`. This is on the Fly Volume — survives restarts. Not local JSONL (Fly.io has ephemeral filesystem).

**SurfSense `cortex_optimization` space for aggregates.** Raw events stay in SQLite. Only aggregated summaries, experiment results, and version records are pushed to SurfSense — keeping the optimization data isolated from venture/ops spaces.

**Double-confirmation rollback.** `rollback_request()` → returns `confirm_phrase`. `rollback_execute(confirm_phrase)` → actually reverts. Prevents accidental git revert. Reason is logged at both steps.

**Memory preservation invariant.** Git rollback cannot touch L1/L2/L3. Memory layers are architecturally decoupled from code. FAISS is snapshot before every experiment.

**Attribution model (Loop 2).** Outcomes classified as cortex_owned / user_owned / external / mixed. `autonomy_score` from VentureDNA is the signal quality multiplier: high-automation = 1.0, low-automation moving company = 0.3. User-owned → weight 0.0 (no signal). External confounders → mixed/external (discounted).

**Structured JSON protocol (Loop 3).** CORTEX and Ruflo exchange structured JSON (no human language for internal messages). 2-3 rounds, convergence criteria: no new questions + proposed fixes stable for 2 rounds. CORTEX writes the final human-readable report.

**20-query test suite.** 5 categories × 4 queries (V1-V4, R1-R4, S1-S4, C1-C4, L1-L4). Each query has 4-5 rubric criteria (binary or 0-2 graded). DeepSeek V3.2 is the primary judge — cheap, independent. Claude spot-checks 10% of evaluations.

**DSPy deferred to G.1.** Loop 1's current change mechanism appends a structured section to the target file (MVP). DSPy-optimized targeted insertion comes in Phase G.1, after Loop 1 is validated over 4+ weekly cycles.

---

## Files Created

### Core Infrastructure (G-0)
- `python/helpers/cortex_event_store.py` — SQLite event log (7 tables, WAL mode)
- `python/helpers/cortex_version_manager.py` — Named versions, pre-experiment checkpoints, 2-step rollback

### Loop 1 Event Logging (G-1)
- `python/extensions/monologue_end/_62_tool_usage_log.py` — logs tool calls per turn
- `python/extensions/monologue_start/_09_correction_detect.py` — detects user correction signals
- Modified: `python/extensions/monologue_end/_60_struggle_detect.py` — added SQLite logging

### Loop 1 Self-Improvement (G-2)
- `python/helpers/cortex_struggle_aggregator.py` — clusters struggle events, generates hypotheses
- `python/helpers/cortex_experiment_suite.py` — all 20 test queries with rubrics
- `python/helpers/cortex_experiment_judge.py` — DeepSeek judge + Claude spot-check
- `python/helpers/cortex_experiment_runner.py` — runs experiments (baseline vs experimental)
- `python/helpers/cortex_experiment_reporter.py` — Markdown reports + Telegram summaries
- `python/helpers/cortex_experiment_applier.py` — applies approved changes, pins version
- `python/tools/self_improve.py` — agent-callable tool (10 operations)
- `agents/cortex/prompts/agent.system.tool.self_improve.md` — tool documentation

### Loop 3+4 Reporting (G-3)
- `python/helpers/cortex_operational_reporter.py` — 10-category operational report
- `python/helpers/cortex_benchmark_runner.py` — monthly 20-query benchmark + drift detection

### Loop 2 Outcome Processing (G-4)
- `python/helpers/cortex_outcome_attributor.py` — classifies outcomes (cortex/user/external/mixed)
- `python/helpers/cortex_outcome_feedback.py` — outcome ingestion, execution checkins (EN + SL)
- `python/helpers/cortex_optimization_signal.py` — converts outcomes → optimization signals

### Loop 3 Inter-agent Protocol (G-5)
- `python/helpers/cortex_interagent_protocol.py` — structured JSON CORTEX↔Ruflo protocol
- `python/helpers/cortex_ruflo_session_packager.py` — full bi-monthly Loop 3 orchestration

### Loop 5 Stack Evolution (G-6)
- `python/helpers/cortex_stack_inventory.py` — authoritative 17-component stack definition
- `python/helpers/cortex_stack_researcher.py` — Tier 1 research per component (Tavily + Exa → DeepSeek)
- `python/helpers/cortex_stack_evaluator.py` — risk/benefit matrix → Replace Now / Investigate / Monitor / Stable

### Schedulers (G-9)
- Modified: `python/extensions/monologue_start/_15_register_schedulers.py` — all 5 loop tasks registered

### Tests (G-7)
- `tests/test_g_core.py` — 46 isolated unit tests
- `tests/test_g_extended.py` — 16 holistic integration tests

---

## Test Results

```
tests/test_g_core.py     46 passed
tests/test_g_extended.py 16 passed
Total: 62 passed in ~22s
```

Coverage across all modules: event_store, version_manager, experiment_suite, struggle_aggregator, experiment_judge, operational_reporter, outcome_attributor, optimization_signal, interagent_protocol, stack_inventory, stack_evaluator. Full pipeline tests: Loop 1 (struggle→cluster→experiment→apply), Loop 2 (outcome→attribution→signal), Loop 3 (protocol session→human report), Loop 5 (research→evaluation→report).

---

## What's Next

**Phase G.1** (after Loop 1 runs 4+ weeks): DSPy integration for targeted prompt optimization instead of append-only changes.

**Phase H**: Commercial Jarvis variant — Fly.io deployment, FastAPI frontend, per-venture windows, investor-grade reporting.
