"""
cortex_operational_reporter.py — Generates the 10-category operational report for Loop 3.

This report is the CORTEX side of the CORTEX+Ruflo inter-agent exchange.
It reads from SQLite event store + self_model + personality model.
Output is a structured dict (machine-readable for Loop 3 protocol) and
an optional human-readable Markdown summary.

10 categories:
1. Struggle clusters
2. Tool usage patterns
3. Latency hotspots
4. User correction patterns
5. Confidence calibration
6. Cross-venture friction
7. Extension failures
8. Success patterns
9. Routing accuracy
10. Stack evolution findings (from Loop 5, if available)
"""

import json
import os
from datetime import datetime
from typing import Optional


def generate(period_days: int = 60, stack_findings: Optional[list] = None) -> dict:
    """
    Generate the full operational report.
    period_days: how far back to look in event store (bi-monthly = 60 days)
    stack_findings: Loop 5 results if available (else None)
    Returns: structured dict (machine-readable, JSON-serializable)
    """
    from python.helpers import cortex_event_store as es
    from python.helpers.cortex_struggle_aggregator import aggregate as struggle_aggregate

    # 1. Struggle clusters
    clusters = struggle_aggregate(days=period_days)
    struggle_clusters = [
        {
            "topic": c.topic,
            "event_count": c.event_count,
            "weighted_score": round(c.weighted_score, 1),
            "severity_distribution": c.severity_distribution,
            "sample_contexts": c.sample_contexts[:2],
        }
        for c in clusters[:6]
    ]

    # 2. Tool usage
    tool_summary = es.get_tool_usage_summary(days=period_days)
    by_tool = tool_summary.get("by_tool", {})
    zero_call_tools = _detect_zero_call_tools(by_tool)
    high_error_tools = [t for t, d in by_tool.items() if d.get("success_rate", 1.0) < 0.85]

    tool_usage = {
        "calls_by_tool": {t: d["calls"] for t, d in by_tool.items()},
        "zero_call_tools": zero_call_tools,
        "high_error_rate_tools": high_error_tools,
        "total_sessions": tool_summary.get("total_sessions", 0),
    }

    # 3. Latency hotspots
    latency = es.get_latency_summary(days=period_days)
    hotspots = [
        {"task_type": r["task_type"], "avg_turns": r["avg_turns"], "max_turns": r["max_turns"], "occurrences": r["occurrences"]}
        for r in latency[:5]
        if r.get("avg_turns", 0) > 2
    ]

    # 4. User corrections
    corrections = es.get_correction_summary(days=period_days)
    correction_summary = [
        {"correction_type": r["correction_type"], "count": r["count"]}
        for r in corrections[:6]
    ]

    # 5. Confidence calibration (derived from struggle vs. total session data)
    struggle_events = es.get_struggle_events(days=period_days)
    hedge_rate = _compute_hedge_rate(struggle_events, tool_summary.get("total_sessions", 1))

    calibration = {
        "hedge_rate": hedge_rate,
        "high_confidence_accuracy": None,  # requires outcome data (Loop 2)
        "note": "Accuracy tracking begins once Loop 2 outcome data accumulates.",
    }

    # 6. Cross-venture friction (heuristic — topics with cross-venture signals)
    cross_venture = _detect_cross_venture_friction(struggle_events)

    # 7. Extension failures
    failures = es.get_extension_failures(days=period_days)
    ext_failures = [
        {"extension": r["extension_name"], "count": r["count"], "last_type": r.get("last_type", "")}
        for r in failures[:8]
    ]

    # 8. Success patterns (low latency + low correction rate tasks)
    success_patterns = _detect_success_patterns(latency, corrections)

    # 9. Routing accuracy (heuristic from tool usage vs. expected tool patterns)
    routing_accuracy = _assess_routing_accuracy(by_tool)

    # 10. Stack evolution findings
    stack_section = None
    if stack_findings:
        stack_section = {
            "components_researched": len(stack_findings),
            "recommendations": stack_findings,
        }

    report = {
        "generated_at": datetime.now().isoformat(),
        "period_days": period_days,
        "struggle_clusters": struggle_clusters,
        "tool_usage": tool_usage,
        "latency_hotspots": hotspots,
        "user_corrections": correction_summary,
        "confidence_calibration": calibration,
        "cross_venture_friction": cross_venture,
        "extension_failures": ext_failures,
        "success_patterns": success_patterns,
        "routing_accuracy": routing_accuracy,
        "stack_evolution_findings": stack_section,
        "open_questions_for_ruflo": _generate_open_questions(
            struggle_clusters, zero_call_tools, high_error_tools, hotspots
        ),
    }

    return report


def to_markdown(report: dict) -> str:
    """Human-readable Markdown summary of the operational report."""
    lines = [
        f"# CORTEX Operational Report",
        f"Period: {report.get('period_days', 60)} days | Generated: {report.get('generated_at', '')[:10]}",
        "",
    ]

    # Struggles
    clusters = report.get("struggle_clusters", [])
    if clusters:
        lines += ["## Top Struggle Areas", ""]
        for c in clusters[:4]:
            lines.append(f"- **{c['topic'].replace('_', ' ').title()}**: {c['event_count']} events (score: {c['weighted_score']})")
        lines.append("")

    # Tools
    tool_data = report.get("tool_usage", {})
    zero_tools = tool_data.get("zero_call_tools", [])
    if zero_tools:
        lines += [f"## Unused Tools (0 calls)", ", ".join(zero_tools), ""]

    # Latency
    hotspots = report.get("latency_hotspots", [])
    if hotspots:
        lines += ["## Latency Hotspots", ""]
        for h in hotspots[:3]:
            lines.append(f"- {h['task_type']}: avg {h['avg_turns']} turns")
        lines.append("")

    # Corrections
    corrections = report.get("user_corrections", [])
    if corrections:
        lines += ["## User Corrections", ""]
        for c in corrections[:4]:
            lines.append(f"- {c['correction_type'].replace('_', ' ')}: {c['count']}x")
        lines.append("")

    # Extension failures
    failures = report.get("extension_failures", [])
    if failures:
        lines += ["## Extension Failures", ""]
        for f in failures[:4]:
            lines.append(f"- {f['extension']}: {f['count']} failures")
        lines.append("")

    # Open questions
    questions = report.get("open_questions_for_ruflo", [])
    if questions:
        lines += ["## Open Questions for Architectural Review", ""]
        for q in questions:
            lines.append(f"- {q}")
        lines.append("")

    return "\n".join(lines)


# ─── INTERNALS ───────────────────────────────────────────────────────────────

def _detect_zero_call_tools(by_tool: dict) -> list:
    known_tools = [
        "cortex_research_tool", "venture_create", "venture_manage", "self_improve",
        "venture_ops", "venture_playbook_create", "telegram_ops", "memory_save",
        "memory_load", "knowledge_save", "knowledge_load", "code_execution",
    ]
    return [t for t in known_tools if t not in by_tool]


def _compute_hedge_rate(struggle_events: list, total_sessions: int) -> float:
    high_hedging = sum(1 for e in struggle_events if "high_hedging" in str(e.get("signals", [])))
    if total_sessions < 1:
        return 0.0
    return round(high_hedging / max(1, total_sessions), 3)


def _detect_cross_venture_friction(struggle_events: list) -> list:
    venture_keywords = ["venture", "startup", "business", "project"]
    cross_signals = []
    for e in struggle_events:
        ctx = e.get("context_snippet", "").lower()
        count = sum(1 for kw in venture_keywords if kw in ctx)
        if count >= 2:
            cross_signals.append({"topic": e.get("topic", ""), "context": ctx[:100]})
    return cross_signals[:4]


def _detect_success_patterns(latency: list, corrections: list) -> list:
    fast_tasks = {r["task_type"] for r in latency if r.get("avg_turns", 99) <= 2}
    corrected_tasks = {r.get("correction_type", "") for r in corrections}
    return [
        {"task_type": t, "note": "low latency, not in correction list — performing well"}
        for t in fast_tasks
        if t not in corrected_tasks
    ][:4]


def _assess_routing_accuracy(by_tool: dict) -> dict:
    research_calls = by_tool.get("cortex_research_tool", {}).get("calls", 0)
    search_calls = by_tool.get("search_engine", {}).get("calls", 0)
    total = research_calls + search_calls
    research_rate = round(research_calls / total, 3) if total > 0 else None
    return {
        "research_tool_preference_rate": research_rate,
        "note": "research_tool should dominate over search_engine — rate near 1.0 is correct",
        "common_misroutes": [],
    }


def _generate_open_questions(clusters, zero_tools, high_error_tools, hotspots) -> list:
    questions = []
    if clusters:
        top = clusters[0]["topic"]
        questions.append(f"Is the '{top}' struggle cluster caused by a prompt gap, a knowledge gap, or an architectural constraint?")
    if zero_tools:
        questions.append(f"Zero-call tools: {', '.join(zero_tools[:3])} — are these dead, not triggered, or not connected?")
    if high_error_tools:
        questions.append(f"High error rate tools: {', '.join(high_error_tools)} — is this a tool bug or a usage pattern issue?")
    if hotspots:
        top_latency = hotspots[0]["task_type"]
        questions.append(f"'{top_latency}' is the highest latency task — is this an architectural bottleneck or expected complexity?")
    return questions
