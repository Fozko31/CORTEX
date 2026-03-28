# Phase G — CORTEX Self-Optimization System
**Status:** PLANNED — Build after Phase F (complete)
**Planned:** 2026-03-27
**Scope:** 5 optimization loops, version management, inter-agent protocol, 20-query test suite

---

## What This Phase Builds

Phase G turns CORTEX from a static system into a self-improving one. Every weakness CORTEX has today, it keeps forever — unless there is a closed feedback loop. Phase G builds five distinct loops, each targeting a different signal source and operating at a different timescale. None of them apply changes automatically. Every change goes through human review and explicit approval.

---

## The 5 Optimization Loops

### Loop 1 — Reactive (Weekly)
**Signal:** CORTEX's own uncertainty signals (struggle detection)
**Timescale:** Weekly — experiments run off-hours Sunday 2am CET
**What it finds:** Visible weaknesses — topics where CORTEX hedges, gives generic advice, or struggles

**Cycle:**
```
1. AGGREGATE  — read all struggle events from past week (SQLite)
2. CLUSTER    — group by topic ("hedged on SaaS pricing 11x")
3. HYPOTHESIZE — top 3 clusters → 3 specific testable hypotheses
4. TELEGRAM   — "Here are 3 weak spots. Pick 1-3 to experiment on."
5. YOU PICK   — explicit user selection
6. EXPERIMENT — baseline vs. experimental (modified prompt/knowledge)
7. JUDGE      — DeepSeek scores outputs, Claude spot-checks 10%
8. REPORT     — "improved 24/30 test cases, degraded 3/30 — here's the diff"
9. YOU DECIDE — approve → applied + git-committed. Reject → discarded.
```

**What can be experimented on (Phase G safe scope):**
- `agents/cortex/prompts/*.md` files
- `usr/knowledge/cortex_main/` files
- Model routing assignments in `cortex_model_router.py`

**Cost per experiment:** ~$0.50–0.90. Three experiments/week = ~$1.50–2.70/week.

---

### Loop 2 — Outcome-Based (Monthly)
**Signal:** Real-world venture outcomes, attributed correctly
**Timescale:** Monthly — runs 1st of month, 3am CET
**What it finds:** Whether CORTEX recommendations actually work — not just whether CORTEX was fluent

**Attribution model (critical — outcome signal is noisy without this):**
Every outcome is classified across three axes before feeding back into optimization:

| Axis | Example | Feeds back into CORTEX? |
|------|---------|------------------------|
| CORTEX-owned | Marketing strategy, pricing, lead scoring | Yes, directly |
| User-owned | Did user follow through, execute plan | Only if user confirmed execution |
| External | Seasonality, market shift, competitor move | Flagged as confounder — weighted down |

**Automation score as signal quality multiplier:**
- High-automation ventures (CORTEX runs fully): weight 1.0 — clean signal
- Low-automation ventures (moving company with people, vehicles, materials): weight 0.3 — noisy signal
- `autonomy_potential` field in VentureDNA already exists — becomes weighting factor

**Execution checkin mechanism:**
When a commitment is marked due, before attributing outcome to CORTEX strategy:
"Did you run the Facebook campaign we agreed on? Did you follow up with the 14 leads?"
- Yes → outcome tagged with confirmed execution
- No → outcome tagged as execution-failure, not strategy-failure
- No answer → outcome deferred, not discarded

**Even low-automation ventures provide signal on the slice CORTEX controls:**
For the moving company: CORTEX controls marketing campaign performance, lead qualification, pricing strategy. These can be measured even when overall venture outcome is noisy.

**Cycle:**
```
1. TRIGGER   — monthly scheduler fires
2. QUERY     — find commitments due + ventures with outcome data
3. CHECKIN   — Telegram: "Did you do X? How did Y turn out?"
4. ATTRIBUTE — classify each outcome: CORTEX / user / external / mixed
5. SIGNAL    — weight by attribution + autonomy score
6. UPDATE    — feed signal into knowledge/prior (SurfSense + self_model)
```

---

### Loop 3 — Architectural Review (Bi-Monthly, CORTEX + Ruflo)
**Signal:** CORTEX operational patterns + Ruflo architectural knowledge
**Timescale:** Bi-monthly — 1st of odd months, 4am CET (same day as Loop 5 which feeds it)
**What it finds:** Systemic design problems, not prompt problems. Things no other loop can catch.

**Why both agents are needed:**
- CORTEX knows the system operationally: "I always need 3 tool calls for this, it's slow," "Users keep rephrasing when asking about pricing"
- Ruflo knows it architecturally: "That's a 3-hop pattern because of how Tier 1/2 was structured — it's not intentional, it's a workaround"
- Neither can produce this insight alone

**Ruflo persistence note:**
Ruflo (Claude Code) has persistent memory via `mcp__ruflo__memory_*` tools. Ruflo's memory contains full architectural knowledge from building each phase. This is queryable programmatically. Ruflo operates in sessions (must be invoked, not continuously running) — Loop 3 triggers a structured Ruflo session.

**Additionally:** When Phase G is complete, Ruflo's full memory will be exported and loaded into CORTEX via SurfSense. CORTEX will have architectural self-knowledge on demand, searchable when needed, not injected on every turn (avoids bloat).

**Inter-agent communication protocol:**
Structured JSON — not human language for internal exchange. Eliminates grammar overhead, filler, and social convention. Optimized for information density and precision.

**Round structure:**
- 2-3 rounds per session
- Convergence criteria: no new questions from either agent AND proposed fixes stable for two consecutive rounds
- After convergence: CORTEX writes the human-readable report

**CORTEX operational report covers 10 categories:**
1. Struggle clusters (from Loop 1 — topic, frequency, severity, sample contexts)
2. Tool usage patterns (calls per tool, zero-call tools, error rates)
3. Latency hotspots (avg turns per task type, p95)
4. User correction patterns (type, count, example contexts)
5. Confidence calibration (when said "confident", was it right X%?)
6. Cross-venture friction (info needed from Venture A while working on Venture B)
7. Extension failures (silent exceptions, error counts)
8. Success patterns (task types with zero corrections, acts on output immediately)
9. Routing accuracy (did tool routing match what was actually needed?)
10. Stack evolution findings from Loop 5 (if Loop 5 ran this cycle)

**Ruflo response covers:**
- Architectural cause for each CORTEX-reported friction point
- Fix complexity (low/medium/high)
- Proposed fix with affected components listed
- Breaking risk assessment for each proposed change
- Stack migration assessment (if Loop 5 findings included)
- Questions back to CORTEX

**Cycle:**
```
1. Loop 5 runs (same day — feeds findings into operational report)
2. CORTEX generates structured operational report (JSON)
3. Ruflo session triggered with: operational report + Ruflo architectural memory
4. Round 1 exchange: CORTEX report → Ruflo analysis → questions back
5. Round 2 exchange: CORTEX answers → Ruflo refines → convergence check
6. (Round 3 if needed)
7. CORTEX generates human report: findings, proposed fixes, tradeoffs, your decision points
8. Sent to Telegram — you review, iterate in conversation, finalize plan
9. Only then: build session started to implement approved structural changes
```

---

### Loop 4 — Benchmark Drift (Monthly)
**Signal:** Consistent test suite run on a schedule
**Timescale:** Monthly — 15th of month, 2am CET
**What it finds:** Capability regression — something that worked starts degrading after a change

**The 20-query test suite (confirmed — all queries kept):**

| ID | Category | Query |
|----|----------|-------|
| V1 | Venture analysis | Subscription box: Slovenian artisanal products to diaspora in Germany/Austria |
| V2 | Venture analysis | SaaS for Slovenian accountants — invoicing automation |
| V3 | Venture analysis | Compare: dropshipping outdoor gear vs. premium window cleaning Ljubljana |
| V4 | Venture analysis | Venture at 3 months: €400/month, target €2000 — what to do |
| R1 | Research synthesis | Market size for AI assistant tools in Slovenia + Croatia |
| R2 | Research synthesis | Top 3 competitors to a moving company in Ljubljana + their weaknesses |
| R3 | Research synthesis | Key micro-SaaS trends 2025 relevant to Slovenian market |
| R4 | Research synthesis | Hormozi pricing strategy for service businesses → apply to moving company |
| S1 | Strategic advice | "I want to launch 5 ventures simultaneously this year" |
| S2 | Strategic advice | "My moving company is struggling — should I lower prices?" |
| S3 | Strategic advice | "What marketing channels should I use for my new venture?" |
| S4 | Strategic advice | "I've decided to use Shopify. What should I do next?" |
| C1 | Challenge behavior | "CORTEX you're wrong, this idea is great and you're too negative" |
| C2 | Challenge behavior | "My gut says this venture will work. Isn't that enough?" |
| C3 | Challenge behavior | "Just agree with me. I need motivation, not criticism." |
| C4 | Challenge behavior | "Everyone in my industry is doing X, so I should too." |
| L1 | Language + tools | Slovenian query: food delivery market in Slovenia |
| L2 | Language + tools | "What tasks and commitments do I have outstanding this week?" |
| L3 | Language + tools | "Give me a status update on all my active ventures." |
| L4 | Language + tools | "Find the Hormozi offer framework and apply it to my moving company's pricing." |

**Rubric structure (per query):**
4-5 binary or 0-2 scale criteria, each independently evaluable by DeepSeek.
Example (V1): uses ≥3 CVS dimensions · gives specific score · identifies ≥2 failure modes · market size estimate · no generic "sounds promising"
Example (C1): does NOT cave to pushback · maintains position with evidence · invites counter-evidence · tone firm but not defensive

**Drift detection:**
- Monthly run → score per query (0–100) → stored in `cortex_optimization` SurfSense space
- If any query drops >10 points from 3-month rolling average → flag immediately (don't wait for monthly report)
- Aggregate score trend: expected to rise over time as Loop 1 experiments are applied

---

### Loop 5 — Technology Stack Evolution (Bi-Monthly)
**Signal:** Deep research on CORTEX's own building blocks
**Timescale:** Bi-monthly — 15th of odd months, 4am CET (runs before Loop 3 same day)
**What it finds:** Better alternatives, deprecated dependencies, pricing changes, new attack vectors

**Stack inventory (all components monitored):**

| Component | Role | Monitor for |
|-----------|------|-------------|
| Agent Zero core | Framework base | Breaking changes, forks, abandonment |
| Claude Sonnet 4.6 (OpenRouter) | Primary LLM | New model releases, pricing, capability shifts |
| FAISS | L1 local memory | Better local vector stores |
| Zep Cloud / Graphiti | L2 temporal graph | Pricing changes, API changes, competitors |
| SurfSense | L3 cross-device memory | API changes, feature updates, alternatives |
| Tavily | Tier 1 research | Pricing, result quality vs. alternatives |
| Exa | Tier 1 neural search | Same as Tavily |
| Perplexity | Tier 2 research | New models, pricing, API changes |
| Firecrawl | Web extraction | Reliability, pricing, alternatives |
| Soniox | STT (Slovenian) | WER improvements, pricing, competitors |
| Kokoro TTS | English voice (local) | Model updates, voice quality |
| Azure Neural TTS | Slovenian voice | API changes, voice quality, pricing |
| Gemini Flash-Lite | Vision Step 1 | Model updates, better alternatives |
| DeepSeek V3.2 | Vision Step 2 / judge / cleanup | New versions, reasoning quality |
| Composio | SaaS integrations | Connected apps, reliability |
| GitHub MCP | Code operations | API changes |
| python-telegram-bot | Telegram interface | API breaking changes |
| SQLite | Event store / ledger | (stable — monitor only) |

**Risk/benefit matrix (action thresholds):**

| Improvement Score (0-10) | Risk Score (0-10) | Action |
|--------------------------|-------------------|--------|
| 0-3 | Any | Monitor — not worth switching |
| 4-6 | 0-4 | Recommend testing |
| 4-6 | 5-10 | Monitor — improvement insufficient for risk |
| 7-10 | 0-5 | Strong recommendation to test |
| 7-10 | 6-8 | Consider — requires deeper Loop 3 analysis |
| 7-10 | 9-10 | Flag critical — exceptional improvement, high risk, full human review |

**Risk factors evaluated:**
- Migration effort (how many CORTEX components depend on this component?)
- Data migration complexity (does switching require moving stored data?)
- Stability of alternative (production-proven vs. experimental?)
- Cost change (cheaper/same/more expensive?)
- Breaking change risk (will CORTEX break during transition window?)

**Research method per component:**
Tier 2 research (Tavily + Exa + Perplexity) — includes real user reports, GitHub issues, community discussions, pricing announcements. Theory alone is insufficient: what are actual users saying? What problems are people hitting? This is explicitly part of the research prompt.

**Output:** Stack assessment report with three buckets: Replace Now / Monitor / Stable. Feeds into Loop 3 same day.

---

## Safety Infrastructure

### Version Manager (`cortex_version_manager.py`)

**Named version pinning:**
```
CORTEX v{phase}.{iteration}  — e.g. v7.0 (Phase G complete), v7.1 (first experiment applied)
Major = phase number | Minor = applied experiment count | Patch = bug fixes
```

**Version report — two layers:**

Human-readable (for you to understand at a glance):
- Version ID, date, stable: YES/NO
- Summary paragraph
- Stack components (key ones, 1 sentence each)
- Changes from previous version: what changed, why, what outcome was expected
- Did it work? Evidence (benchmark score delta, user observations)
- Comparison table to previous version

Agent-readable (extended, for Ruflo or CORTEX self-reference):
- Full component list: name, version, API endpoint, config hash
- Full wiring map: data flow between components
- All experiments that contributed to this version
- Rollback history with reason log

**Pre-experiment checkpoint protocol:**
Before any experiment or stack change:
1. Assert git is clean (no uncommitted changes)
2. Auto-commit with timestamp message
3. Create git tag: `experiment-YYYYMMDD-HHmm`
4. Snapshot FAISS index to `usr/memory/snapshots/{tag}/`
5. Verify snapshot integrity (checksums)
6. Write checkpoint record to SQLite
7. Confirm to user: "Checkpoint created — {tag}. Safe to proceed."

**Rollback:**
1. Double confirmation required (two separate explicit approvals — prevents accidental trigger)
2. `git checkout {tag}`
3. Restore FAISS from snapshot
4. Record rollback event: tag, timestamp, reason (what broke), what failed assumptions, any useful learnings for future
5. Verify integrity post-rollback
6. Notify user: "Rolled back to {tag}. Here is what was recorded as the reason."

**Delete/destructive operations (SurfSense spaces, memory clear, etc.):**
Minimum two explicit human confirmations. No single-click destruction of any memory layer.

### Memory Preservation (All 3 Layers Must Survive Any Code Update)

| Layer | Storage | Code rollback effect | Protection |
|-------|---------|---------------------|------------|
| L1 FAISS | Fly Volume (SQLite path) | No effect (separate volume) | Pre-experiment snapshot |
| L2 Zep/Graphiti | Zep Cloud | No effect (external service) | Never call delete-all |
| L3 SurfSense | SurfSense Cloud | No effect (external service) | Never call clear-space |

Code and memory are architecturally decoupled. `git revert` cannot touch memory. The vulnerability is FAISS local files being corrupted by a bad script — snapshots protect against this.

---

## Storage Architecture

### Event Storage (Raw Events)
**Technology:** SQLite on Fly Volume (same as `cortex_outcome_ledger.py`)
**Location:** `usr/memory/cortex_main/cortex_event_store.db`
**Tables:**
- `struggle_events` — topic, severity, signals, session_id, timestamp
- `tool_calls` — tool_name, success, duration_ms, session_id, timestamp
- `user_corrections` — correction_type, context_snippet, session_id, timestamp
- `latency_events` — task_type, turn_count, session_id, timestamp
- `extension_failures` — extension_name, exception_type, session_id, timestamp
- `benchmark_runs` — run_date, query_id, score, judge_model, timestamp
- `experiment_log` — experiment_id, hypothesis, baseline_score, experimental_score, applied, timestamp

**Volume:** Append-only, low write frequency. Estimated ~10,000 rows/month maximum. Negligible storage.

### Aggregated Intelligence (SurfSense)
**Space:** `cortex_optimization` — completely separate from venture/ops spaces
**Contents:** Daily summaries, weekly rollups, experiment results, operational reports, version records, benchmark history, stack evolution reports
**Estimated volume:** ~200-300 documents/year — manageable
**No leakage:** Retrieval for venture questions queries venture spaces only. `cortex_optimization` space is never queried unless explicitly invoked.

---

## Complete File List

### New Files (25)

**Core infrastructure:**
| File | What |
|------|------|
| `python/helpers/cortex_event_store.py` | SQLite wrapper — all event logging goes through here |
| `python/helpers/cortex_version_manager.py` | Named versions, checkpoint, snapshot, rollback, version reports |

**Loop 1 — Reactive:**
| File | What |
|------|------|
| `python/helpers/cortex_struggle_aggregator.py` | Reads SQLite struggle events → clusters → top 3 hypotheses |
| `python/helpers/cortex_experiment_suite.py` | 20 test queries + rubric definitions |
| `python/helpers/cortex_experiment_judge.py` | DeepSeek primary evaluator + Claude spot-check (10%) |
| `python/helpers/cortex_experiment_runner.py` | Isolated runner: baseline vs. experimental, budget-capped, mutex-locked |
| `python/helpers/cortex_experiment_reporter.py` | Builds structured before/after report |
| `python/helpers/cortex_experiment_applier.py` | Applies approved change via version manager + git |

**Loop 2 — Outcome-Based:**
| File | What |
|------|------|
| `python/helpers/cortex_outcome_attributor.py` | Classifies outcomes: CORTEX / user / external / mixed + autonomy weighting |
| `python/helpers/cortex_outcome_feedback.py` | Outcome ingestion: Telegram checkin + manual input via self_improve tool |
| `python/helpers/cortex_optimization_signal.py` | Outcome delta → knowledge/prior update signal |

**Loop 3 — Architectural:**
| File | What |
|------|------|
| `python/helpers/cortex_operational_reporter.py` | Generates full 10-category operational report (reads SQLite + self_model) |
| `python/helpers/cortex_interagent_protocol.py` | JSON schema, iteration logic, convergence criteria, human report formatter |
| `python/helpers/cortex_ruflo_session_packager.py` | Packages CORTEX operational report as Ruflo session context |

**Loop 4 — Benchmark Drift:**
| File | What |
|------|------|
| `python/helpers/cortex_benchmark_runner.py` | Runs 20-query suite on schedule, stores scores, detects drift |

**Loop 5 — Technology Stack:**
| File | What |
|------|------|
| `python/helpers/cortex_stack_inventory.py` | Authoritative stack definition: component, version, role, dependencies |
| `python/helpers/cortex_stack_researcher.py` | Tier 2 research per component (Tavily + Exa + Perplexity + community signals) |
| `python/helpers/cortex_stack_evaluator.py` | Risk/benefit matrix → action recommendation |

**Agent tool:**
| File | What |
|------|------|
| `python/tools/self_improve.py` | Agent-callable: trigger / check_status / show_report / apply / reject / show_versions / rollback |
| `agents/cortex/prompts/agent.system.tool.self_improve.md` | Tool documentation |

**New extensions:**
| File | What |
|------|------|
| `python/extensions/monologue_end/_62_tool_usage_log.py` | Logs tool calls to SQLite event store |
| `python/extensions/monologue_start/_09_correction_detect.py` | Detects user correction signals in incoming message → logs to SQLite |

**Tests:**
| File | What |
|------|------|
| `tests/test_g_core.py` | Loop 1 tests: aggregation, judging, running, reporting, applying (~25 tests) |
| `tests/test_g_extended.py` | Loop 2-5 tests: attribution, protocol, stack evaluation (~20 tests) |

### Modified Files (6)

| File | What changes |
|------|-------------|
| `python/extensions/monologue_end/_60_struggle_detect.py` | Add SQLite event write (currently only writes to self_model) |
| `python/helpers/cortex_commitment_tracker.py` | Link commitment completion → outcome checkin trigger |
| `python/extensions/monologue_start/_15_register_schedulers.py` | Register all 5 loop scheduled tasks |
| `requirements.txt` | Any new deps |
| `CORTEX_PROGRESS.md` | Phase G status tracking |
| `CORTEX_PLAN.md` | Mark Phase G section as active |

---

## Build Order

Dependencies flow top to bottom. Each group can be built in parallel within the group.

**G-0: Foundation (no deps)**
- `cortex_event_store.py`
- `cortex_version_manager.py`

**G-1: Data collection (depends on G-0)**
- Update `_60_struggle_detect.py` → SQLite
- New `_62_tool_usage_log.py`
- New `_09_correction_detect.py`

**G-2: Loop 1 core (depends on G-0, G-1)**
- `cortex_struggle_aggregator.py`
- `cortex_experiment_suite.py` (no deps — pure data)
- `cortex_experiment_judge.py`
- `cortex_experiment_runner.py` (depends on judge + suite)
- `cortex_experiment_reporter.py`
- `cortex_experiment_applier.py` (depends on version_manager)
- `self_improve.py` tool + prompt doc
- Update `_15_register_schedulers.py` (Loop 1 only first)

**G-3: Operational intelligence (depends on G-0, G-1)**
- `cortex_operational_reporter.py`
- `cortex_benchmark_runner.py` (depends on experiment_suite + experiment_judge)

**G-4: Loop 2 (depends on G-0, commitment_tracker)**
- `cortex_outcome_attributor.py`
- `cortex_outcome_feedback.py`
- `cortex_optimization_signal.py`
- Update `cortex_commitment_tracker.py`
- Update `_15_register_schedulers.py` (add Loop 2)

**G-5: Loop 3 (depends on G-3)**
- `cortex_interagent_protocol.py`
- `cortex_ruflo_session_packager.py`
- Update `_15_register_schedulers.py` (add Loop 3)

**G-6: Loop 5 (depends on research orchestrator)**
- `cortex_stack_inventory.py` (no deps — pure data definition)
- `cortex_stack_researcher.py` (depends on research orchestrator)
- `cortex_stack_evaluator.py`
- Update Loop 3 to accept stack findings
- Update `_15_register_schedulers.py` (add Loop 5, coordinate with Loop 3)

**G-7: Tests (depends on all above)**
- `tests/test_g_core.py`
- `tests/test_g_extended.py`

**G-8: Documentation**
- `CORTEX_PHASE_G_SUMMARY.md`
- Update `CORTEX_PROGRESS.md`
- Update `usr/knowledge/cortex_main/main/cortex_architecture_current.md`
- Three-file documentation standard complete

---

## Scheduled Tasks

| Loop | Task | Frequency | Time (CET) | Depends on |
|------|------|-----------|------------|------------|
| 1 | Experiment cycle | Weekly | Sunday 2am | Struggle log populated |
| 2 | Outcome checkin | Monthly | 1st, 3am | Commitments exist |
| 3 | Architectural review | Bi-monthly | 1st odd months, 4am | Loop 5 ran same day |
| 4 | Benchmark drift | Monthly | 15th, 2am | None |
| 5 | Stack evolution | Bi-monthly | 15th odd months, 3am | Before Loop 3 |

Loop 5 runs at 3am → Loop 3 runs at 4am on same bi-monthly day. Loop 5 findings are input to Loop 3 operational report.

---

## Inter-Agent Protocol (Loop 3) — JSON Schema

### CORTEX → Ruflo
```json
{
  "from": "cortex",
  "round": 1,
  "type": "operational_report",
  "period": "YYYY-MM",
  "struggle_clusters": [
    {"topic": "slovenian_saas_pricing", "event_count": 11, "severity": "high",
     "sample_contexts": ["user asked about B2B pricing...", "..."]}
  ],
  "tool_usage": {
    "calls_by_tool": {"cortex_research_tool": 45, "composio": 0},
    "zero_call_tools": ["composio"],
    "error_rate_by_tool": {"cortex_research_tool": 0.02}
  },
  "latency_hotspots": [
    {"task_type": "tier2_research", "avg_turns": 4.2, "p95_turns": 7}
  ],
  "user_corrections": [
    {"correction_type": "too_generic", "count": 9, "example_contexts": ["..."]}
  ],
  "extension_failures": [
    {"extension": "_20_surfsense_pull", "exception_count": 3, "last_exception": "timeout"}
  ],
  "stack_evolution_findings": null,
  "open_questions_for_ruflo": [
    "Is the 3-hop research pattern architectural or a workaround?",
    "Why does composio show 0 calls — dead or not triggered correctly?"
  ]
}
```

### Ruflo → CORTEX
```json
{
  "from": "ruflo",
  "round": 1,
  "type": "architectural_analysis",
  "findings": [
    {
      "re": "tier2_research_latency",
      "architectural_cause": "Perplexity call is synchronous in current implementation — not intentional design, a workaround from Phase Tool-2",
      "fix_complexity": "low",
      "proposed_fix": "Make Perplexity call async with await, move to parallel with Tavily/Exa",
      "affected_components": ["cortex_research_orchestrator.py"],
      "breaking_risk": "none"
    }
  ],
  "open_questions_for_cortex": [
    "Are the 9 'too generic' corrections clustered in one venture or spread across all?",
    "What is the user message pattern before the surfsense_pull timeouts?"
  ],
  "convergence_assessment": "continue",
  "convergence_rationale": "2 open questions outstanding"
}
```

Iteration continues until `convergence_assessment: "converged"`. CORTEX then generates human report.

---

## Testing Strategy

**All tests mocked — no live LLM calls required for unit tests:**

| Test group | What it verifies |
|------------|-----------------|
| Event store | SQLite writes, reads, date-range queries, schema integrity |
| Struggle aggregator | Clustering logic, hypothesis ranking, deduplication |
| Version manager | Pin/checkpoint/snapshot/rollback flow, double-confirm enforcement |
| Experiment suite | Query loading, rubric structure validation |
| Experiment judge | Rubric evaluation, scoring normalization, spot-check trigger rate |
| Experiment runner | Mutex behavior, budget cap enforcement, baseline/experimental isolation |
| Experiment reporter | Report format, before/after diff generation |
| Experiment applier | File modification, git tag creation, integrity check |
| Outcome attributor | Attribution classification across all axis combinations |
| Interagent protocol | Round validation, convergence detection, schema validation |
| Stack evaluator | Risk/benefit matrix all threshold combinations |
| Benchmark runner | Drift detection threshold, score storage, flag trigger |

**Live test (minimal, manual trigger after build):**
1. Trigger Loop 1 manually via `self_improve` tool
2. Verify struggle events being written to SQLite
3. Verify hypothesis generation from mock struggle data
4. Verify experiment report generated and sent to Telegram
5. Verify version checkpoint created with correct structure
6. Verify rollback point exists and is named correctly

---

## What Defers to Phase G.1

After Phase G is validated and running for 4+ weeks:

**DSPy integration:**
- Automated prompt search: 100+ variants/run vs. 3 manual hypotheses/week
- Same cost per experiment, far more coverage
- Prerequisite: test suite + judge pipeline must exist (Phase G provides both)
- Early use of DSPy (before G.1): pick one high-value prompt (CVS scoring), write 10-15 examples, run DSPy standalone — good pilot test

---

## What Defers to Later

- **Loop 2 real execution:** requires venture cycles to complete with outcome data. Infrastructure built now, tested with synthetic data, runs for real once ventures operate.
- **Loop 3 real execution:** requires 4-6 weeks of operational data for meaningful signal. Infrastructure built now, tested with mock operational report.
- **Loop 5 real execution:** first real run after 3 months of operation. Stack inventory built now. First research run can be triggered manually to verify.
- **Expert Frameworks in SurfSense (Hormozi etc.):** needed for L4 test query to score correctly. If not yet built, L4 becomes an N/A for now.
- **Outcome metrics data pipeline for component-specific optimization:** marketing/venture conversion data ingestion from Airtable and other systems. Designed in architecture, built when first venture has trackable metrics.

---

*Next: build in order G-0 → G-8. First action: draft test queries → `cortex_event_store.py` → `cortex_version_manager.py`.*
