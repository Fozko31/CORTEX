# venture_discover

Runs the full venture discovery pipeline for a specific niche and market.
Evaluates pain signal volume (D-2), clusters pain themes (D-3), scans incumbent
tool disruption opportunities (D-5), scores via all gates, and outputs a ranked
CVS score. High-scoring candidates are automatically added to the discovery queue.

## When to use

- User asks "scan this niche", "is there opportunity in X", "research Y for a venture"
- User wants to know if a niche passes the gates (regulatory, capital, AI autonomy)
- User wants to see disruption targets in a market
- User says "add this to the discovery queue"

## Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `niche` | string | required | The niche to evaluate. Be specific: "local SEO for restaurants" not "SEO" |
| `market` | string | `"global"` | Geographic market: "Slovenia", "EU", "US", "global" |
| `mode` | string | `"fast"` | `"full"` (with influencer monitoring), `"fast"` (no influencers), `"scan_only"` (disruption only) |
| `max_cost_eur` | float | `0.5` | Hard budget cap in EUR. Full run costs ~EUR 0.05-0.09 |

## Modes

| Mode | Steps | Cost | When |
|------|-------|------|------|
| `fast` | D-2 signals + D-3 clusters + D-5 disruption + gates + scoring | ~EUR 0.025 | Default. Most discovery tasks. |
| `full` | All fast steps + D-4 influencer monitoring | ~EUR 0.05-0.09 | When you want transcript-level pain intelligence. Slower. |
| `scan_only` | D-5 disruption scan only (reads stored signals) | ~EUR 0.017 | When signals already collected and you just want disruption targets. |

## Outcomes

- `queued` — Niche scored above threshold. Candidate in queue with ID.
- `rejected` — Score too low. Reason provided. Niche can be re-evaluated later.
- `parked` — Gate 0 or Gate 1 blocked it (regulatory, no demand). Niche flagged.
- `error` — Pipeline failure. Errors listed in warnings.

## Examples

```
venture_discover(niche="AI agent automation for accountants", market="EU")

venture_discover(
    niche="restaurant local SEO agency",
    market="Slovenia",
    mode="full",
    max_cost_eur=0.15
)

venture_discover(niche="property management SaaS for landlords", market="global", mode="fast")
```

## Output

Returns a structured summary including:
- CVS score and strategy type
- Pain summary (top themes from D-3 clustering)
- Disruption targets (top tools vulnerable in this niche)
- Candidate ID (if queued) — use this with `venture_manage` to accept, park, or reject
- Steps completed and cost estimate

## Queue management

After discovery, candidates sit in the queue with their CVS score. Use `venture_manage` to:
- List queue: `venture_manage(action="queue")`
- Accept a candidate: `venture_manage(action="accept", candidate_id="...")`
- Park with note: `venture_manage(action="park", candidate_id="...", reason="...")`
