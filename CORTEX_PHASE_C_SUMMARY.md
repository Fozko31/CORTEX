# Phase C — Venture Machine: Summary

**Completed:** 2026-03-26 | **Tests:** 34/34 PASS | **Live validation:** scan_tier1 → 75% confidence, real data
**Human-readable reference. For CORTEX-facing detail see `phase_c_architecture.md`.**

---

## What Phase C Built

Phase C transforms CORTEX from a research assistant into a venture factory. It can now:

1. **Create ventures** through a guided conversational flow with real market research
2. **Score ventures** using an 8-dimension CVS (Customer Value Score) framework
3. **Size positions** using Kelly Criterion for any capital deployment decision
4. **Manage a portfolio** of ventures with persistent memory across sessions
5. **Synthesize patterns** across ventures to find shared insights and risks

---

## How to Use It

**Create a venture:**
Just tell CORTEX: *"I want to create a venture around [idea]"*

CORTEX will research the market (Tavily + Exa, ~€0.02), ask gap-filling questions,
score with CVS, let you review, then confirm and persist everything.

**Manage ventures:**
- *"List my ventures"* → all active ventures with CVS scores
- *"Status of [name]"* → full DNA, research findings, open questions
- *"Health check [name]"* → SurfSense space + ledger history
- *"Activate [name]"* → sets as active context, injected every turn
- *"Kelly sizing: capital €X, edge Y%, odds Z:1"* → recommended position size

---

## The Creation Flow

```
User: "create venture X"
         ↓
   Parse brief [DeepSeek V3.2]
   → type, market, goals, constraints
         ↓
   Tier 1 Research [Tavily + Exa]
   → market size, keywords, competitors, opportunities
         ↓
   Gap Analysis [DeepSeek V3.2]
   → 0–5 brain-picking questions
         ↓
   Q&A with user
         ↓
   Synthesis [Claude Sonnet 4.6]
   → VentureDNA + CVS scoring
         ↓
   User reviews → approves
         ↓
   Crystallization
   → disk + OutcomeLedger + SurfSense
```

---

## CVS Score Dimensions

| Dimension | What it measures |
|-----------|-----------------|
| Market Size | TAM relative to build effort |
| Problem Severity | Pain intensity + frequency |
| Solution Uniqueness | Differentiation vs. alternatives |
| Implementation Ease | Build complexity (inverted) |
| Distribution Clarity | Go-to-market path clarity |
| AI Setup Autonomy | % of setup CORTEX can automate |
| AI Run Autonomy | % of operations CORTEX can run |
| Risk Level | Lower is better |

**Verdicts:** ≥75 AUTO_PROCEED / 60–74 PROCEED_WITH_CAUTION / 45–59 INVESTIGATE_FURTHER / <45 DISCARD

---

## Files Created in Phase C

| File | Purpose |
|------|---------|
| `python/helpers/cortex_venture_dna.py` | VentureDNA model, CVS, Kelly, cross-venture synthesis |
| `python/helpers/cortex_outcome_ledger.py` | Decision tracking, ROI, Kelly math, SQLite |
| `python/helpers/cortex_venture_discovery.py` | Market research scanner, Tier 1/2, gap analysis |
| `python/tools/venture_create.py` | Conversational venture creation tool |
| `python/tools/venture_manage.py` | Portfolio management tool |
| `python/extensions/monologue_start/_07_venture_context.py` | DNA injection per turn |
| `agents/cortex/prompts/agent.system.tool.venture_create.md` | Tool documentation |
| `agents/cortex/prompts/agent.system.tool.venture_manage.md` | Tool documentation |

---

## Key Design Decisions (see CORTEX_DECISIONS.md D-042 through D-046)

- CVS has 8 dimensions including AI autonomy scores (differentiates CORTEX from generic frameworks)
- Kelly Criterion is mandatory — no fixed position sizing ever
- Research always precedes CVS — CVS without Tier 1 data is invalid
- Challenge-first — CORTEX challenges bad venture inputs before proceeding
- Research caching designed (TTL by venture type, 9-category cache display) — not yet built
- Voice: Kokoro TTS primary (local/private), Inworld AI fallback. Groq Whisper for STT.

---

## Phase C → Phase D Connection

Phase D (Venture Discovery) is the opportunity radar that feeds Phase C.

```
Phase D: discovers opportunities (pain mining, disruption scanner, influencer monitor)
               ↓
         opportunity queue (ranked, filtered, surfaced to user)
               ↓
         user selects one
               ↓
Phase C: venture_create tool runs with prior_research context
               ↓
         VentureDNA committed, venture live
```

Phase C is the factory floor. Phase D is the radar that feeds it.
