"""
cortex_stack_evaluator.py — Loop 5: evaluate research findings → risk/benefit matrix.

Takes ComponentFinding dicts from stack_researcher and applies the decision matrix:
  improvement_score × risk_score → Replace Now / Monitor / Stable

Decision quadrants:
  High improvement + Low risk  → REPLACE_NOW (flag immediately)
  High improvement + High risk → INVESTIGATE (dig deeper before deciding)
  Low improvement  + Low risk  → MONITOR (watch passively)
  Low improvement  + High risk → STABLE (don't touch it)

Outputs a structured evaluation report pushed to SurfSense cortex_optimization space.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ── Thresholds ─────────────────────────────────────────────────────────────
_IMPROVEMENT_HIGH_THRESHOLD = 0.6   # >= 0.6 → high improvement signal
_RISK_LOW_THRESHOLD = 0.4           # <= 0.4 → low risk (safe to act)


@dataclass
class ComponentEvaluation:
    component: str
    category: str
    current_version: str
    recommendation: str            # from researcher: stable|monitor|investigate|replace
    improvement_score: float       # 0.0–1.0 (benefit of switching/updating)
    risk_score: float              # 0.0–1.0 (risk of switching/updating)
    decision: str                  # REPLACE_NOW | INVESTIGATE | MONITOR | STABLE
    decision_rationale: str
    estimated_effort: str          # "hours" | "days" | "weeks"
    cost_impact: str               # "saves" | "same" | "costs_more" | "unknown"
    blocking_dependencies: list = field(default_factory=list)
    researched_at: str = ""

    def __post_init__(self):
        if not self.researched_at:
            self.researched_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "category": self.category,
            "current_version": self.current_version,
            "recommendation": self.recommendation,
            "improvement_score": round(self.improvement_score, 2),
            "risk_score": round(self.risk_score, 2),
            "decision": self.decision,
            "decision_rationale": self.decision_rationale,
            "estimated_effort": self.estimated_effort,
            "cost_impact": self.cost_impact,
            "blocking_dependencies": self.blocking_dependencies,
            "researched_at": self.researched_at,
        }


def _compute_improvement_score(finding: dict) -> float:
    """
    Score the potential improvement from updating/replacing this component.
    0.0 = no benefit, 1.0 = major benefit.
    """
    score = 0.0
    rec = finding.get("recommendation", "stable")

    # Base from researcher recommendation
    base_map = {"stable": 0.0, "monitor": 0.25, "investigate": 0.55, "replace": 0.80}
    score = base_map.get(rec, 0.0)

    # Pricing change (savings) boosts score
    if finding.get("pricing_change") and finding.get("pricing_change_description", ""):
        desc = finding["pricing_change_description"].lower()
        if any(word in desc for word in ("cheaper", "free", "discount", "lower", "reduced", "save")):
            score = min(1.0, score + 0.15)
        elif any(word in desc for word in ("increase", "expensive", "higher", "raised")):
            score = max(0.0, score - 0.10)  # price increase reduces improvement case

    # Update available adds modest benefit
    if finding.get("update_available"):
        score = min(1.0, score + 0.10)

    # Notable alternatives with clear advantage
    alts = finding.get("notable_alternatives", [])
    if len(alts) >= 2:
        score = min(1.0, score + 0.05)

    return score


def _compute_risk_score(finding: dict, component_info: Optional[dict] = None) -> float:
    """
    Score the risk of updating/replacing this component.
    0.0 = trivial change, 1.0 = system-critical high-risk change.
    """
    component_name = finding.get("component", "")
    category = finding.get("category", "")

    # Base risk by category
    category_risk = {
        "infra": 0.7,        # infra changes are highest risk
        "memory": 0.65,      # memory changes risk data loss
        "llm": 0.30,         # model swaps are usually low-risk (same API)
        "research": 0.20,    # research tools are interchangeable
        "communication": 0.50,  # Telegram change would break everything
        "voice": 0.25,       # voice is optional / graceful fallback
    }
    risk = category_risk.get(category, 0.40)

    # Special high-risk components
    high_risk_components = {
        "openrouter": 0.90,    # all LLM calls go through this
        "agent_zero": 0.95,    # the framework itself
        "faiss_local": 0.75,   # L1 memory
        "telegram": 0.85,      # primary UI
        "sqlite": 0.80,        # event store
    }
    if component_name in high_risk_components:
        risk = high_risk_components[component_name]

    # Reliability issues reduce confidence → higher risk to switch now
    reliability_signals = finding.get("reliability_signals", [])
    if reliability_signals:
        # Reliability issues on the ALTERNATIVE make switching risky
        risk = min(1.0, risk + 0.10)

    # Recommendation "replace" from researcher already implies they found a clear path
    if finding.get("recommendation") == "replace":
        risk = max(0.0, risk - 0.10)

    return risk


def _determine_decision(improvement: float, risk: float, rec: str) -> tuple[str, str]:
    """Apply the 2×2 risk/benefit matrix. Returns (decision, rationale)."""
    high_improvement = improvement >= _IMPROVEMENT_HIGH_THRESHOLD
    low_risk = risk <= _RISK_LOW_THRESHOLD

    if high_improvement and low_risk:
        return (
            "REPLACE_NOW",
            f"High improvement potential ({improvement:.0%}) with acceptable risk ({risk:.0%}). Warrants action this cycle.",
        )
    elif high_improvement and not low_risk:
        return (
            "INVESTIGATE",
            f"Strong improvement case ({improvement:.0%}) but elevated risk ({risk:.0%}). Needs deeper analysis before acting.",
        )
    elif not high_improvement and low_risk:
        return (
            "MONITOR",
            f"Modest improvement signal ({improvement:.0%}), low risk ({risk:.0%}). Watch for 1-2 more cycles.",
        )
    else:
        return (
            "STABLE",
            f"Low improvement potential ({improvement:.0%}) and/or high risk ({risk:.0%}). No action needed.",
        )


def _estimate_effort(finding: dict) -> str:
    """Rough effort estimate for acting on this finding."""
    rec = finding.get("recommendation", "stable")
    category = finding.get("category", "")

    if rec in ("stable", "monitor"):
        return "none"
    if category in ("research", "voice"):
        return "hours"
    if category in ("llm",):
        return "hours"  # model ID swap
    if category in ("memory",):
        return "days"
    return "days"


def _estimate_cost_impact(finding: dict) -> str:
    """Estimate cost impact of acting on this finding."""
    if not finding.get("pricing_change"):
        return "unknown"
    desc = finding.get("pricing_change_description", "").lower()
    if any(w in desc for w in ("cheaper", "free", "discount", "lower", "reduced", "save")):
        return "saves"
    if any(w in desc for w in ("increase", "expensive", "higher", "raised")):
        return "costs_more"
    return "same"


def _get_blocking_dependencies(component_name: str) -> list[str]:
    """Return list of components that depend on this one."""
    dependency_map = {
        "openrouter": ["claude_sonnet_46", "deepseek_v3", "gemini_flash_lite", "perplexity"],
        "agent_zero": ["all extensions", "all tools"],
        "faiss_local": ["memory layer L1", "session recall"],
        "zep_graphiti": ["memory layer L2", "entity tracking"],
        "surfsense": ["memory layer L3", "cross-device consciousness"],
    }
    return dependency_map.get(component_name, [])


def evaluate_finding(finding: dict) -> ComponentEvaluation:
    """Evaluate a single ComponentFinding and return a ComponentEvaluation."""
    improvement = _compute_improvement_score(finding)
    risk = _compute_risk_score(finding)
    decision, rationale = _determine_decision(improvement, risk, finding.get("recommendation", "stable"))
    effort = _estimate_effort(finding)
    cost = _estimate_cost_impact(finding)
    deps = _get_blocking_dependencies(finding.get("component", ""))

    return ComponentEvaluation(
        component=finding.get("component", ""),
        category=finding.get("category", ""),
        current_version=finding.get("current_version", ""),
        recommendation=finding.get("recommendation", "stable"),
        improvement_score=improvement,
        risk_score=risk,
        decision=decision,
        decision_rationale=rationale,
        estimated_effort=effort,
        cost_impact=cost,
        blocking_dependencies=deps,
        researched_at=finding.get("researched_at", datetime.now().isoformat()),
    )


def evaluate_all_findings(findings: list[dict]) -> list[ComponentEvaluation]:
    """Evaluate all findings from a Loop 5 research run."""
    return [evaluate_finding(f) for f in findings]


def build_evaluation_report(evaluations: list[ComponentEvaluation]) -> dict:
    """
    Build a structured evaluation report for inclusion in the Loop 3 operational report
    and for pushing to SurfSense cortex_optimization space.
    """
    replace_now = [e for e in evaluations if e.decision == "REPLACE_NOW"]
    investigate = [e for e in evaluations if e.decision == "INVESTIGATE"]
    monitor = [e for e in evaluations if e.decision == "MONITOR"]
    stable = [e for e in evaluations if e.decision == "STABLE"]

    return {
        "evaluated_at": datetime.now().isoformat(),
        "total_components": len(evaluations),
        "summary": {
            "replace_now": len(replace_now),
            "investigate": len(investigate),
            "monitor": len(monitor),
            "stable": len(stable),
        },
        "replace_now": [e.to_dict() for e in replace_now],
        "investigate": [e.to_dict() for e in investigate],
        "monitor": [e.to_dict() for e in monitor],
        "stable_count": len(stable),
        "highest_priority": (
            replace_now[0].to_dict() if replace_now
            else investigate[0].to_dict() if investigate
            else None
        ),
    }


def format_report_markdown(report: dict) -> str:
    """Format evaluation report as Markdown for Telegram / human report."""
    summary = report.get("summary", {})
    lines = [
        f"## Loop 5: Stack Evaluation — {report.get('evaluated_at', '')[:10]}",
        f"Components: {report['total_components']} | "
        f"Replace: {summary.get('replace_now', 0)} | "
        f"Investigate: {summary.get('investigate', 0)} | "
        f"Monitor: {summary.get('monitor', 0)} | "
        f"Stable: {summary.get('stable', 0)}",
        "",
    ]

    if report.get("replace_now"):
        lines.append("### Action Required (REPLACE NOW)")
        for e in report["replace_now"]:
            lines += [
                f"**{e['component']}** ({e['category']})",
                f"- Current: `{e['current_version']}`",
                f"- Rationale: {e['decision_rationale']}",
                f"- Effort: {e['estimated_effort']} | Cost impact: {e['cost_impact']}",
                "",
            ]

    if report.get("investigate"):
        lines.append("### Investigate")
        for e in report["investigate"]:
            lines += [
                f"**{e['component']}**: {e['decision_rationale']}",
                "",
            ]

    if not report.get("replace_now") and not report.get("investigate"):
        lines.append("*No action required this cycle. Stack is stable.*")

    return "\n".join(lines)


async def run_full_evaluation(findings: list[dict]) -> dict:
    """
    Full Loop 5 evaluation pipeline: findings → evaluations → report → SurfSense push.
    Returns the evaluation report dict.
    """
    if not findings:
        return {"total_components": 0, "summary": {}, "replace_now": [], "investigate": []}

    evaluations = evaluate_all_findings(findings)
    report = build_evaluation_report(evaluations)

    # Push to SurfSense cortex_optimization space
    try:
        from python.helpers.cortex_surfsense_push import push_to_optimization_space
        content = format_report_markdown(report)
        await push_to_optimization_space(
            title=f"Loop5 Stack Evaluation: {datetime.now().strftime('%Y-%m')}",
            content=content,
            tags=["loop5", "stack_evaluation", datetime.now().strftime("%Y-%m")],
        )
    except Exception:
        pass

    # Log to event store
    try:
        from python.helpers import cortex_event_store as es
        es.log_benchmark_run(
            suite_id="loop5_stack_evaluation",
            scores={
                "replace_now": report["summary"].get("replace_now", 0),
                "investigate": report["summary"].get("investigate", 0),
            },
            baseline_scores={},
            drift_flags=[e["component"] for e in report.get("replace_now", [])],
        )
    except Exception:
        pass

    return report
