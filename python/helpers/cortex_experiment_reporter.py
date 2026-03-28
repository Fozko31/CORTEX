"""
cortex_experiment_reporter.py — Builds the user-facing experiment report.

Report principles (from Phase G design):
  - Objective: judge scores, not CORTEX's opinion of its own improvement
  - Specific: "improved 14/20 test cases" not "seems better"
  - Visual: before/after comparison on 3-5 representative cases
  - Honest about negatives: degraded categories shown
  - No recommendation to approve: CORTEX presents, user decides
"""

from python.helpers.cortex_experiment_runner import ExperimentResult


def build_report(result: ExperimentResult) -> str:
    """Build a complete Markdown experiment report."""
    h = result.hypothesis
    lines = [
        f"# Experiment Report: {result.experiment_id}",
        f"**Hypothesis:** {h.get('hypothesis_text', 'N/A')}",
        f"**Target:** `{h.get('target_file', 'N/A').split('/')[-1]}`",
        "",
        "---",
        "",
        "## Results",
        "",
        f"| Metric | Score |",
        f"|--------|-------|",
        f"| Baseline average | {result.baseline_avg:.1f}/100 |",
        f"| Experimental average | {result.experimental_avg:.1f}/100 |",
        f"| Overall delta | {_delta_str(result.overall_delta)} |",
        f"| Queries run | {result.queries_run} |",
        f"| Improved | {result.improved_count}/{result.queries_run} test cases |",
        f"| Degraded | {result.degraded_count}/{result.queries_run} test cases |",
        f"| Neutral | {result.neutral_count}/{result.queries_run} test cases |",
        "",
    ]

    # Error short-circuit
    if result.error:
        lines += [f"**Error:** {result.error}", ""]
        return "\n".join(lines)

    # Category breakdown
    if result.query_results:
        lines += ["## Score by Test Case", ""]
        lines += ["| ID | Category | Baseline | Experimental | Delta |"]
        lines += ["|-----|----------|----------|--------------|-------|"]
        for qr in sorted(result.query_results, key=lambda x: x.delta, reverse=True):
            cat = _get_category(qr.query_id)
            lines.append(
                f"| {qr.query_id} | {cat} | {qr.baseline_score:.0f} | {qr.experimental_score:.0f} | {_delta_str(qr.delta)} |"
            )
        lines.append("")

    # Before/after comparison (top 3 most changed)
    changed = sorted(result.query_results, key=lambda x: abs(x.delta), reverse=True)[:3]
    if changed:
        lines += ["## Sample Comparisons (most changed)", ""]
        for qr in changed:
            lines += [
                f"### {qr.query_id}: {qr.query_text[:80]}{'...' if len(qr.query_text) > 80 else ''}",
                f"**Baseline ({qr.baseline_score:.0f}/100):** {_truncate(qr.baseline_response, 300)}",
                "",
                f"**Experimental ({qr.experimental_score:.0f}/100):** {_truncate(qr.experimental_response, 300)}",
                "",
            ]

    # Verdict framing (no recommendation — present only)
    lines += [
        "---",
        "",
        "## Decision",
        "",
        f"Overall change: **{_delta_str(result.overall_delta)}** ({result.baseline_avg:.1f} → {result.experimental_avg:.1f})",
        f"Improved {result.improved_count}, degraded {result.degraded_count}, neutral {result.neutral_count} test cases.",
        "",
        "**Apply this experiment?**",
        "- Reply `apply {experiment_id}` to apply to live files + git commit",
        "- Reply `reject {experiment_id}` to discard",
        "",
        f"Checkpoint tag: `{result.checkpoint_tag}` (rollback available if needed)",
    ]

    return "\n".join(lines)


def build_telegram_summary(result: ExperimentResult) -> str:
    """Shorter version for Telegram delivery (4000 char limit)."""
    h = result.hypothesis
    delta_emoji = "+" if result.overall_delta > 0 else ("-" if result.overall_delta < 0 else "=")

    lines = [
        f"*Experiment {result.experiment_id}*",
        f"Topic: {h.get('cluster_topic', 'N/A').replace('_', ' ').title()}",
        "",
        f"Baseline: {result.baseline_avg:.1f}/100",
        f"Experimental: {result.experimental_avg:.1f}/100",
        f"Delta: {delta_emoji}{abs(result.overall_delta):.1f} pts",
        "",
        f"Improved: {result.improved_count}/{result.queries_run} queries",
        f"Degraded: {result.degraded_count}/{result.queries_run} queries",
        "",
    ]

    if result.error:
        lines.append(f"Error: {result.error}")
    else:
        lines += [
            "Reply:",
            f"`apply {result.experiment_id}` to apply",
            f"`reject {result.experiment_id}` to discard",
        ]

    return "\n".join(lines)


def _delta_str(delta: float) -> str:
    if delta > 0:
        return f"+{delta:.1f}"
    elif delta < 0:
        return f"{delta:.1f}"
    return "0.0"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _get_category(query_id: str) -> str:
    prefix_map = {"V": "venture", "R": "research", "S": "strategy", "C": "challenge", "L": "language"}
    return prefix_map.get(query_id[0], "other") if query_id else "other"
