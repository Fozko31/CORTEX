# CORTEX Phase D — Venture Discovery Engine
## Human Summary

**Status:** COMPLETE | **Built:** 2026-03-26
**Tests:** 188 unit tests PASS + 84/84 holistic integration tests PASS

---

## What Was Built

Phase D gives CORTEX the ability to autonomously find business opportunities by mining real pain signals from communities, clustering them into themes, scanning incumbent tools for disruption vulnerabilities, and scoring the result — without the user having to do any of this manually.

**In plain terms:** You configure CORTEX with niches you're interested in. It watches those markets, collects what people are complaining about in forums and review sites, identifies the tools that are failing those people, scores each opportunity, and presents you with a ranked list of candidates worth pursuing. Overnight, unattended.

---

## The Pipeline (What Actually Happens)

When you run `venture_discover(niche="AI agent automation for accountants", market="EU")`:

1. **Gate 0 (free, instant)** — Regulatory check. Is this niche legal, viable, not excessively capital-intensive? Pharmaceutical licensing, weapons, heavy finance regulation → auto-parked. No API cost.

2. **D-2: Pain Signal Ingestion** — CORTEX searches G2, Capterra, Reddit, App Store reviews for your niche using Tavily + Exa. Extracts `PainSignal` objects: source, complaint text, sentiment, severity.

3. **Gate 1 (cost gate)** — How many signals? How diverse (forum vs. review site vs. podcast)? If signal density is too low, pipeline stops before spending money on expensive steps. Red = park. Yellow = continue with reduced scope. Green = full pipeline.

4. **D-3: Pain Clustering** — LLM groups signals by semantic theme. "Software is too slow" + "crashes during export" + "freezes on large files" → cluster: "Performance issues / reliability". Clusters get severity scores.

5. **D-4: Influencer Monitoring** (only in `mode="full"`) — Finds YouTube channels, podcasts, newsletters in the niche. Scrapes recent transcripts via Firecrawl. Extracts additional pain signals from real creator conversations.

6. **D-5: Disruption Scanner** — Scores incumbent tools on 7 dimensions:
   - Complaint volume (how loud is the community anger)
   - Pricing vulnerability (per-seat traps, surprise billing, steep tiers)
   - Feature stagnation (changelog frequency, "missing X" complaints)
   - Stranded segment (who the tool abandoned inside its own user base)
   - Competitor emergence (new entrants already targeting this)
   - Support degradation (response time trends, CSAT drops)
   - Rating drift (G2 / App Store rating changes over time)

   Outputs: disruption window (open-critical / open / narrowing / closed) and approach (disrupt / partner / wrap).

7. **Gate 2 (LLM pre-score)** — Uses all gathered data to run a CVS pre-score. Checks uniqueness, market saturation, AI autonomy feasibility. Reject if too crowded, no AI leverage, or no clear path.

8. **D-6: Opportunity Score** — Full CVS score across all 8 dimensions (same dimensions as venture_create). Produces a `VentureCandidate` with a final score.

9. **Queue or reject** — Score above threshold → added to queue with a candidate ID. Below → rejected with reason.

---

## Three Operating Modes

| Mode | What runs | Cost | When to use |
|------|-----------|------|-------------|
| `fast` (default) | D-2 + D-3 + D-5 + Gate 2 + D-6 | ~€0.025 | Default. Most discovery tasks. |
| `full` | Everything above + D-4 influencer monitoring | ~€0.05–0.09 | When you want transcript-level pain intelligence |
| `scan_only` | D-5 disruption scan only (reads stored signals) | ~€0.017 | When signals already collected, just want disruption targets |

---

## Autonomous Mode

Set `CORTEX_DISCOVERY_AUTO=1` in your environment. CORTEX registers a daily cron job at 03:00. It reads your configured `target_niches` from `VentureDiscoveryParameters` and runs the fast pipeline for each — up to 5 niches per run, €0.10 max per niche. Results queue automatically. You wake up and check what landed.

Configure niches: update `usr/memory/cortex_main/discovery_params.json` with a `target_niches` list.

---

## What Gets Queued

Every candidate in the queue has:
- **CVS score** — same 8-dimension score used in venture_create
- **Strategy type** — Fast Follower / Disruption / Jobs to Be Done / etc.
- **Pain summary** — top clusters with severity
- **Disruption targets** — which tools are vulnerable and how
- **Candidate ID** — to accept, park, or reject via `venture_manage`

---

## Queue Management

```
venture_manage(action="queue")                          → list all candidates
venture_manage(action="accept", candidate_id="...")     → promote to active venture creation
venture_manage(action="park", candidate_id="...", reason="...") → hold for later
venture_manage(action="reject", candidate_id="...")     → discard
```

Accepted candidates flow directly into `venture_create` (the Phase C tool), skipping the initial research phase because discovery already ran it.

---

## Files Created

| File | Purpose |
|------|---------|
| `python/helpers/cortex_discovery_orchestrator.py` | D-8: 8-step pipeline, budget gating, DiscoveryResult |
| `python/tools/venture_discover.py` | D-9: Agent-callable tool (fast/full/scan_only modes) |
| `python/helpers/cortex_discovery_scheduler.py` | D-10: Cron registration + autonomous loop runner |
| `python/extensions/system_prompt/_10_discovery_context.py` | D-10: Queue summary injected into system prompt |
| `python/extensions/monologue_start/_15_register_schedulers.py` | D-10: Updated to register discovery scheduler |
| `agents/cortex/prompts/agent.system.tool.venture_discover.md` | D-11: Tool documentation for CORTEX |
| `agents/cortex/prompts/agent.system.main.role.md` | D-11: Updated routing table to include venture_discover |
| `tests/test_d5_disruption_scanner.py` | 70 unit tests for D-5 |
| `tests/test_d8_discovery_orchestrator.py` | 52 unit tests for D-8 |

Previously built (D-1 through D-7) were done in the prior session — pain signals, clustering, influencer monitor, opportunity gates, disruption scanner, opportunity scorer, candidate queue, discovery params.

---

## Connection to Phase C (Venture Machine)

Phase D is the top of the funnel. Phase C is the execution layer.

- **Phase D** → finds and scores opportunities → queues candidates
- **Phase C** → takes a candidate from the queue → runs 9-step creation flow → produces a confirmed venture with full DNA, SurfSense spaces, OutcomeLedger entry

Together: **D discovers → C creates → OutcomeLedger tracks ROI → (Phase G eventually) self-optimizes the discovery criteria based on which ventures actually made money.**

---

## What's Next

Phase C and Phase D are both complete. The next layer is:

| Phase | What | Why now |
|-------|------|---------|
| **E** | Background processes, NEVER STOP protocol, memory backup, proactive engine, weekly digest | Operational reliability — CORTEX should survive restarts, report its own performance, stay conscious across gaps |
| **F** | Telegram + Voice | Mobile-first access, voice commands |
| **G** | Self-optimization loop | CORTEX improves its own discovery criteria based on which leads convert |

User decides priority.
