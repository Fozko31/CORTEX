"""
cortex_struggle_aggregator.py — Loop 1 Step 1/2: Aggregate + cluster struggle events.

Reads the past week's SQLite struggle events, groups by topic cluster, ranks by
frequency × severity weight, and generates the top 3 improvement hypotheses.

A "hypothesis" is a specific, testable improvement to a prompt or knowledge file.
It is NOT a vague statement — it must name the target file and the proposed change.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

_SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}

# Topics that map to specific CORTEX knowledge/prompt targets
_TOPIC_TO_TARGET = {
    "pricing": ("agents/cortex/prompts/agent.system.main.role.md", "prompt"),
    "saas": ("agents/cortex/prompts/agent.system.main.role.md", "prompt"),
    "market": ("usr/knowledge/cortex_main/main/tools/tool_selection_rules.md", "knowledge"),
    "outreach": ("agents/cortex/prompts/agent.system.main.role.md", "prompt"),
    "marketing": ("agents/cortex/prompts/agent.system.main.role.md", "prompt"),
    "venture": ("agents/cortex/prompts/agent.system.main.role.md", "prompt"),
    "tool": ("usr/knowledge/cortex_main/main/tools/tool_selection_rules.md", "knowledge"),
    "routing": ("usr/knowledge/cortex_main/main/tools/tool_selection_rules.md", "knowledge"),
    "research": ("agents/cortex/prompts/agent.system.tool.cortex_research_tool.md", "prompt"),
    "slovenian": ("agents/cortex/prompts/agent.system.main.role.md", "prompt"),
    "language": ("agents/cortex/prompts/agent.system.main.role.md", "prompt"),
    "memory": ("agents/cortex/prompts/agent.system.main.role.md", "prompt"),
    "commitment": ("agents/cortex/prompts/agent.system.main.role.md", "prompt"),
}


@dataclass
class StruggleCluster:
    topic: str
    event_count: int
    weighted_score: float
    severity_distribution: dict  # {"high": N, "medium": N, "low": N}
    sample_contexts: list = field(default_factory=list)


@dataclass
class ImprovementHypothesis:
    rank: int
    cluster_topic: str
    weighted_score: float
    hypothesis_text: str
    target_file: str
    target_type: str  # "prompt" or "knowledge"
    proposed_change_summary: str
    experiment_id: str = ""

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "cluster_topic": self.cluster_topic,
            "weighted_score": self.weighted_score,
            "hypothesis_text": self.hypothesis_text,
            "target_file": self.target_file,
            "target_type": self.target_type,
            "proposed_change_summary": self.proposed_change_summary,
            "experiment_id": self.experiment_id,
        }


def aggregate(days: int = 7) -> list[StruggleCluster]:
    """Read struggle events and group into clusters ranked by weighted frequency."""
    from python.helpers import cortex_event_store as es
    events = es.get_struggle_events(days=days)

    if not events:
        return []

    clusters: dict[str, StruggleCluster] = {}

    for event in events:
        topic_key = _normalize_topic(event.get("topic", "general"))
        severity = event.get("severity", "medium")
        weight = _SEVERITY_WEIGHT.get(severity, 2)

        if topic_key not in clusters:
            clusters[topic_key] = StruggleCluster(
                topic=topic_key,
                event_count=0,
                weighted_score=0.0,
                severity_distribution={"high": 0, "medium": 0, "low": 0},
                sample_contexts=[],
            )

        c = clusters[topic_key]
        c.event_count += 1
        c.weighted_score += weight
        c.severity_distribution[severity] = c.severity_distribution.get(severity, 0) + 1

        ctx = event.get("context_snippet", "")
        if ctx and len(c.sample_contexts) < 3:
            c.sample_contexts.append(ctx[:150])

    return sorted(clusters.values(), key=lambda x: x.weighted_score, reverse=True)


def generate_hypotheses(clusters: list[StruggleCluster], top_n: int = 3) -> list[ImprovementHypothesis]:
    """Convert top N clusters into specific, testable improvement hypotheses."""
    import uuid
    hypotheses = []

    for i, cluster in enumerate(clusters[:top_n]):
        target_file, target_type = _resolve_target(cluster.topic)
        hypothesis_text, change_summary = _formulate_hypothesis(cluster.topic, cluster.event_count, cluster.weighted_score)

        hypotheses.append(ImprovementHypothesis(
            rank=i + 1,
            cluster_topic=cluster.topic,
            weighted_score=cluster.weighted_score,
            hypothesis_text=hypothesis_text,
            target_file=target_file,
            target_type=target_type,
            proposed_change_summary=change_summary,
            experiment_id=f"exp-{uuid.uuid4().hex[:8]}",
        ))

    return hypotheses


def run(days: int = 7, top_n: int = 3) -> list[ImprovementHypothesis]:
    """Full pipeline: aggregate → cluster → hypotheses. Returns top N."""
    clusters = aggregate(days=days)
    return generate_hypotheses(clusters, top_n=top_n)


def format_for_telegram(hypotheses: list[ImprovementHypothesis]) -> str:
    """Format hypotheses as a Telegram message for user selection."""
    if not hypotheses:
        return "No significant struggle patterns found this week. CORTEX is performing within normal range."

    lines = ["*CORTEX Weekly Self-Improvement*", ""]
    lines.append(f"Found {len(hypotheses)} improvement opportunity/ies this week:")
    lines.append("")

    for h in hypotheses:
        lines.append(f"*{h.rank}. {h.cluster_topic.replace('_', ' ').title()}*")
        lines.append(f"   {h.hypothesis_text}")
        lines.append(f"   Target: `{h.target_file.split('/')[-1]}`")
        lines.append(f"   Score: {h.weighted_score:.0f} (higher = more frequent/severe)")
        lines.append("")

    lines.append("Reply with the number(s) to test (e.g. '1' or '1,2' or 'skip').")
    return "\n".join(lines)


# ─── INTERNALS ───────────────────────────────────────────────────────────────

def _normalize_topic(raw: str) -> str:
    """Normalize raw topic to a clean cluster key."""
    cleaned = raw.lower().strip()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    words = cleaned.split()
    # Find first keyword match
    for word in words:
        for key in _TOPIC_TO_TARGET:
            if key in word or word in key:
                return key
    # Default: first 2 meaningful words
    meaningful = [w for w in words if len(w) > 3]
    return "_".join(meaningful[:2]) if meaningful else "general"


def _resolve_target(topic: str) -> tuple:
    """Map cluster topic to a target file."""
    for key, (path, typ) in _TOPIC_TO_TARGET.items():
        if key in topic:
            return path, typ
    return "agents/cortex/prompts/agent.system.main.role.md", "prompt"


def _formulate_hypothesis(topic: str, count: int, score: float) -> tuple:
    """Generate hypothesis text and proposed change summary."""
    topic_label = topic.replace("_", " ").title()

    templates = {
        "pricing": (
            f"CORTEX hedges on {topic_label} {count}x this week. "
            f"Hypothesis: adding Slovenian B2B pricing benchmarks to role.md reduces hedging.",
            "Add 2-3 specific Slovenian SaaS/service pricing ranges with source data to role.md",
        ),
        "saas": (
            f"CORTEX gives generic SaaS advice {count}x. "
            f"Hypothesis: adding small-market SaaS specifics improves precision.",
            "Add Slovenian/CEE market SaaS distribution and pricing context to role.md",
        ),
        "outreach": (
            f"CORTEX gives generic outreach advice {count}x. "
            f"Hypothesis: Slovenian B2B outreach context in role.md improves specificity.",
            "Add Slovenian B2B outreach norms and channel preferences to role.md",
        ),
        "marketing": (
            f"CORTEX hedges on marketing strategy {count}x. "
            f"Hypothesis: adding Hormozi-based marketing decision framework improves specificity.",
            "Add marketing channel selection framework with Slovenian market specifics to role.md",
        ),
        "tool": (
            f"CORTEX misroutes tool selection {count}x. "
            f"Hypothesis: clearer decision rules in tool_selection_rules.md fixes routing.",
            "Tighten tool routing rules with explicit trigger conditions and examples",
        ),
        "routing": (
            f"CORTEX misroutes {count}x. "
            f"Hypothesis: refined decision rules reduce routing errors.",
            "Add disambiguation examples to tool_selection_rules.md",
        ),
    }

    for key, (hyp, change) in templates.items():
        if key in topic:
            return hyp, change

    return (
        f"CORTEX struggles with '{topic_label}' {count}x (score: {score:.0f}). "
        f"Hypothesis: adding focused context for this topic improves output quality.",
        f"Add {topic_label} specific guidance to role.md with concrete examples",
    )
