"""
CORTEX Disruption Scanner -- Phase D, D-5
==========================================

Identifies incumbent tools in a niche that are vulnerable to disruption,
suitable for partnership, or wrappable with AI automation.

Two-phase combined pipeline (always both, not either/or):
  Phase 1 -- D-4 feed: aggregate tools_mentioned from stored pain signals
             (pre-ranked by complaint frequency, near-zero cost)
  Phase 2 -- Independent scan: Exa discovery, G2/Capterra, ProductHunt,
             pricing/acquisition signals, competitor emergence

All candidates scored on 7 dimensions and merged into a unified ranked list.

Three approach types (map to Gate 2 strategy assignment):
  "disrupt" -> Disruption, Fast Follower, Niche Domination
  "partner" -> Picks and Shovels, SaaS Wrapper
  "wrap"    -> SaaS Wrapper

Disruption windows anchored to current date (2026-03-26):
  open-critical  < 1 month since trigger event
  open           1-3 months
  narrowing      3-6 months
  closed         > 6 months (users have settled or migrated)

Cost: ~EUR 0.017 per niche scan (5 tools x EUR 0.003 + EUR 0.002 discovery)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from python.helpers.cortex_discovery_params import PainSignal, load_signals


# ─────────────────────────────────────────────────────────────────────────────
# Current date anchor (2026 — not datetime.now() to avoid year drift in prompts)
# ─────────────────────────────────────────────────────────────────────────────

def _current_date() -> datetime:
    """Returns current date. Centralised so prompts stay year-accurate."""
    return datetime.now()


def _current_year_range() -> str:
    """Returns '2025 OR 2026' style string for Exa queries."""
    now = _current_date()
    return f"{now.year - 1} OR {now.year}"


# ─────────────────────────────────────────────────────────────────────────────
# Data Model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DisruptionTarget:
    tool_name: str
    niche: str
    disruption_score: float                    # 0-100 composite
    disruption_signals: List[str]              # evidence items (human-readable)
    stranded_segment: Optional[str]            # which user segment is being abandoned
    recommended_strategies: List[str]          # from taxonomy
    approach: str                              # "disrupt" | "partner" | "wrap"
    disruption_window: str                     # "open-critical"|"open"|"narrowing"|"closed"|"unknown"
    window_trigger_date: Optional[str]         # YYYY-MM of triggering event
    timing_signal: str                         # "early" | "mid" | "crowded"
    sourced_from_d4: bool                      # True if surfaces via D-4 tools_mentioned
    partnership_viable: bool
    dimension_scores: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "niche": self.niche,
            "disruption_score": self.disruption_score,
            "disruption_signals": self.disruption_signals,
            "stranded_segment": self.stranded_segment,
            "recommended_strategies": self.recommended_strategies,
            "approach": self.approach,
            "disruption_window": self.disruption_window,
            "window_trigger_date": self.window_trigger_date,
            "timing_signal": self.timing_signal,
            "sourced_from_d4": self.sourced_from_d4,
            "partnership_viable": self.partnership_viable,
            "dimension_scores": self.dimension_scores,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Scoring Weights
# ─────────────────────────────────────────────────────────────────────────────

_DIMENSION_WEIGHTS = {
    "complaint_volume":      0.20,
    "pricing_vulnerability": 0.20,
    "feature_stagnation":    0.15,
    "stranded_segment":      0.15,
    "competitor_emergence":  0.15,
    "support_degradation":   0.10,
    "rating_drift":          0.05,
}

assert abs(sum(_DIMENSION_WEIGHTS.values()) - 1.0) < 0.001


# ─────────────────────────────────────────────────────────────────────────────
# Disruption Window Calculation
# ─────────────────────────────────────────────────────────────────────────────

def calculate_disruption_window(
    trigger_date_str: Optional[str],
    event_type: str = "pricing",
) -> Tuple[str, Optional[str]]:
    """
    Calculate how open the disruption window is based on trigger event recency.
    Anchored to current actual date.

    Pricing events: window closes faster (users decide quickly on price)
      < 1 month  -> open-critical
      1-3 months -> open
      3-6 months -> narrowing
      > 6 months -> closed

    Acquisition events: window stays open longer (trust rebuilds slowly)
      < 3 months  -> open-critical
      3-6 months  -> open
      6-12 months -> narrowing
      > 12 months -> closed

    Returns (window_label, trigger_date_str).
    """
    if not trigger_date_str:
        return "unknown", None

    now = _current_date()
    for fmt, length in [("%Y-%m-%d", 10), ("%Y-%m", 7), ("%Y", 4)]:
        try:
            trigger = datetime.strptime(trigger_date_str[:length], fmt)
            days_ago = (now - trigger).days
            break
        except ValueError:
            continue
    else:
        return "unknown", trigger_date_str

    if event_type == "acquisition":
        if days_ago < 90:
            return "open-critical", trigger_date_str
        elif days_ago < 180:
            return "open", trigger_date_str
        elif days_ago < 365:
            return "narrowing", trigger_date_str
        else:
            return "closed", trigger_date_str
    else:  # pricing or default
        if days_ago < 30:
            return "open-critical", trigger_date_str
        elif days_ago < 90:
            return "open", trigger_date_str
        elif days_ago < 180:
            return "narrowing", trigger_date_str
        else:
            return "closed", trigger_date_str


# ─────────────────────────────────────────────────────────────────────────────
# Approach Determination
# ─────────────────────────────────────────────────────────────────────────────

def determine_approach(dimension_scores: Dict[str, float]) -> Tuple[str, List[str], bool]:
    """
    Determine disruption approach and recommended strategies from dimension scores.

    Returns: (approach, recommended_strategies, partnership_viable)
    """
    complaint = dimension_scores.get("complaint_volume", 0)
    pricing = dimension_scores.get("pricing_vulnerability", 0)
    stagnation = dimension_scores.get("feature_stagnation", 0)
    stranded = dimension_scores.get("stranded_segment", 0)

    # High disruption signals -> build a replacement
    if complaint >= 60 and (stagnation >= 50 or pricing >= 60):
        approach = "disrupt"
        strategies = []
        if stranded >= 60:
            strategies.append("Niche Domination")
            strategies.append("Disruption")
        else:
            strategies.append("Fast Follower")
            strategies.append("Disruption")
        partnership_viable = False

    # High satisfaction + specific gap -> build the missing piece, sell into their base
    elif complaint < 50 and stranded >= 50:
        approach = "partner"
        strategies = ["Picks and Shovels", "SaaS Wrapper"]
        partnership_viable = True

    # Strong infrastructure, thin automation/UX layer -> wrap with AI
    elif stagnation < 40 and complaint >= 40:
        approach = "wrap"
        strategies = ["SaaS Wrapper"]
        partnership_viable = True

    # Default: disrupt if enough signals, else partner
    elif complaint >= 50:
        approach = "disrupt"
        strategies = ["Fast Follower", "Niche Domination"]
        partnership_viable = False
    else:
        approach = "partner"
        strategies = ["Picks and Shovels"]
        partnership_viable = True

    return approach, strategies, partnership_viable


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 -- D-4 Feed (aggregate tools from stored pain signals)
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_tools_from_d4(niche: str) -> Dict[str, Dict[str, Any]]:
    """
    Read stored pain signals for the niche and aggregate tool mentions.
    Returns {tool_name: {"count": N, "paying_evidence": N, "strength_sum": N}}.
    Near-zero cost -- reads local JSON files written by D-2 and D-4.
    """
    signals: List[PainSignal] = load_signals(niche)
    tool_counts: Dict[str, Dict[str, Any]] = {}

    for s in signals:
        if not s.tool_mentioned:
            continue
        tool = s.tool_mentioned.strip()
        if len(tool) < 2:
            continue
        if tool not in tool_counts:
            tool_counts[tool] = {"count": 0, "paying_count": 0, "strength_sum": 0}
        tool_counts[tool]["count"] += 1
        if s.paying_evidence:
            tool_counts[tool]["paying_count"] += 1
        tool_counts[tool]["strength_sum"] += s.strength

    # Sort by weighted score (paying mentions count more)
    for tool in tool_counts:
        d = tool_counts[tool]
        d["d4_score"] = d["count"] * 1.0 + d["paying_count"] * 1.5 + d["strength_sum"] * 0.5

    return dict(sorted(tool_counts.items(), key=lambda x: x[1]["d4_score"], reverse=True))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 -- Independent Tool Discovery
# ─────────────────────────────────────────────────────────────────────────────

async def discover_tools_independently(
    niche: str,
    market: str = "global",
    agent=None,
) -> List[str]:
    """
    D-5's own discovery: finds incumbent tools via Exa searches independent
    of what influencers have mentioned. Complements D-4 feed.

    Searches:
      - "best [niche] tool/software" -> established incumbents
      - "[niche] tool alternative" -> tools people are actively leaving
      - ProductHunt [niche] 2025 OR 2026 -> recent competitor launches

    Returns: List of tool names (strings), deduped.
    Cost: ~EUR 0.002 (2 Exa searches + 1 DeepSeek name extraction).
    """
    try:
        from python.helpers.cortex_exa_client import CortexExaClient
        from python.helpers.cortex_model_router import CortexModelRouter
        from python.cortex.dirty_json import DirtyJson

        exa_key = os.getenv("EXA_API_KEY", "")
        exa = CortexExaClient(api_key=exa_key)
        year_range = _current_year_range()

        # Query 1: established incumbents
        results_incumbents = await exa.search(
            f"best {niche} software tool review comparison {year_range}",
            num_results=8,
            use_autoprompt=True,
        )

        # Query 2: switching intent (tools people are leaving)
        results_switching = await exa.search(
            f"{niche} tool alternative switch replace {year_range}",
            num_results=8,
            use_autoprompt=False,
        )

        # Query 3: competitor emergence (ProductHunt launches)
        results_launches = await exa.search(
            f"site:producthunt.com {niche} tool {year_range}",
            num_results=5,
            use_autoprompt=False,
        )

        all_snippets = "\n".join(
            f"[{r.title}]: {r.content[:150]}"
            for r in (results_incumbents + results_switching + results_launches)[:20]
        )

        prompt = (
            f"Niche: '{niche}' | Market: {market}\n\n"
            f"Search results:\n{all_snippets}\n\n"
            "Extract all tool/software/product NAMES mentioned. "
            "Return only tool names, not company names or generic terms. "
            "JSON array of strings only:\n"
            '["ToolName1", "ToolName2", ...]'
        )

        raw = await CortexModelRouter.call_routed_model(
            "classification",
            "Extract product/tool names from search results. JSON array only.",
            prompt,
            agent,
        )
        parsed = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if isinstance(t, str) and 1 < len(t) < 50][:20]

    except Exception as e:
        print(f"[CORTEX disruption_scanner] Independent discovery error: {e}")

    return []


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 -- Score One Tool on All 7 Dimensions
# ─────────────────────────────────────────────────────────────────────────────

async def score_disruption_target(
    tool_name: str,
    niche: str,
    market: str = "global",
    d4_data: Optional[Dict[str, Any]] = None,
    agent=None,
) -> DisruptionTarget:
    """
    Score a single tool across all 7 disruption dimensions using Exa evidence
    + DeepSeek synthesis. Returns a fully populated DisruptionTarget.

    d4_data: dict from aggregate_tools_from_d4() for this tool (if present).
    Cost: ~EUR 0.003 (1-2 Exa searches + 1 DeepSeek synthesis call).
    """
    from python.helpers.cortex_exa_client import CortexExaClient
    from python.helpers.cortex_model_router import CortexModelRouter
    from python.cortex.dirty_json import DirtyJson

    exa_key = os.getenv("EXA_API_KEY", "")
    exa = CortexExaClient(api_key=exa_key)
    year_range = _current_year_range()
    now_str = _current_date().strftime("%Y-%m-%d")

    # Gather evidence for all dimensions in 2 Exa calls
    evidence_parts = []

    try:
        # Call 1: complaints + pricing + acquisition + stagnation
        r1 = await exa.search(
            f'"{tool_name}" {niche} pricing change OR acquired OR alternative '
            f'OR complaint OR problem OR slow OR "not updated" {year_range}',
            num_results=8,
            use_autoprompt=False,
        )
        evidence_parts += [f"[{r.title}] {r.content[:200]}" for r in r1]

        # Call 2: competitors + reviews + app store
        r2 = await exa.search(
            f'"{tool_name}" review cons OR missing OR rating OR competitor '
            f'site:g2.com OR site:capterra.com OR site:producthunt.com OR site:apps.apple.com',
            num_results=6,
            use_autoprompt=False,
        )
        evidence_parts += [f"[{r.title}] {r.content[:200]}" for r in r2]

    except Exception as e:
        print(f"[CORTEX disruption_scanner] Exa evidence error ({tool_name}): {e}")

    # D-4 signal summary
    d4_summary = ""
    sourced_from_d4 = bool(d4_data)
    if d4_data:
        d4_summary = (
            f"D-4 influencer signals: {d4_data.get('count', 0)} mentions, "
            f"{d4_data.get('paying_count', 0)} from paying customers, "
            f"complaint strength sum {d4_data.get('strength_sum', 0)}."
        )

    evidence_text = "\n".join(evidence_parts[:14]) if evidence_parts else "No evidence found."

    prompt = (
        f"Tool: '{tool_name}' | Niche: '{niche}' | Market: {market}\n"
        f"Assessment date: {now_str}\n"
        f"{d4_summary}\n\n"
        f"Evidence:\n{evidence_text}\n\n"
        f"Score this tool as a disruption target. JSON only:\n"
        "{\n"
        '  "complaint_volume": 0-100,\n'
        '  "pricing_vulnerability": 0-100,\n'
        '  "feature_stagnation": 0-100,\n'
        '  "stranded_segment": 0-100,\n'
        '  "competitor_emergence": 0-100,\n'
        '  "support_degradation": 0-100,\n'
        '  "rating_drift": 0-100,\n'
        '  "stranded_segment_description": "which user type is being abandoned or null",\n'
        '  "pricing_event_date": "YYYY-MM if recent pricing change found, else null",\n'
        '  "acquisition_event_date": "YYYY-MM if recently acquired, else null",\n'
        '  "timing_signal": "early" | "mid" | "crowded",\n'
        '  "key_signals": ["list up to 5 specific evidence items"],\n'
        '  "summary": "2 sentences on disruption opportunity"\n'
        "}\n\n"
        "Score conservatively. pricing_vulnerability: high if changed pricing recently "
        f"(within 6 months of {now_str}) or pricing misaligned with user segment. "
        "feature_stagnation: high if changelog/roadmap shows no new features in 12+ months. "
        "stranded_segment: high if a specific user type (SMB, vertical, etc.) is clearly underserved. "
        "competitor_emergence: high if 3+ alternatives launched recently."
    )

    # Defaults in case of failure
    dimension_scores = {k: 30.0 for k in _DIMENSION_WEIGHTS}
    stranded_desc = None
    pricing_date = None
    acquisition_date = None
    timing_signal = "mid"
    key_signals: List[str] = []
    summary = f"Disruption scoring unavailable for {tool_name}."

    try:
        raw = await CortexModelRouter.call_routed_model(
            "classification",
            "You are a competitive intelligence analyst scoring disruption readiness. JSON only.",
            prompt,
            agent,
        )
        parsed = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw

        if isinstance(parsed, dict):
            for dim in _DIMENSION_WEIGHTS:
                if dim in parsed:
                    dimension_scores[dim] = float(parsed[dim])
            stranded_desc = parsed.get("stranded_segment_description")
            pricing_date = parsed.get("pricing_event_date")
            acquisition_date = parsed.get("acquisition_event_date")
            timing_signal = parsed.get("timing_signal", "mid")
            key_signals = parsed.get("key_signals", [])
            summary = parsed.get("summary", "")

    except Exception as e:
        print(f"[CORTEX disruption_scanner] Scoring error ({tool_name}): {e}")

    # Compute composite
    composite = sum(dimension_scores[k] * _DIMENSION_WEIGHTS[k] for k in _DIMENSION_WEIGHTS)

    # Disruption window — use most recent trigger event
    trigger_date = pricing_date or acquisition_date
    event_type = "acquisition" if acquisition_date and not pricing_date else "pricing"
    window, window_date = calculate_disruption_window(trigger_date, event_type)

    # Approach + strategies
    approach, strategies, partnership_viable = determine_approach(dimension_scores)

    # Add D-4 paying-evidence signal to key_signals if available
    disruption_signals = list(key_signals)
    if d4_data and d4_data.get("paying_count", 0) > 0:
        disruption_signals.insert(0,
            f"D-4: {d4_data['paying_count']} paying-customer complaints via influencer monitoring"
        )
    if summary:
        disruption_signals.append(f"Summary: {summary}")

    return DisruptionTarget(
        tool_name=tool_name,
        niche=niche,
        disruption_score=round(composite, 1),
        disruption_signals=disruption_signals[:8],
        stranded_segment=stranded_desc,
        recommended_strategies=strategies,
        approach=approach,
        disruption_window=window,
        window_trigger_date=window_date,
        timing_signal=timing_signal,
        sourced_from_d4=sourced_from_d4,
        partnership_viable=partnership_viable,
        dimension_scores={k: round(v, 1) for k, v in dimension_scores.items()},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point -- Full Scan
# ─────────────────────────────────────────────────────────────────────────────

async def scan_disruption_targets(
    niche: str,
    market: str = "global",
    max_targets: int = 8,
    agent=None,
) -> List[DisruptionTarget]:
    """
    Full D-5 scan: combined D-4 feed + independent discovery, scored and ranked.

    Phase 1: Pull D-4 aggregated tools_mentioned (free, local files)
    Phase 2: Run independent Exa discovery (~EUR 0.002)
    Phase 3: Merge, dedup, score top max_targets (~EUR 0.003/tool)

    Returns: List[DisruptionTarget] sorted by disruption_score descending.
    Window-critical targets (open-critical) floated to top within same score tier.
    """
    print(f"[CORTEX disruption_scanner] Scanning '{niche}' | {market}")

    # Phase 1: D-4 tools
    d4_tools = aggregate_tools_from_d4(niche)
    print(f"[CORTEX disruption_scanner] D-4 feed: {len(d4_tools)} tools from stored signals")

    # Phase 2: Independent discovery
    discovered = await discover_tools_independently(niche, market, agent)
    print(f"[CORTEX disruption_scanner] Independent: {len(discovered)} tools discovered")

    # Merge and dedup (D-4 tools take priority, then discovered)
    all_tools: Dict[str, Optional[Dict]] = {}

    # D-4 tools first (already ranked by complaint score)
    for tool, data in list(d4_tools.items())[:max_targets]:
        all_tools[tool.lower()] = (tool, data)

    # Add independent discoveries not already in D-4
    for tool in discovered:
        key = tool.lower()
        if key not in all_tools:
            all_tools[key] = (tool, None)

    # Score top max_targets
    candidates = list(all_tools.values())[:max_targets]
    targets: List[DisruptionTarget] = []

    for tool_name, d4_data in candidates:
        target = await score_disruption_target(
            tool_name, niche, market, d4_data, agent
        )
        targets.append(target)
        print(
            f"[CORTEX disruption_scanner] {tool_name}: "
            f"score={target.disruption_score:.0f} | "
            f"approach={target.approach} | "
            f"window={target.disruption_window}"
        )

    # Sort: window-critical first, then by score
    def _sort_key(t: DisruptionTarget) -> Tuple[int, float]:
        window_priority = {"open-critical": 0, "open": 1, "narrowing": 2, "closed": 3, "unknown": 4}
        return (window_priority.get(t.disruption_window, 4), -t.disruption_score)

    targets.sort(key=_sort_key)

    print(
        f"[CORTEX disruption_scanner] Complete: {len(targets)} targets scored. "
        f"Top: {targets[0].tool_name} ({targets[0].disruption_score:.0f}/100)"
        if targets else "[CORTEX disruption_scanner] No targets found."
    )

    return targets


# ─────────────────────────────────────────────────────────────────────────────
# Formatting (for queue display and Gate 2 prompt injection)
# ─────────────────────────────────────────────────────────────────────────────

def format_disruption_summary(targets: List[DisruptionTarget], top_n: int = 3) -> str:
    """
    Concise summary of top disruption targets for injection into Gate 2 prompt
    and venture_discover tool output.
    """
    if not targets:
        return "No disruption targets identified."

    lines = [f"Top disruption targets for this niche:"]
    for i, t in enumerate(targets[:top_n], 1):
        window_note = f" [{t.disruption_window.upper()}]" if t.disruption_window != "unknown" else ""
        segment = f" | stranded: {t.stranded_segment}" if t.stranded_segment else ""
        lines.append(
            f"  {i}. {t.tool_name} — score {t.disruption_score:.0f}/100{window_note} | "
            f"{t.approach} | strategies: {', '.join(t.recommended_strategies)}{segment}"
        )
        if t.disruption_signals:
            lines.append(f"     Evidence: {t.disruption_signals[0]}")

    return "\n".join(lines)
