"""
cortex_outcome_attributor.py — Loop 2: classifies venture outcomes by attribution axis.

Before any outcome feeds back into CORTEX optimization, it must be classified:
  - cortex_owned: CORTEX's recommendation quality caused this outcome
  - user_owned:   User execution caused this outcome (did/didn't follow through)
  - external:     Market conditions, seasonality, competitor action caused this
  - mixed:        Combination of the above

The autonomy_score from VentureDNA is used as signal quality multiplier:
  - High autonomy (CORTEX runs it fully): weight 1.0 — clean signal
  - Low autonomy (moving company with humans): weight 0.3 — noisy signal
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class OutcomeRecord:
    venture_id: str
    venture_name: str
    period: str               # "2026-Q1" or "2026-03"
    metric_type: str          # "revenue", "lead_count", "conversion_rate", "user_satisfaction", etc.
    target_value: float
    actual_value: float
    cortex_controlled_slice: str   # what CORTEX specifically owned (e.g. "marketing strategy")
    user_execution_confirmed: Optional[bool]  # None = unknown, True/False = confirmed
    external_confounders: list = field(default_factory=list)  # ["seasonal_peak", "competitor_entry"]
    autonomy_score: float = 0.5  # from VentureDNA
    attribution: str = ""         # filled by classify()
    signal_weight: float = 0.0    # filled by classify()
    optimization_delta: float = 0.0  # actual - target (normalized, filled by classify())
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "venture_id": self.venture_id,
            "venture_name": self.venture_name,
            "period": self.period,
            "metric_type": self.metric_type,
            "target_value": self.target_value,
            "actual_value": self.actual_value,
            "cortex_controlled_slice": self.cortex_controlled_slice,
            "user_execution_confirmed": self.user_execution_confirmed,
            "external_confounders": self.external_confounders,
            "autonomy_score": self.autonomy_score,
            "attribution": self.attribution,
            "signal_weight": self.signal_weight,
            "optimization_delta": self.optimization_delta,
            "timestamp": self.timestamp,
        }


def classify(record: OutcomeRecord) -> OutcomeRecord:
    """
    Classify attribution and compute signal weight for an outcome record.
    Modifies record in-place and returns it.
    """
    delta_pct = _compute_delta_pct(record.target_value, record.actual_value)
    record.optimization_delta = round(delta_pct, 3)

    # Attribution logic
    has_external = len(record.external_confounders) > 0
    execution_unknown = record.user_execution_confirmed is None
    execution_failed = record.user_execution_confirmed is False

    if execution_failed and not has_external:
        record.attribution = "user_owned"
        record.signal_weight = 0.0  # user didn't execute — CORTEX gets no signal
    elif has_external and not execution_failed:
        confounder_strength = len(record.external_confounders) * 0.2
        if confounder_strength >= 0.5:
            record.attribution = "external"
            record.signal_weight = max(0.1, record.autonomy_score * 0.3)
        else:
            record.attribution = "mixed"
            record.signal_weight = record.autonomy_score * 0.5
    elif has_external and (execution_failed or execution_unknown):
        record.attribution = "mixed"
        record.signal_weight = record.autonomy_score * 0.2
    elif execution_unknown:
        record.attribution = "mixed"
        record.signal_weight = record.autonomy_score * 0.5
    else:
        # Execution confirmed, no external confounders — cleanest signal
        record.attribution = "cortex_owned"
        record.signal_weight = record.autonomy_score

    record.signal_weight = round(record.signal_weight, 3)
    return record


def classify_batch(records: list) -> list:
    return [classify(r) for r in records]


def _compute_delta_pct(target: float, actual: float) -> float:
    if target == 0:
        return 0.0
    return (actual - target) / abs(target)


def signal_qualifies(record: OutcomeRecord, min_weight: float = 0.2) -> bool:
    """Returns True if this outcome should feed into Loop 2 optimization."""
    return record.signal_weight >= min_weight and record.attribution != "user_owned"


def format_attribution_summary(records: list) -> str:
    """Human-readable summary of outcome attributions."""
    if not records:
        return "No outcome records for this period."

    by_attribution: dict = {}
    for r in records:
        key = r.attribution or "unclassified"
        by_attribution.setdefault(key, []).append(r)

    lines = ["**Outcome Attribution Summary**", ""]
    for attr, recs in by_attribution.items():
        avg_delta = sum(r.optimization_delta for r in recs) / len(recs)
        avg_weight = sum(r.signal_weight for r in recs) / len(recs)
        lines.append(
            f"- {attr}: {len(recs)} outcomes | avg delta: {avg_delta:+.1%} | avg signal weight: {avg_weight:.2f}"
        )

    qualified = [r for r in records if signal_qualifies(r)]
    lines.append(f"\nQualified for optimization: {len(qualified)}/{len(records)} records")
    return "\n".join(lines)
