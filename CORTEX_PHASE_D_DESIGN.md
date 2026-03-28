# Phase D — Venture Discovery Engine: Design Document

**Status:** LOCKED — ready to build
**Last Updated:** 2026-03-26
**Prerequisite:** Phase C complete ✅ (research pipeline confirmed, 34/34 tests pass)

---

## What Phase D Is

An opportunity radar that continuously finds, filters, scores, and surfaces venture candidates
aligned with the user's parameters. NOT a standalone system — shares all Phase C infrastructure
(CVS scoring, CortexResearchOrchestrator, SurfSense, OutcomeLedger, Graphiti).

**The flow:**
```
Signal sources (5 types)
        ↓
Three-gate filtering (instant → quick → pre-score)
        ↓
Opportunity queue (ranked, with evidence)
        ↓
User reviews → accept / reject / park
        ↓
Accepted → venture_create (Phase C) with pre-loaded research
        ↓
VentureDNA committed, venture live
```

Phase D is the radar. Phase C is the factory floor it feeds.

---

## Five Signal Sources

All five feed the same opportunity queue through the same gate system.

### Source 1: Autonomous Research Loop (Mode 2 from original plan)
CORTEX generates queries from discovery parameters, runs Tier 1 research cycles,
extracts venture ideas from findings. Off-hours, budget-capped.

### Source 2: Pain Mining
Monitor Reddit (free PRAW API), G2/Capterra reviews (via Exa), App Store reviews
(AppFollow when budget allows — Exa+Firecrawl as free fallback), ProductHunt
(free GraphQL API). Extract: feature requests, complaints with paying-customer evidence,
"I wish X existed", switching announcements.

**Pain signal quality filter:** A complaint only enters the queue if:
- Source shows someone is currently paying for an imperfect solution, OR
- Multiple sources show the same underlying pain (cross-source strength)

### Source 3: Disruption Scanning
Find incumbents with: large user base + active switching intent + engagement decline
+ no lock-in. Sources: "X alternative" search volume (Exa), app review trends (AppFollow
or Exa), ProductHunt abandoned products (free API), Twitter/X departure announcements
(Exa search).

Sub-mode: **App graveyard** — apps with 4+ star ratings, strong user base, zero updates
in 12+ months. Users are stranded and searching. Highest switching urgency signal.

### Source 4: Influencer Monitoring
Track top accounts in target niches. When new content appears:
1. YouTube: RSS feed (free, instant) → auto-transcribe (youtube-transcript-api, free)
2. Extract: tool complaints, feature gaps, "I wish" statements, audience questions
3. Store in Graphiti as: influencer entity → mentioned tool → pain type → date

Signal strength increases when the same complaint appears across multiple influencers
or the same influencer repeatedly over time. Graphiti's temporal graph handles this.

### Source 5: Geographic Arbitrage Scan
Identify US-validated SaaS/tools with no CEE/EU equivalent. Sources: Exa search for
"[category] for [country/language]" gaps + Product Hunt EU traction analysis.
When found: flag as geographic opportunity with "proven demand, low competition" bonus.

---

## Three Discovery Modes (one engine, multiple entry points)

### Mode 1: Interactive Parameter Discovery Session (~10 min)
User defines what kinds of ventures CORTEX should look for.
Free-form input → CORTEX structures into VentureDiscoveryParameters → user confirms.
Output saved to `discovery/params.json`. Reusable until explicitly updated.
This dramatically improves Mode 2 quality (5-10x signal-to-noise improvement).

### Mode 2: Autonomous Background Discovery
CORTEX runs Source 1 (research loops) + Source 3 (disruption scan) + Source 5
(geographic scan) during scheduled off-hours windows. Budget-capped per night.
Does NOT run during active user sessions. Queue reviewed by user at their schedule.

### Mode 3: User-Triggered Deep Dive
User points CORTEX at a specific niche, product, or problem space.
CORTEX immediately runs all 5 signal sources for that target.
Results go to top of queue with "manual trigger" tag.
No budget cap — user explicitly requested it.

---

## Three-Gate Filtering System

Every candidate from every source passes through these gates before entering the queue.
Goal: eliminate cheaply before spending on research.

### Gate 0 — Instant Disqualifiers (free, seconds)
Any one of these = immediate park/discard:
- Requires regulatory approval before launch (financial products, medical, pharma, legal advice)
- Requires hardware before software validates
- Controlled by network-effect giant with no switching intent detected
- Requires >€2K initial capital at current phase
- Core tech doesn't exist yet (needs research breakthrough)

### Gate 1 — Quick Signal Check (~5 min, ~€0.002)
One Exa query + Google Trends check:
- Market trending up or stable? (trending down 2+ years = park)
- "X alternative" search volume — active switching intent? (none = weak, flag)
- Can operate solo + CORTEX? (needs team = park for now)
- B2B enterprise with 6-month sales cycles? (park until Phase G capital)

### Gate 2 — CVS Pre-Score (~€0.003, DeepSeek)
Estimated without full research:
- CORTEX buildability: can 80%+ be automated? (No = red flag)
- Initial capital: <€500 green / €500–2K yellow / >€2K red (at current phase)
- Time-to-first-revenue: <6 weeks green / 6–16 weeks yellow / >16 weeks red
- Strategy type assigned (see strategy taxonomy in memory)
- Scores 2+ red dimensions → parking lot, not queue

**Cost to filter 40 candidates through all gates: ~€0.25 total.**

---

## Opportunity Scoring (9 Filters)

Candidates that pass Gate 2 get full pre-score for queue ranking:

| Filter | Weight | What it checks |
|---|---|---|
| Pain is paid-for currently | High | Someone paying for imperfect solution now |
| Complaint is feature-specific | High | "Missing X" vs generic dissatisfaction |
| Active switching intent | High | "X alternative" volume or departure announcements |
| Build fits our stack | High | AI-first, automatable core, no hardware |
| CEE opportunity | Medium | US-validated OR local market underserved |
| CORTEX buildability | High | 80%+ of operations automatable? Estimate owner hrs/week |
| Initial capital requirement | High | <€500 green, €500–2K yellow, >€2K red |
| Time-to-first-revenue | Medium | How fast can we validate? |
| Strategy type match | Medium | Fits known playbook (see strategy taxonomy) |

Each candidate gets a score, strategy type label, and evidence summary.
Queue sorted by score descending.

---

## Parking Lot

Candidates that fail gates but show promise are NOT discarded — they are parked.

Each parked entry stores:
- Why parked: which gate failed, specific reason
- What would change it: the condition that makes it viable ("viable when capital > €5K")
- Evidence preserved: the signals that made it interesting
- Revisit trigger: date or system condition (e.g., "after Phase E autonomy improvements")
- Expiry: if no revisit condition fires within 6 months, archive to history

The proactive engine (Phase E) checks parked ventures against current state on its
heartbeat and alerts: "Parked venture [X] — revisit condition met."

---

## Switching Friction as Design Principle

Every venture identified through Phase D gets a switching friction assessment as part
of its candidate record. This is not optional — it's a mandatory field.

For disruption targets (Source 3): assess what keeps users with the incumbent.
For all ventures: design the "Migration Kit" concept at discovery time, not post-launch.

Migration Kit minimum spec (planned at discovery, built at launch):
- One-click import from main incumbent
- 30-minute migration guide
- Side-by-side comparison showing exact gains
- White-glove migration offer for first 20 customers (manual, builds case studies)

This is a selling asset and SEO asset ("migrate from X to Y guide") not just UX work.

---

## Data Structures

```python
# D-1: python/helpers/cortex_discovery_params.py

@dataclass
class VentureDiscoveryParameters:
    market_domains: List[str]           # ["SaaS", "content", "data services"]
    geography: str                      # "Slovenia", "EU", "global"
    min_cvs_score: float                # Default 45 — minimum to enter queue
    min_ai_run_autonomy: float          # Default 50 — minimum autonomy required
    max_capital_requirement: Optional[float]  # EUR cap
    languages: List[str]                # ["sl", "en"]
    excluded_domains: List[str]         # Hard exclusions
    strategy_preferences: List[str]     # ["SaaS Wrapper", "Geographic Rollout", ...]
    autonomy_weight: float              # 0-100, how much to weight AI autonomy in ranking
    created_at: datetime
    last_updated: datetime
    version: int                        # Auto-increment on update

@dataclass
class PainSignal:
    source: str                         # "reddit", "g2", "app_store", "influencer", "twitter"
    source_url: str
    raw_text: str
    extracted_pain: str                 # Cleaned pain statement
    tool_mentioned: Optional[str]       # The product being complained about
    paying_evidence: bool               # Evidence they're currently paying for something
    date: datetime
    strength: int                       # 1-5: 1=single mention, 5=cross-source recurring

@dataclass
class InfluencerWatch:
    platform: str                       # "youtube", "twitter", "substack"
    handle: str
    channel_id: Optional[str]
    niche: str
    last_checked: datetime
    subscriber_count: Optional[int]

@dataclass
class VentureCandidate:
    id: str                             # UUID
    name: str                           # Working title
    source: str                         # Which signal source produced this
    source_signals: List[PainSignal]    # Evidence that triggered this candidate
    niche: str
    market: str
    language: str
    strategy_type: str                  # From strategy taxonomy
    gate_scores: Dict[str, str]         # Gate 0/1/2 results
    cvs_prescore: float                 # Pre-score (Gate 2)
    opportunity_summary: str            # 2-3 sentence summary
    switching_friction_notes: str       # Assessment of incumbent lock-in
    geographic_bonus: bool              # CEE arbitrage opportunity?
    status: str                         # "pending_review", "accepted", "rejected", "parked"
    park_reason: Optional[str]
    park_revisit_condition: Optional[str]
    park_revisit_date: Optional[datetime]
    created_at: datetime
    research_context: Optional[str]     # Full Tier 1 output if already run — passed to venture_create
```

---

## Components (D-1 → D-11)

| ID | File | What |
|----|------|------|
| D-1 | `python/helpers/cortex_discovery_params.py` | All dataclasses: VentureDiscoveryParameters, VentureCandidate, PainSignal, InfluencerWatch, ParkingLot + persistence |
| D-2 | `python/helpers/cortex_signal_ingestion.py` | Signal sources: Reddit PRAW, Exa multi-source (G2/Capterra/ProductHunt/reviews), YouTube Data API stub |
| D-3 | `python/helpers/cortex_pain_clustering.py` | Cross-source dedup, pain aggregation, Graphiti storage for temporal signals |
| D-4 | `python/helpers/cortex_influencer_monitor.py` | YouTube RSS monitoring, youtube-transcript-api, pain extraction via DeepSeek |
| D-5 | `python/helpers/cortex_disruption_scanner.py` | Incumbent weakness detection, app graveyard scan, "X alternative" volume check |
| D-6 | `python/helpers/cortex_discovery_gates.py` | Gate 0/1/2 logic, fast disqualifiers, quick signal check, CVS pre-score |
| D-7 | `python/helpers/cortex_opportunity_scorer.py` | 9-filter scoring, strategy type assignment, switching friction assessment |
| D-8 | `python/helpers/cortex_discovery_engine.py` | Orchestrates all sources + gates. Mode 1 (interactive), Mode 2 (autonomous), Mode 3 (triggered) |
| D-9 | `python/tools/venture_discover.py` | Agent tool: discover/run/queue/review/accept/reject/park/params/influencers actions |
| D-10 | `python/extensions/monologue_start/_08_discovery_context.py` | Inject queue length + top candidate preview when queue non-empty |
| D-11 | Prompts + role.md update | Tool doc + routing table entry |

---

## Tool Actions (venture_discover)

| Action | What it does |
|--------|-------------|
| `discover` | Start Mode 1: interactive parameter discovery session |
| `run [n]` | Mode 3: run n discovery cycles immediately across all sources (default 10) |
| `queue` | Show pending review queue sorted by CVS pre-score |
| `review <id>` | Full detail: pain signals, CVS pre-score, switching friction, strategy type, research if available |
| `accept <id>` | Move to accepted → calls venture_create._initiate() with research_context pre-loaded |
| `reject <id> [reason]` | Mark rejected → rejected.json. Reason stored for pattern learning. |
| `park <id> [condition] [date]` | Move to parking lot with revisit condition and/or date |
| `parked` | Show parking lot with revisit conditions |
| `unpark <id>` | Move back to queue for review |
| `params` | Show current discovery parameters |
| `update_params` | Launch Mode 1 to update any parameter field |
| `influencers` | Show watched influencers list |
| `add_influencer <url> <niche>` | Add YouTube/Twitter account to monitoring list |
| `signals <niche>` | Show raw pain signals for a niche across all sources |

---

## Storage Structure

```
usr/memory/cortex_main/discovery/
  params.json              ← active VentureDiscoveryParameters
  params_history/          ← archived versions (auto-saved on each update)
  queue.json               ← VentureCandidate[] (status: pending_review)
  rejected.json            ← rejected candidates (dedup + pattern learning)
  parked.json              ← parking lot (with revisit conditions)
  accepted.json            ← candidates accepted → ventures
  influencers.json         ← InfluencerWatch[] (watched accounts)
  signals/                 ← PainSignal[] by niche (for dedup across cycles)
    {niche_slug}.json
```

---

## Tool Inventory (cost-first selection)

| Source | Tool | Cost | Priority |
|--------|------|------|----------|
| Reddit | PRAW (Python Reddit API Wrapper) | Free (rate-limited) | D-2, Phase D launch |
| App reviews, G2, Capterra | Exa + Firecrawl (already have) | Per query | D-2, Phase D launch |
| ProductHunt | ProductHunt GraphQL API | Free | D-2, Phase D launch |
| YouTube monitoring | YouTube Data API v3 | Free quota | D-4, Phase D launch |
| YouTube transcripts | youtube-transcript-api | Free | D-4, Phase D launch |
| Trend detection | Exa similarity search (already have) | Per query | D-5, Phase D launch |
| App review dedicated | AppFollow API | $29/mo | Phase D upgrade — if Exa coverage insufficient |
| Trend detection dedicated | Exploding Topics API | $39/mo | Phase D upgrade — if needed |
| Browser automation (no-API sources) | browser-use (open source) | Free | Phase D upgrade — for JS-rendered pages |

**Principle:** Launch with free tools. Upgrade only when free coverage demonstrably insufficient.

---

## Cost Model

| Operation | Model | Cost |
|---|---|---|
| Gate 1 quick scan (per candidate) | Exa query | ~€0.002 |
| Gate 2 pre-score (per candidate) | DeepSeek V3.2 | ~€0.003 |
| Autonomous research cycle (5 Tavily + 3 Exa queries) | APIs | ~€0.03–0.06 |
| Pain signal extraction from Reddit/reviews | DeepSeek V3.2 | ~€0.001/signal |
| YouTube transcript extraction | Free | €0 |
| Influencer pain extraction | DeepSeek V3.2 | ~€0.003/video |
| **Full pipeline: 40 raw → 5 queue entries** | | **~€0.25** |
| **30 autonomous cycles/night** | | **~€1.00–2.10/night** |
| **Default nightly budget cap** | | **€3.00 hard max** |

---

## Integration Points

| From → To | How |
|-----------|-----|
| Phase D → Phase C | `accept <id>` → `venture_create._initiate(prior_research=candidate.research_context)` |
| Phase D → Graphiti | Pain signals stored as episodes: source → pain → tool → date (temporal aggregation) |
| Phase D → SurfSense | Discovery sessions → `cortex_ventures` space. Accepted candidates → `cortex_main` space |
| Phase D → Phase E | Mode 2 nightly scheduling registered in `_15_register_schedulers.py` |
| Phase D → Phase E | Parking lot revisit conditions checked by proactive engine heartbeat |

---

## Architectural Constraints (Phase D respects)

All constraints in `cortex_architecture_current.md` apply. Phase D specific:

| Constraint | Reason | Valid until |
|---|---|---|
| Pain signal only enters queue if paying-for-imperfect evidence exists | Signal quality — complainers ≠ payers | Permanent |
| No paid tool subscriptions until free alternatives proven insufficient | Cost discipline | Until revenue justifies |
| Budget cap is hard-coded max, not default — user can only reduce, not remove | Risk management | Permanent |
| Mode 2 does NOT run during active user sessions | Performance + UX | Until dedicated compute available |
| Strategy type assigned at Gate 2 — not post-queue | Strategy informs scoring, not decoration | Permanent |

---

## Build Order

```
D-1  → Data structures (no dependencies)
D-6  → Gate logic (depends D-1 only — build early, test independently)
D-7  → Scoring (depends D-1, D-6)
D-2  → Signal ingestion (depends D-1, D-6 — can stub D-6 initially)
D-3  → Pain clustering (depends D-2, Graphiti already live)
D-4  → Influencer monitor (depends D-2 patterns — can build in parallel with D-3)
D-5  → Disruption scanner (depends D-2, D-6)
D-8  → Discovery engine orchestrator (depends D-1 through D-7)
D-9  → venture_discover tool (depends D-8)
D-10 → Extensions (context injection, scheduler — depends D-9 working)
D-11 → Prompt docs + role.md (final, after D-9 working)
```

---

## Verification Tests

| Test | What it verifies |
|------|-----------------|
| D-T1 | Mode 1 param session → params saved to disk, fields complete |
| D-T2 | Gate 0: a hardware-required idea is immediately disqualified |
| D-T3 | Gate 1: declining-market idea gets flagged (doesn't crash) |
| D-T4 | Gate 2: candidate below min_cvs_score doesn't enter queue |
| D-T5 | 5 autonomous research cycles → at least 1 candidate enters queue |
| D-T6 | Pain signal extraction from Reddit returns structured PainSignal objects |
| D-T7 | Influencer: add YouTube URL → RSS monitored → transcript extracted on new video |
| D-T8 | Accept candidate → venture_create launches with research_context pre-loaded |
| D-T9 | Reject → candidate in rejected.json, not re-surfaced in next cycle |
| D-T10 | Park with revisit date → proactive engine surfaces on that date |
| D-T11 | Budget cap enforced — autonomous mode stops at configured cap |
| D-T12 | Cross-source: same pain in Reddit + G2 → signal strength = 2, single queue entry |

---

## Phase D Completion Deliverables

After Phase D passes all D-T tests, create (following the three-file standard):
1. `usr/knowledge/cortex_main/main/phase_d_architecture.md`
2. `CORTEX_PHASE_D_SUMMARY.md`
3. Update `usr/knowledge/cortex_main/main/cortex_architecture_current.md`

Update `CORTEX_PROGRESS.md` and `CORTEX_DECISIONS.md` with Phase D decisions (D-047 onward).
