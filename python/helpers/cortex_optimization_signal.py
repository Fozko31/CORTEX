"""
cortex_optimization_signal.py — Loop 2: converts classified outcomes into optimization signals.

An optimization signal is a structured update to CORTEX's knowledge or priors.
Signals are accumulated and pushed to SurfSense cortex_optimization space periodically.

Signal types:
  - prior_update: CORTEX's confidence estimate for a claim was wrong → update prior
  - knowledge_gap: CORTEX made a recommendation that failed → flag knowledge gap
  - success_pattern: CORTEX made a recommendation that worked → reinforce pattern
  - calibration_note: CORTEX's confidence level was miscalibrated → recalibrate
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from python.helpers.cortex_outcome_attributor import OutcomeRecord


@dataclass
class OptimizationSignal:
    signal_type: str          # "prior_update" | "knowledge_gap" | "success_pattern" | "calibration_note"
    venture_id: str
    metric_type: str
    signal_strength: float    # 0.0 - 1.0 (= signal_weight from attribution)
    description: str
    recommended_action: str   # what Loop 1 or Loop 3 should consider
    evidence: dict            # raw numbers supporting the signal
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "signal_type": self.signal_type,
            "venture_id": self.venture_id,
            "metric_type": self.metric_type,
            "signal_strength": round(self.signal_strength, 3),
            "description": self.description,
            "recommended_action": self.recommended_action,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }


def generate_signal(record: OutcomeRecord) -> Optional[OptimizationSignal]:
    """
    Convert a classified outcome record into an optimization signal.
    Returns None if the record doesn't qualify (too noisy or user-owned).
    """
    from python.helpers.cortex_outcome_attributor import signal_qualifies

    if not signal_qualifies(record):
        return None

    delta = record.optimization_delta
    strength = record.signal_weight
    evidence = {
        "target": record.target_value,
        "actual": record.actual_value,
        "delta_pct": round(delta * 100, 1),
        "attribution": record.attribution,
        "autonomy_score": record.autonomy_score,
        "confounders": record.external_confounders,
    }

    # Strong failure (>30% below target) — knowledge gap
    if delta < -0.30:
        return OptimizationSignal(
            signal_type="knowledge_gap",
            venture_id=record.venture_id,
            metric_type=record.metric_type,
            signal_strength=strength,
            description=(
                f"Recommendation for '{record.cortex_controlled_slice}' in {record.venture_name} "
                f"missed target by {abs(delta)*100:.0f}% ({record.actual_value:.1f} vs target {record.target_value:.1f}). "
                f"Attribution: {record.attribution}."
            ),
            recommended_action=(
                f"Investigate CORTEX's {record.cortex_controlled_slice} advice quality. "
                f"Add this domain to Loop 1 experiment targets if struggle events confirm."
            ),
            evidence=evidence,
        )

    # Strong success (>20% above target) — success pattern
    elif delta > 0.20:
        return OptimizationSignal(
            signal_type="success_pattern",
            venture_id=record.venture_id,
            metric_type=record.metric_type,
            signal_strength=strength,
            description=(
                f"'{record.cortex_controlled_slice}' recommendation exceeded target by {delta*100:.0f}% "
                f"in {record.venture_name}. Pattern worth reinforcing."
            ),
            recommended_action=(
                f"Preserve this approach in {record.cortex_controlled_slice} advice. "
                f"Consider adding to knowledge base as a worked example."
            ),
            evidence=evidence,
        )

    # Moderate miss with high confidence — calibration note
    elif -0.30 <= delta <= -0.10:
        return OptimizationSignal(
            signal_type="calibration_note",
            venture_id=record.venture_id,
            metric_type=record.metric_type,
            signal_strength=strength * 0.6,  # softer signal
            description=(
                f"Moderate miss on {record.metric_type} for {record.venture_name}: "
                f"{delta*100:+.0f}% vs target. CORTEX may be slightly overconfident in this domain."
            ),
            recommended_action="Monitor. If pattern repeats across 3+ ventures, flag for Loop 3 architectural review.",
            evidence=evidence,
        )

    return None


def generate_signals_batch(records: list) -> list:
    """Generate signals for a batch of outcome records."""
    signals = []
    for r in records:
        sig = generate_signal(r)
        if sig:
            signals.append(sig)
    return signals


async def push_signals_to_surfsense(signals: list) -> bool:
    """Push optimization signals to SurfSense cortex_optimization space."""
    if not signals:
        return True
    from python.helpers.cortex_surfsense_push import push_to_optimization_space
    ok = True
    for sig in signals:
        content = (
            f"Optimization Signal: {sig.signal_type}\n"
            f"Venture: {sig.venture_id} | Metric: {sig.metric_type}\n"
            f"Strength: {sig.signal_strength:.2f}\n\n"
            f"{sig.description}\n\n"
            f"Recommended Action: {sig.recommended_action}\n\n"
            f"Evidence: {json.dumps(sig.evidence)}"
        )
        title = f"OptSignal: {sig.signal_type} | {sig.venture_id} | {sig.timestamp[:10]}"
        result = await push_to_optimization_space(
            title=title,
            content=content,
            tags=["loop2", "outcome", sig.signal_type, sig.venture_id],
        )
        ok = ok and result
    return ok


async def run_monthly_signal_processing(agent=None) -> dict:
    """
    Monthly Loop 2 run: gather recent outcome records from event store, generate
    optimization signals, push to SurfSense cortex_optimization space, notify via Telegram.
    Called from scheduler on 20th of each month at 3am CET.
    """
    from python.helpers import cortex_event_store as es
    from python.helpers.cortex_outcome_attributor import OutcomeRecord, classify

    # 1. Pull recent experiment outcomes used as outcome proxies (last 35 days)
    #    Real venture outcomes come through ingest_outcome() — this processes
    #    any that were stored in event store since last run.
    experiment_history = es.get_experiment_history(days=35)
    signals_generated = []
    skipped = 0

    for exp in experiment_history:
        # Only process applied experiments (confirmed CORTEX actions with outcomes)
        if not exp.get("applied"):
            skipped += 1
            continue
        try:
            # Build a minimal OutcomeRecord from experiment data
            baseline = exp.get("baseline_score", 0.0)
            experimental = exp.get("experimental_score", 0.0)
            if baseline <= 0:
                skipped += 1
                continue
            delta_pct = (experimental - baseline) / baseline if baseline else 0.0

            record = OutcomeRecord(
                venture_id="cortex_self",
                venture_name="CORTEX Self-Improvement",
                period=exp.get("timestamp", "")[:7],
                metric_type="benchmark_score",
                target_value=baseline,
                actual_value=experimental,
                cortex_controlled_slice="prompt_optimization",
                user_execution_confirmed=True,
                external_confounders=[],
                autonomy_score=1.0,  # fully CORTEX-controlled
            )
            classified = classify(record)
            sig = generate_signal(classified)
            if sig:
                signals_generated.append(sig)
        except Exception:
            skipped += 1

    # 2. Push generated signals
    pushed = False
    if signals_generated:
        pushed = await push_signals_to_surfsense(signals_generated)

    # 3. Build and push monthly summary to SurfSense
    from python.helpers.cortex_surfsense_push import push_to_optimization_space
    summary_content = (
        f"## Loop 2 Monthly Signal Processing — {datetime.now().strftime('%Y-%m')}\n\n"
        f"Experiments reviewed: {len(experiment_history)}\n"
        f"Signals generated: {len(signals_generated)}\n"
        f"Skipped (no data): {skipped}\n\n"
        + (
            "\n".join(
                f"- [{s.signal_type}] {s.venture_id}: {s.description[:100]}"
                for s in signals_generated
            )
            if signals_generated else "No actionable signals this cycle."
        )
    )
    await push_to_optimization_space(
        title=f"Loop2 Monthly: {datetime.now().strftime('%Y-%m')}",
        content=summary_content,
        tags=["loop2", "monthly_summary", datetime.now().strftime("%Y-%m")],
    )

    # 4. Notify via Telegram
    try:
        from python.helpers.cortex_telegram_bot import TelegramBotHandler
        bot = TelegramBotHandler()
        msg = (
            f"*Loop 2 Monthly Signal Processing*\n"
            f"Signals: {len(signals_generated)} | Skipped: {skipped}\n"
        )
        if signals_generated:
            msg += "\n".join(f"- {s.signal_type}: {s.description[:60]}" for s in signals_generated[:3])
        await bot.send_text(msg)
    except Exception:
        pass

    return {
        "processed": len(experiment_history),
        "signals_generated": len(signals_generated),
        "skipped": skipped,
        "pushed_to_surfsense": pushed,
        "message": f"Loop 2 complete: {len(signals_generated)} signals from {len(experiment_history)} records.",
    }
