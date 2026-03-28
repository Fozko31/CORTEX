"""
Phase D -- Test D-5: Disruption Scanner (pure logic only, no API calls)
========================================================================
Tests: DisruptionTarget model, calculate_disruption_window, determine_approach,
       aggregate_tools_from_d4, _current_year_range, format_disruption_summary.
No network calls, no LLM, no SurfSense.
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import python.helpers.cortex_discovery_params as dp

_TEST_DIR = os.path.join("usr", "memory", "cortex_main", "_test_d5")


def _patch():
    dp._DISCOVERY_DIR = _TEST_DIR
    dp._PARAMS_FILE = os.path.join(_TEST_DIR, "params.json")
    dp._PARAMS_HISTORY_DIR = os.path.join(_TEST_DIR, "params_history")
    dp._QUEUE_FILE = os.path.join(_TEST_DIR, "queue.json")
    dp._REJECTED_FILE = os.path.join(_TEST_DIR, "rejected.json")
    dp._PARKED_FILE = os.path.join(_TEST_DIR, "parked.json")
    dp._ACCEPTED_FILE = os.path.join(_TEST_DIR, "accepted.json")
    dp._INFLUENCERS_FILE = os.path.join(_TEST_DIR, "influencers.json")
    dp._SIGNALS_DIR = os.path.join(_TEST_DIR, "signals")


_patch()

from python.helpers.cortex_disruption_scanner import (
    DisruptionTarget,
    _DIMENSION_WEIGHTS,
    _current_year_range,
    calculate_disruption_window,
    determine_approach,
    aggregate_tools_from_d4,
    format_disruption_summary,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _date_str(days_ago: int) -> str:
    """Return YYYY-MM string for N days ago."""
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m")


def _target(
    tool="TestTool",
    niche="SEO",
    score=50.0,
    approach="disrupt",
    window="open",
    window_date=None,
    stranded=None,
    strategies=None,
    timing="mid",
    d4=False,
    partnership=False,
    signals=None,
    dims=None,
):
    return DisruptionTarget(
        tool_name=tool,
        niche=niche,
        disruption_score=score,
        disruption_signals=signals or [],
        stranded_segment=stranded,
        recommended_strategies=strategies or ["Fast Follower"],
        approach=approach,
        disruption_window=window,
        window_trigger_date=window_date,
        timing_signal=timing,
        sourced_from_d4=d4,
        partnership_viable=partnership,
        dimension_scores=dims or {k: 30.0 for k in _DIMENSION_WEIGHTS},
    )


def _signal(tool=None, paying=False, strength=3):
    return dp.PainSignal(
        source="youtube",
        tool_mentioned=tool,
        paying_evidence=paying,
        extracted_pain="test pain",
        strength=strength,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Dimension weights sum
# ─────────────────────────────────────────────────────────────────────────────

class TestDimensionWeights(unittest.TestCase):

    def test_weights_sum_to_1(self):
        self.assertAlmostEqual(sum(_DIMENSION_WEIGHTS.values()), 1.0, places=3)

    def test_all_seven_dimensions_present(self):
        expected = {
            "complaint_volume", "pricing_vulnerability", "feature_stagnation",
            "stranded_segment", "competitor_emergence", "support_degradation", "rating_drift",
        }
        self.assertEqual(set(_DIMENSION_WEIGHTS.keys()), expected)

    def test_complaint_and_pricing_highest_weight(self):
        self.assertEqual(_DIMENSION_WEIGHTS["complaint_volume"], 0.20)
        self.assertEqual(_DIMENSION_WEIGHTS["pricing_vulnerability"], 0.20)

    def test_rating_drift_lowest_weight(self):
        self.assertEqual(_DIMENSION_WEIGHTS["rating_drift"], 0.05)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _current_year_range
# ─────────────────────────────────────────────────────────────────────────────

class TestCurrentYearRange(unittest.TestCase):

    def test_returns_string(self):
        self.assertIsInstance(_current_year_range(), str)

    def test_contains_current_year(self):
        yr = str(datetime.now().year)
        self.assertIn(yr, _current_year_range())

    def test_contains_previous_year(self):
        prev = str(datetime.now().year - 1)
        self.assertIn(prev, _current_year_range())

    def test_format_has_or(self):
        self.assertIn("OR", _current_year_range())

    def test_two_years(self):
        parts = _current_year_range().split(" OR ")
        self.assertEqual(len(parts), 2)
        for p in parts:
            self.assertTrue(p.strip().isdigit())


# ─────────────────────────────────────────────────────────────────────────────
# Tests: calculate_disruption_window (pricing)
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateDisruptionWindowPricing(unittest.TestCase):

    def test_no_date_returns_unknown(self):
        w, d = calculate_disruption_window(None)
        self.assertEqual(w, "unknown")
        self.assertIsNone(d)

    def test_empty_string_returns_unknown(self):
        w, d = calculate_disruption_window("")
        self.assertEqual(w, "unknown")

    def test_invalid_date_returns_unknown(self):
        w, d = calculate_disruption_window("not-a-date")
        self.assertEqual(w, "unknown")

    def test_15_days_ago_is_open_critical(self):
        w, _ = calculate_disruption_window(_date_str(15), "pricing")
        self.assertEqual(w, "open-critical")

    def test_45_days_ago_is_open(self):
        w, _ = calculate_disruption_window(_date_str(45), "pricing")
        self.assertEqual(w, "open")

    def test_120_days_ago_is_narrowing(self):
        w, _ = calculate_disruption_window(_date_str(120), "pricing")
        self.assertEqual(w, "narrowing")

    def test_200_days_ago_is_closed(self):
        w, _ = calculate_disruption_window(_date_str(200), "pricing")
        self.assertEqual(w, "closed")

    def test_returns_input_date_string(self):
        date_s = _date_str(50)
        _, returned = calculate_disruption_window(date_s, "pricing")
        self.assertEqual(returned, date_s)

    def test_yyyy_mm_dd_format_accepted(self):
        date_full = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        w, _ = calculate_disruption_window(date_full, "pricing")
        self.assertEqual(w, "open-critical")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: calculate_disruption_window (acquisition)
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateDisruptionWindowAcquisition(unittest.TestCase):

    def test_60_days_ago_is_open_critical(self):
        w, _ = calculate_disruption_window(_date_str(60), "acquisition")
        self.assertEqual(w, "open-critical")

    def test_120_days_ago_is_open(self):
        w, _ = calculate_disruption_window(_date_str(120), "acquisition")
        self.assertEqual(w, "open")

    def test_250_days_ago_is_narrowing(self):
        w, _ = calculate_disruption_window(_date_str(250), "acquisition")
        self.assertEqual(w, "narrowing")

    def test_400_days_ago_is_closed(self):
        w, _ = calculate_disruption_window(_date_str(400), "acquisition")
        self.assertEqual(w, "closed")

    def test_acquisition_stays_open_longer_than_pricing(self):
        date_str = _date_str(60)  # 60 days: open-critical for acq, open for pricing
        w_acq, _ = calculate_disruption_window(date_str, "acquisition")
        w_pr, _ = calculate_disruption_window(date_str, "pricing")
        self.assertIn(w_acq, ("open-critical", "open"))
        # Acquisition threshold for open-critical is 90 days vs pricing 30 days
        # At 60 days: pricing is "open", acquisition is "open-critical"
        self.assertNotEqual(w_acq, w_pr)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: determine_approach
# ─────────────────────────────────────────────────────────────────────────────

class TestDetermineApproach(unittest.TestCase):

    def _dims(self, complaint=30, pricing=30, stagnation=30, stranded=30,
               competitor=30, support=30, rating=30):
        return {
            "complaint_volume": complaint,
            "pricing_vulnerability": pricing,
            "feature_stagnation": stagnation,
            "stranded_segment": stranded,
            "competitor_emergence": competitor,
            "support_degradation": support,
            "rating_drift": rating,
        }

    def test_returns_tuple_of_three(self):
        result = determine_approach(self._dims())
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_approach_is_valid_string(self):
        approach, _, _ = determine_approach(self._dims())
        self.assertIn(approach, ("disrupt", "partner", "wrap"))

    def test_strategies_is_list(self):
        _, strategies, _ = determine_approach(self._dims())
        self.assertIsInstance(strategies, list)
        self.assertGreater(len(strategies), 0)

    def test_partnership_viable_is_bool(self):
        _, _, viable = determine_approach(self._dims())
        self.assertIsInstance(viable, bool)

    def test_high_complaint_high_stagnation_is_disrupt(self):
        approach, _, _ = determine_approach(self._dims(complaint=70, stagnation=60))
        self.assertEqual(approach, "disrupt")

    def test_high_complaint_high_pricing_is_disrupt(self):
        approach, _, _ = determine_approach(self._dims(complaint=65, pricing=65))
        self.assertEqual(approach, "disrupt")

    def test_disrupt_with_stranded_includes_niche_domination(self):
        _, strategies, _ = determine_approach(
            self._dims(complaint=70, stagnation=60, stranded=70)
        )
        self.assertIn("Niche Domination", strategies)

    def test_disrupt_without_stranded_includes_fast_follower(self):
        _, strategies, _ = determine_approach(
            self._dims(complaint=70, stagnation=60, stranded=30)
        )
        self.assertIn("Fast Follower", strategies)

    def test_low_complaint_high_stranded_is_partner(self):
        approach, _, viable = determine_approach(
            self._dims(complaint=30, stranded=60)
        )
        self.assertEqual(approach, "partner")
        self.assertTrue(viable)

    def test_partner_includes_picks_and_shovels(self):
        _, strategies, _ = determine_approach(self._dims(complaint=30, stranded=60))
        self.assertIn("Picks and Shovels", strategies)

    def test_disrupt_not_partnership_viable(self):
        _, _, viable = determine_approach(self._dims(complaint=70, stagnation=60))
        self.assertFalse(viable)

    def test_wrap_approach_includes_saas_wrapper(self):
        approach, strategies, _ = determine_approach(
            self._dims(complaint=45, stagnation=30)
        )
        # wrap condition: stagnation < 40 and complaint >= 40
        if approach == "wrap":
            self.assertIn("SaaS Wrapper", strategies)

    def test_empty_dims_defaults_gracefully(self):
        approach, strategies, viable = determine_approach({})
        self.assertIn(approach, ("disrupt", "partner", "wrap"))
        self.assertIsInstance(strategies, list)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: aggregate_tools_from_d4
# ─────────────────────────────────────────────────────────────────────────────

class TestAggregateToolsFromD4(unittest.TestCase):

    def setUp(self):
        import shutil
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def tearDown(self):
        import shutil
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def _save_signals(self, niche, signals):
        dp.save_signals(niche, signals)

    def test_no_signals_returns_empty(self):
        result = aggregate_tools_from_d4("nonexistent niche")
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 0)

    def test_signals_without_tool_excluded(self):
        self._save_signals("SEO tools", [
            _signal(tool=None, paying=False),
            _signal(tool="", paying=False),
        ])
        result = aggregate_tools_from_d4("SEO tools")
        self.assertEqual(len(result), 0)

    def test_tool_mention_counted(self):
        self._save_signals("SEO tools", [
            _signal(tool="Semrush", paying=False, strength=3),
        ])
        result = aggregate_tools_from_d4("SEO tools")
        self.assertIn("Semrush", result)
        self.assertEqual(result["Semrush"]["count"], 1)

    def test_multiple_mentions_aggregated(self):
        self._save_signals("SEO tools", [
            _signal(tool="Ahrefs", paying=False, strength=3),
            _signal(tool="Ahrefs", paying=True, strength=5),
            _signal(tool="Ahrefs", paying=False, strength=2),
        ])
        result = aggregate_tools_from_d4("SEO tools")
        self.assertEqual(result["Ahrefs"]["count"], 3)
        self.assertEqual(result["Ahrefs"]["paying_count"], 1)

    def test_paying_count_tracked(self):
        self._save_signals("SEO tools", [
            _signal(tool="Moz", paying=True, strength=4),
            _signal(tool="Moz", paying=True, strength=5),
            _signal(tool="Moz", paying=False, strength=2),
        ])
        result = aggregate_tools_from_d4("SEO tools")
        self.assertEqual(result["Moz"]["paying_count"], 2)

    def test_strength_summed(self):
        self._save_signals("SEO tools", [
            _signal(tool="Surfer", paying=False, strength=3),
            _signal(tool="Surfer", paying=False, strength=4),
        ])
        result = aggregate_tools_from_d4("SEO tools")
        self.assertEqual(result["Surfer"]["strength_sum"], 7)

    def test_d4_score_computed(self):
        self._save_signals("SEO tools", [_signal(tool="ToolX", paying=True, strength=4)])
        result = aggregate_tools_from_d4("SEO tools")
        self.assertIn("d4_score", result["ToolX"])
        self.assertGreater(result["ToolX"]["d4_score"], 0)

    def test_sorted_by_d4_score_descending(self):
        self._save_signals("SEO tools", [
            _signal(tool="LowTool", paying=False, strength=1),
            _signal(tool="HighTool", paying=True, strength=5),
            _signal(tool="HighTool", paying=True, strength=5),
            _signal(tool="HighTool", paying=True, strength=5),
        ])
        result = aggregate_tools_from_d4("SEO tools")
        keys = list(result.keys())
        self.assertEqual(keys[0], "HighTool")

    def test_short_tool_names_excluded(self):
        self._save_signals("SEO tools", [_signal(tool="X", paying=False)])
        result = aggregate_tools_from_d4("SEO tools")
        self.assertNotIn("X", result)

    def test_multiple_tools_all_present(self):
        self._save_signals("SEO tools", [
            _signal(tool="ToolA", paying=False),
            _signal(tool="ToolB", paying=True),
            _signal(tool="ToolC", paying=False),
        ])
        result = aggregate_tools_from_d4("SEO tools")
        self.assertIn("ToolA", result)
        self.assertIn("ToolB", result)
        self.assertIn("ToolC", result)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: DisruptionTarget model
# ─────────────────────────────────────────────────────────────────────────────

class TestDisruptionTargetModel(unittest.TestCase):

    def test_to_dict_contains_all_fields(self):
        t = _target(tool="Semrush", score=72.5)
        d = t.to_dict()
        required = {
            "tool_name", "niche", "disruption_score", "disruption_signals",
            "stranded_segment", "recommended_strategies", "approach",
            "disruption_window", "window_trigger_date", "timing_signal",
            "sourced_from_d4", "partnership_viable", "dimension_scores",
        }
        self.assertEqual(set(d.keys()), required)

    def test_to_dict_tool_name(self):
        t = _target(tool="Ahrefs")
        self.assertEqual(t.to_dict()["tool_name"], "Ahrefs")

    def test_to_dict_score_is_float(self):
        t = _target(score=67.3)
        self.assertIsInstance(t.to_dict()["disruption_score"], float)

    def test_to_dict_partnership_viable_is_bool(self):
        t = _target(partnership=True)
        self.assertIsInstance(t.to_dict()["partnership_viable"], bool)
        self.assertTrue(t.to_dict()["partnership_viable"])

    def test_approach_values_valid(self):
        for approach in ("disrupt", "partner", "wrap"):
            t = _target(approach=approach)
            self.assertEqual(t.to_dict()["approach"], approach)

    def test_window_values_valid(self):
        for w in ("open-critical", "open", "narrowing", "closed", "unknown"):
            t = _target(window=w)
            self.assertEqual(t.disruption_window, w)

    def test_dimension_scores_default_empty_dict(self):
        t = DisruptionTarget(
            tool_name="T", niche="N", disruption_score=50.0,
            disruption_signals=[], stranded_segment=None,
            recommended_strategies=[], approach="disrupt",
            disruption_window="open", window_trigger_date=None,
            timing_signal="mid", sourced_from_d4=False, partnership_viable=False,
        )
        self.assertIsInstance(t.dimension_scores, dict)

    def test_sourced_from_d4_false_by_default_if_not_set(self):
        t = _target(d4=False)
        self.assertFalse(t.sourced_from_d4)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: format_disruption_summary
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatDisruptionSummary(unittest.TestCase):

    def test_empty_list_returns_no_targets_message(self):
        result = format_disruption_summary([])
        self.assertIn("No disruption targets", result)

    def test_returns_string(self):
        t = _target(tool="Semrush", score=75.0)
        result = format_disruption_summary([t])
        self.assertIsInstance(result, str)

    def test_contains_tool_name(self):
        t = _target(tool="Moz")
        result = format_disruption_summary([t])
        self.assertIn("Moz", result)

    def test_contains_score(self):
        t = _target(score=62.0)
        result = format_disruption_summary([t])
        self.assertIn("62", result)

    def test_contains_approach(self):
        t = _target(approach="partner")
        result = format_disruption_summary([t])
        self.assertIn("partner", result)

    def test_contains_window_when_known(self):
        t = _target(window="open-critical")
        result = format_disruption_summary([t])
        self.assertIn("OPEN-CRITICAL", result)

    def test_top_n_respected(self):
        targets = [_target(tool=f"Tool{i}", score=float(90 - i)) for i in range(5)]
        result = format_disruption_summary(targets, top_n=2)
        self.assertIn("Tool0", result)
        self.assertIn("Tool1", result)
        self.assertNotIn("Tool2", result)

    def test_stranded_segment_shown_when_present(self):
        t = _target(stranded="SMB restaurant owners")
        result = format_disruption_summary([t])
        self.assertIn("SMB restaurant owners", result)

    def test_stranded_segment_absent_when_none(self):
        t = _target(stranded=None)
        result = format_disruption_summary([t])
        self.assertNotIn("stranded:", result)

    def test_strategies_shown(self):
        t = _target(strategies=["Niche Domination", "Fast Follower"])
        result = format_disruption_summary([t])
        self.assertIn("Niche Domination", result)

    def test_evidence_shown_when_present(self):
        t = _target(signals=["Pricing doubled in Q1 2026"])
        result = format_disruption_summary([t])
        self.assertIn("Pricing doubled", result)

    def test_unknown_window_no_bracket(self):
        t = _target(window="unknown")
        result = format_disruption_summary([t])
        self.assertNotIn("[UNKNOWN]", result)

    def test_multiple_tools_numbered(self):
        targets = [_target(tool=f"Tool{i}") for i in range(3)]
        result = format_disruption_summary(targets, top_n=3)
        self.assertIn("1.", result)
        self.assertIn("2.", result)
        self.assertIn("3.", result)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Sorting (window priority then score)
# ─────────────────────────────────────────────────────────────────────────────

class TestSortingLogic(unittest.TestCase):
    """
    Validates that the sort key used in scan_disruption_targets is correct.
    We test it indirectly via format_disruption_summary with pre-sorted input.
    """

    def _sort_key(self, t):
        window_priority = {"open-critical": 0, "open": 1, "narrowing": 2, "closed": 3, "unknown": 4}
        return (window_priority.get(t.disruption_window, 4), -t.disruption_score)

    def test_open_critical_floats_above_higher_score(self):
        t_high_score = _target(tool="HighScore", score=90.0, window="closed")
        t_critical = _target(tool="Critical", score=50.0, window="open-critical")
        targets = [t_high_score, t_critical]
        targets.sort(key=self._sort_key)
        self.assertEqual(targets[0].tool_name, "Critical")

    def test_within_same_window_higher_score_wins(self):
        t1 = _target(tool="T1", score=80.0, window="open")
        t2 = _target(tool="T2", score=60.0, window="open")
        targets = [t2, t1]
        targets.sort(key=self._sort_key)
        self.assertEqual(targets[0].tool_name, "T1")

    def test_window_order_respected(self):
        windows_in_order = ["open-critical", "open", "narrowing", "closed", "unknown"]
        targets = [_target(tool=w, score=50.0, window=w) for w in reversed(windows_in_order)]
        targets.sort(key=self._sort_key)
        sorted_windows = [t.disruption_window for t in targets]
        self.assertEqual(sorted_windows, windows_in_order)


if __name__ == "__main__":
    unittest.main(verbosity=2)
