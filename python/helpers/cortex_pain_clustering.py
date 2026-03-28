"""
CORTEX Pain Clustering — Phase D, D-3
=======================================

Takes raw PainSignal list from D-2 and:
  1. Clusters signals by semantic theme (DeepSeek, ~€0.001/20 signals)
  2. Computes aggregate strength per cluster
  3. Stores cluster summary as Graphiti episode for temporal tracking
     (Zep extracts entities/relationships asynchronously — niche → pain → market)

Temporal value: running D-3 over multiple weeks lets CORTEX detect which pain
themes are intensifying vs. fading. A cluster with growing signal count over
time = higher confidence in the opportunity.

Fallback: if DeepSeek unavailable, keyword-based clustering (free, rougher).
If Graphiti not configured, skips temporal storage (non-blocking).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from python.helpers.cortex_discovery_params import PainSignal


# ─────────────────────────────────────────────────────────────────────────────
# Data Model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PainCluster:
    theme: str                          # e.g. "Difficulty ranking on Google Maps"
    signals: List[PainSignal]           # all signals assigned to this theme
    strength: int                       # sum of signal.strength values
    paying_count: int                   # signals with paying_evidence=True
    representative_pain: str            # best 1-sentence distillation
    sources: List[str]                  # unique source names

    @property
    def signal_count(self) -> int:
        return len(self.signals)

    @property
    def paying_ratio(self) -> float:
        return self.paying_count / max(self.signal_count, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme": self.theme,
            "signal_count": self.signal_count,
            "strength": self.strength,
            "paying_count": self.paying_count,
            "paying_ratio": round(self.paying_ratio, 2),
            "representative_pain": self.representative_pain,
            "sources": self.sources,
        }


# ─────────────────────────────────────────────────────────────────────────────
# LLM-Based Clustering (primary)
# ─────────────────────────────────────────────────────────────────────────────

async def _cluster_via_llm(
    signals: List[PainSignal],
    niche: str,
    agent=None,
) -> Dict[str, List[int]]:
    """
    Ask DeepSeek to assign each signal to a theme cluster.
    Returns {theme_label: [signal_indices]}.
    Cost: ~€0.001 per batch of 20.
    """
    from python.helpers.cortex_model_router import CortexModelRouter
    from python.cortex.dirty_json import DirtyJson

    BATCH = 20
    theme_map: Dict[str, List[int]] = {}   # theme → list of original indices
    offset = 0

    for i in range(0, len(signals), BATCH):
        batch = signals[i:i + BATCH]
        numbered = "\n".join(
            f"{j + 1}. [{s.source}] {s.extracted_pain[:150]}"
            for j, s in enumerate(batch)
        )

        prompt = (
            f"Niche: '{niche}'\n\n"
            f"Pain signals:\n{numbered}\n\n"
            "Group these signals into 2-6 distinct pain themes. "
            "Each theme should be a short noun phrase (5-8 words max).\n"
            "For each signal, return its theme. JSON only:\n"
            "{\n"
            '  "themes": ["Theme A", "Theme B", ...],\n'
            '  "assignments": [1, 2, 1, 3, ...]  // theme index (1-based) for each signal\n'
            "}"
        )

        try:
            raw = await CortexModelRouter.call_routed_model(
                "classification",
                "You are a pain signal analyst. Cluster signals into themes. JSON only.",
                prompt,
                agent,
            )
            parsed = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw
            themes = parsed.get("themes", [])
            assignments = parsed.get("assignments", [])

            for j, theme_idx in enumerate(assignments):
                if j >= len(batch):
                    break
                idx = int(theme_idx) - 1
                theme = themes[idx] if 0 <= idx < len(themes) else "Uncategorized"
                theme_map.setdefault(theme, []).append(offset + j)

        except Exception as e:
            print(f"[CORTEX pain_clustering] LLM clustering error (batch {i}): {e}")
            # Fall through — will be handled by keyword fallback on re-merge

        offset += len(batch)

    return theme_map


# ─────────────────────────────────────────────────────────────────────────────
# Keyword Fallback Clustering
# ─────────────────────────────────────────────────────────────────────────────

_THEME_KEYWORDS = [
    ("Pricing & Cost Complaints",   ["expensive", "overpriced", "cost", "pricing", "price", "fee", "invoice", "charge"]),
    ("Missing Features",            ["missing", "wish", "feature", "doesn't have", "cannot", "no way to", "lacks"]),
    ("Poor Support & Service",      ["support", "slow", "response", "help", "customer service", "abandoned", "broken"]),
    ("Switching Intent",            ["alternative", "switch", "replace", "moving to", "leaving", "competitor"]),
    ("Reliability & Bugs",          ["bug", "crash", "broken", "unreliable", "glitch", "error", "down", "outage"]),
    ("Onboarding & Complexity",     ["complicated", "hard to use", "confusing", "steep", "learning curve", "setup"]),
]


def _cluster_via_keywords(signals: List[PainSignal]) -> Dict[str, List[int]]:
    """Fast keyword-based fallback clustering. No API cost."""
    theme_map: Dict[str, List[int]] = {}

    for i, s in enumerate(signals):
        text = (s.extracted_pain + " " + s.raw_text).lower()
        assigned = False
        for theme, kws in _THEME_KEYWORDS:
            if any(kw in text for kw in kws):
                theme_map.setdefault(theme, []).append(i)
                assigned = True
                break
        if not assigned:
            theme_map.setdefault("General Pain", []).append(i)

    return theme_map


# ─────────────────────────────────────────────────────────────────────────────
# Best Representative Pain Selector
# ─────────────────────────────────────────────────────────────────────────────

def _pick_representative(cluster_signals: List[PainSignal]) -> str:
    """
    Pick the best representative pain statement from a cluster.
    Prefers: paying_evidence=True, higher strength, longer text.
    """
    ranked = sorted(
        cluster_signals,
        key=lambda s: (s.paying_evidence, s.strength, len(s.extracted_pain)),
        reverse=True,
    )
    return ranked[0].extracted_pain if ranked else ""


# ─────────────────────────────────────────────────────────────────────────────
# Main Clustering Entry Point
# ─────────────────────────────────────────────────────────────────────────────

async def cluster_signals(
    signals: List[PainSignal],
    niche: str,
    agent=None,
    use_llm: bool = True,
) -> List[PainCluster]:
    """
    Cluster pain signals by theme. Returns sorted List[PainCluster]
    (strongest/most-paying clusters first).

    use_llm=True: DeepSeek clustering (better quality, ~€0.001/20 signals)
    use_llm=False: keyword fallback (free, rough)
    """
    if not signals:
        return []

    if use_llm:
        theme_map = await _cluster_via_llm(signals, niche, agent)
        # Any signals not assigned (LLM batch error) → keyword fallback
        assigned = {idx for indices in theme_map.values() for idx in indices}
        unassigned = [i for i in range(len(signals)) if i not in assigned]
        if unassigned:
            fallback = _cluster_via_keywords([signals[i] for i in unassigned])
            for theme, local_indices in fallback.items():
                global_indices = [unassigned[j] for j in local_indices]
                theme_map.setdefault(theme, []).extend(global_indices)
    else:
        theme_map = _cluster_via_keywords(signals)

    clusters: List[PainCluster] = []
    for theme, indices in theme_map.items():
        cluster_sigs = [signals[i] for i in indices]
        paying = sum(1 for s in cluster_sigs if s.paying_evidence)
        strength = sum(s.strength for s in cluster_sigs)
        sources = list({s.source for s in cluster_sigs})

        clusters.append(PainCluster(
            theme=theme,
            signals=cluster_sigs,
            strength=strength,
            paying_count=paying,
            representative_pain=_pick_representative(cluster_sigs),
            sources=sources,
        ))

    # Sort: paying_count desc, then strength desc
    clusters.sort(key=lambda c: (c.paying_count, c.strength), reverse=True)
    return clusters


# ─────────────────────────────────────────────────────────────────────────────
# Graphiti Temporal Storage
# ─────────────────────────────────────────────────────────────────────────────

async def store_clusters_to_graphiti(
    clusters: List[PainCluster],
    niche: str,
    market: str = "global",
    agent=None,
) -> bool:
    """
    Persist cluster summary as a Graphiti episode.
    Zep extracts entities/relationships asynchronously (~30-60s).
    Temporal value: call this each run — Zep's graph accumulates over time,
    letting CORTEX detect which pain themes are intensifying.

    Returns True if stored, False if Graphiti not configured/failed.
    """
    try:
        import os
        from python.helpers.cortex_graphiti_client import CortexGraphitiClient

        api_key = (
            getattr(getattr(agent, "config", None), "cortex_graphiti_api_key", "")
            or os.getenv("ZEP_API_KEY", "")
            or os.getenv("GRAPHITI_API_KEY", "")
        )
        if not api_key:
            return False

        client = CortexGraphitiClient(api_key=api_key)

        # Build episode text — Zep extracts entities from natural-language text
        lines = [
            f"Pain signal analysis for niche: '{niche}' in market: {market}.",
            f"Total clusters identified: {len(clusters)}.",
            "",
        ]
        for c in clusters[:8]:  # cap at 8 clusters per episode
            paying_note = f" ({c.paying_count} with paying evidence)" if c.paying_count else ""
            lines.append(
                f"Pain theme '{c.theme}': {c.signal_count} signals{paying_note}. "
                f"Sources: {', '.join(c.sources)}. "
                f"Representative: {c.representative_pain[:200]}"
            )

        episode_text = "\n".join(lines)
        await client.add_episode(
            text=episode_text,
            source=f"pain_clustering:{niche}",
        )
        return True

    except Exception as e:
        print(f"[CORTEX pain_clustering] Graphiti store error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: Cluster + Store in One Call
# ─────────────────────────────────────────────────────────────────────────────

async def cluster_and_store(
    signals: List[PainSignal],
    niche: str,
    market: str = "global",
    agent=None,
    use_llm: bool = True,
) -> List[PainCluster]:
    """
    Main D-3 entry point. Clusters signals and persists to Graphiti.
    Returns List[PainCluster] sorted by strength (strongest first).
    Non-blocking: Graphiti failure does not affect clustering result.
    """
    clusters = await cluster_signals(signals, niche, agent=agent, use_llm=use_llm)

    if clusters:
        stored = await store_clusters_to_graphiti(clusters, niche, market, agent)
        if stored:
            print(
                f"[CORTEX pain_clustering] {niche}: {len(clusters)} clusters stored to Graphiti"
            )
        else:
            print(
                f"[CORTEX pain_clustering] {niche}: {len(clusters)} clusters (Graphiti not configured)"
            )

    return clusters


# ─────────────────────────────────────────────────────────────────────────────
# Pain Summary Builder (used by Gate 2 and D-7 scorer)
# ─────────────────────────────────────────────────────────────────────────────

def build_pain_summary(clusters: List[PainCluster], max_chars: int = 400) -> str:
    """
    Build a concise pain summary string from clusters for Gate 2 / D-7 prompts.
    Format: "Theme A (N signals, X paying): representative pain | Theme B ..."
    """
    parts = []
    for c in clusters[:5]:
        paying = f", {c.paying_count} paying" if c.paying_count else ""
        parts.append(
            f"{c.theme} ({c.signal_count} signals{paying}): {c.representative_pain[:100]}"
        )
    summary = " | ".join(parts)
    return summary[:max_chars]
