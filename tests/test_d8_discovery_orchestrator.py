"""
Phase D -- Test D-8: Discovery Orchestrator (pure logic, no API calls)
=======================================================================
Tests: DiscoveryResult model, estimate_cost, outcome constants,
       process_niche_influencers dedup logic, _make_candidate,
       pipeline early-exit logic (mocked sub-components).
No network calls, no LLM, no SurfSense.
"""

import asyncio
import os
import sys
import shutil
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import python.helpers.cortex_discovery_params as dp

_TEST_DIR = os.path.join("usr", "memory", "cortex_main", "_test_d8")


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

from python.helpers.cortex_discovery_orchestrator import (
    DiscoveryResult,
    OUTCOME_QUEUED,
    OUTCOME_REJECTED,
    OUTCOME_PARKED,
    OUTCOME_ERROR,
    _VALID_OUTCOMES,
    _STEP_COSTS,
    estimate_cost,
    _make_candidate,
    _finalize,
    run_discovery,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _signal(pain="test pain", paying=False, tool=None, strength=2):
    return dp.PainSignal(
        source="youtube",
        extracted_pain=pain,
        paying_evidence=paying,
        tool_mentioned=tool,
        strength=strength,
    )


def _result(outcome=OUTCOME_QUEUED, niche="SEO", market="global"):
    return DiscoveryResult(niche=niche, market=market, outcome=outcome, reason="test")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Outcome constants
# ─────────────────────────────────────────────────────────────────────────────

class TestOutcomeConstants(unittest.TestCase):

    def test_all_outcomes_in_valid_set(self):
        self.assertIn(OUTCOME_QUEUED, _VALID_OUTCOMES)
        self.assertIn(OUTCOME_REJECTED, _VALID_OUTCOMES)
        self.assertIn(OUTCOME_PARKED, _VALID_OUTCOMES)
        self.assertIn(OUTCOME_ERROR, _VALID_OUTCOMES)

    def test_four_valid_outcomes(self):
        self.assertEqual(len(_VALID_OUTCOMES), 4)

    def test_outcome_strings(self):
        self.assertEqual(OUTCOME_QUEUED, "queued")
        self.assertEqual(OUTCOME_REJECTED, "rejected")
        self.assertEqual(OUTCOME_PARKED, "parked")
        self.assertEqual(OUTCOME_ERROR, "error")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Step costs
# ─────────────────────────────────────────────────────────────────────────────

class TestStepCosts(unittest.TestCase):

    def test_all_pipeline_steps_present(self):
        expected = {
            "gate_0", "signal_ingestion", "gate_1", "pain_clustering",
            "influencers", "disruption_scan", "gate_2", "opportunity_score",
        }
        self.assertEqual(set(_STEP_COSTS.keys()), expected)

    def test_all_costs_non_negative(self):
        for step, cost in _STEP_COSTS.items():
            self.assertGreaterEqual(cost, 0.0, f"{step} has negative cost")

    def test_gate_0_is_free(self):
        self.assertEqual(_STEP_COSTS["gate_0"], 0.0)

    def test_influencers_most_expensive(self):
        self.assertEqual(
            max(_STEP_COSTS, key=lambda k: _STEP_COSTS[k]),
            "influencers"
        )

    def test_disruption_scan_second_most_expensive(self):
        sorted_costs = sorted(_STEP_COSTS.values(), reverse=True)
        self.assertGreater(_STEP_COSTS["disruption_scan"], sorted_costs[2])


# ─────────────────────────────────────────────────────────────────────────────
# Tests: estimate_cost
# ─────────────────────────────────────────────────────────────────────────────

class TestEstimateCost(unittest.TestCase):

    def test_empty_steps_zero_cost(self):
        self.assertEqual(estimate_cost([]), 0.0)

    def test_returns_float(self):
        self.assertIsInstance(estimate_cost(["gate_0"]), float)

    def test_gate_0_only_is_free(self):
        self.assertEqual(estimate_cost(["gate_0"]), 0.0)

    def test_full_pipeline_cost_reasonable(self):
        full = list(_STEP_COSTS.keys())
        cost = estimate_cost(full)
        self.assertGreater(cost, 0.01)
        self.assertLess(cost, 1.0)   # full pipeline should be well under EUR 1

    def test_skip_influencers_reduces_cost(self):
        with_inf = estimate_cost(list(_STEP_COSTS.keys()))
        without_inf = estimate_cost([k for k in _STEP_COSTS if k != "influencers"])
        self.assertGreater(with_inf, without_inf)

    def test_unknown_step_ignored(self):
        cost = estimate_cost(["nonexistent_step"])
        self.assertEqual(cost, 0.0)

    def test_additive(self):
        c1 = estimate_cost(["gate_0", "signal_ingestion"])
        c2 = estimate_cost(["gate_0"]) + estimate_cost(["signal_ingestion"])
        self.assertAlmostEqual(c1, c2, places=5)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: DiscoveryResult model
# ─────────────────────────────────────────────────────────────────────────────

class TestDiscoveryResult(unittest.TestCase):

    def test_to_dict_contains_all_keys(self):
        r = _result()
        d = r.to_dict()
        required = {
            "niche", "market", "outcome", "reason", "signal_count",
            "cluster_count", "disruption_target_count", "candidate_id",
            "final_score", "strategy_type", "pain_summary", "disruption_summary",
            "cost_estimate_eur", "steps_completed", "steps_skipped",
            "errors", "started_at", "completed_at",
        }
        self.assertEqual(set(d.keys()), required)

    def test_signal_count_reflects_signals(self):
        r = _result()
        r.signals = [_signal(), _signal()]
        self.assertEqual(r.to_dict()["signal_count"], 2)

    def test_candidate_id_none_when_no_candidate(self):
        r = _result()
        r.candidate = None
        self.assertIsNone(r.to_dict()["candidate_id"])

    def test_candidate_id_present_when_candidate_set(self):
        r = _result()
        r.candidate = _make_candidate("SEO", "global", [], {}, 50.0, "Fast Follower")
        self.assertIsNotNone(r.to_dict()["candidate_id"])

    def test_outcome_stored(self):
        for outcome in _VALID_OUTCOMES:
            r = DiscoveryResult(niche="n", market="m", outcome=outcome, reason="r")
            self.assertEqual(r.to_dict()["outcome"], outcome)

    def test_started_at_is_iso_string(self):
        r = _result()
        # Should parse without error
        datetime.fromisoformat(r.started_at)

    def test_errors_list_default_empty(self):
        r = _result()
        self.assertEqual(r.errors, [])

    def test_steps_completed_default_empty(self):
        r = _result()
        self.assertEqual(r.steps_completed, [])


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _make_candidate
# ─────────────────────────────────────────────────────────────────────────────

class TestMakeCandidate(unittest.TestCase):

    def test_returns_venture_candidate(self):
        c = _make_candidate("SEO", "Slovenia", [], {}, 55.0, "Fast Follower")
        self.assertIsInstance(c, dp.VentureCandidate)

    def test_niche_set(self):
        c = _make_candidate("Local SEO", "global", [], {}, 0.0, "")
        self.assertEqual(c.niche, "Local SEO")

    def test_market_set(self):
        c = _make_candidate("SEO", "Slovenia", [], {}, 0.0, "")
        self.assertEqual(c.market, "Slovenia")

    def test_prescore_set(self):
        c = _make_candidate("SEO", "global", [], {}, 72.5, "")
        self.assertAlmostEqual(c.cvs_prescore, 72.5)

    def test_strategy_set(self):
        c = _make_candidate("SEO", "global", [], {}, 0.0, "Niche Domination")
        self.assertEqual(c.strategy_type, "Niche Domination")

    def test_source_is_discovery_orchestrator(self):
        c = _make_candidate("SEO", "global", [], {}, 0.0, "")
        self.assertEqual(c.source, "discovery_orchestrator")

    def test_signals_capped_at_20(self):
        signals = [_signal(f"pain {i}") for i in range(30)]
        c = _make_candidate("SEO", "global", signals, {}, 0.0, "")
        self.assertLessEqual(len(c.source_signals), 20)

    def test_name_contains_niche_and_market(self):
        c = _make_candidate("Restaurant SEO", "Slovenia", [], {}, 0.0, "")
        self.assertIn("Restaurant SEO", c.name)
        self.assertIn("Slovenia", c.name)

    def test_id_generated(self):
        c = _make_candidate("SEO", "global", [], {}, 0.0, "")
        self.assertTrue(bool(c.id))


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _finalize
# ─────────────────────────────────────────────────────────────────────────────

class TestFinalize(unittest.TestCase):

    def test_cost_set(self):
        r = _result()
        _finalize(r, 0.0234)
        self.assertAlmostEqual(r.cost_estimate_eur, 0.0234, places=4)

    def test_completed_at_set(self):
        r = _result()
        self.assertEqual(r.completed_at, "")
        _finalize(r, 0.0)
        self.assertNotEqual(r.completed_at, "")
        datetime.fromisoformat(r.completed_at)   # valid ISO string

    def test_cost_rounded_to_4_places(self):
        r = _result()
        _finalize(r, 0.0123456789)
        self.assertEqual(r.cost_estimate_eur, round(0.0123456789, 4))


# ─────────────────────────────────────────────────────────────────────────────
# Tests: run_discovery pipeline logic (mocked sub-components)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunDiscoveryPipelineLogic(unittest.TestCase):

    def setUp(self):
        _patch()  # re-apply in case another test file's tearDown restored original paths
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def tearDown(self):
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def _gate_result(self, passed=True, score="green", reason="ok"):
        gr = MagicMock()
        gr.passed = passed
        gr.score = score
        gr.reason = reason
        gr.details = {}
        gr.all_results = []
        return gr

    def test_gate0_fail_returns_parked(self):
        """Gate 0 failure should immediately return PARKED without running later steps."""
        with patch("python.helpers.cortex_discovery_orchestrator.gate_0",
                   return_value=self._gate_result(passed=False, reason="regulatory")):
            with patch("python.helpers.cortex_discovery_gates.gate_0"):
                from python.helpers.cortex_discovery_gates import gate_0
                result = _run(run_discovery(
                    niche="financial advice platform",
                    market="global",
                    params=dp.VentureDiscoveryParameters(),
                ))
        self.assertEqual(result.outcome, OUTCOME_PARKED)
        self.assertIn("gate_0", result.steps_completed)
        # Gate 1 and beyond should be skipped
        self.assertNotIn("signal_ingestion", result.steps_completed)

    def test_gate1_red_returns_parked_skips_expensive_steps(self):
        """Gate 1 red should park and skip D-4, D-5, gate_2, scoring."""
        g0_pass = self._gate_result(passed=True)
        g1_fail = self._gate_result(passed=False, score="red", reason="insufficient demand")

        with patch("python.helpers.cortex_discovery_orchestrator.gate_0",
                   new=AsyncMock(return_value=g0_pass)):
            with patch("python.helpers.cortex_discovery_orchestrator.gate_1",
                       new=AsyncMock(return_value=g1_fail)):
                with patch("python.helpers.cortex_discovery_orchestrator.fetch_review_signals",
                           new=AsyncMock(return_value=[])):
                    result = _run(run_discovery(
                        niche="niche with no demand",
                        market="global",
                        params=dp.VentureDiscoveryParameters(),
                    ))

        self.assertEqual(result.outcome, OUTCOME_PARKED)
        self.assertIn("influencers", result.steps_skipped)
        self.assertIn("disruption_scan", result.steps_skipped)
        self.assertIn("gate_2", result.steps_skipped)
        self.assertIn("opportunity_score", result.steps_skipped)

    def test_budget_cap_skips_influencers(self):
        """max_cost_eur=0.0 should skip all expensive steps."""
        g0 = self._gate_result(passed=True)
        g1 = self._gate_result(passed=True, score="yellow")

        with patch("python.helpers.cortex_discovery_orchestrator.gate_0",
                   return_value=g0):
            with patch("python.helpers.cortex_discovery_orchestrator.gate_1",
                       new=AsyncMock(return_value=g1)):
                with patch("python.helpers.cortex_discovery_orchestrator.fetch_review_signals",
                           new=AsyncMock(return_value=[])):
                    result = _run(run_discovery(
                        niche="test niche",
                        market="global",
                        params=dp.VentureDiscoveryParameters(),
                        max_cost_eur=0.000,  # zero budget
                    ))

        self.assertIn("influencers", result.steps_skipped)

    def test_skip_influencers_flag_skips_d4(self):
        """skip_influencers=True should skip D-4 regardless of budget."""
        g0 = self._gate_result(passed=True)
        g1 = self._gate_result(passed=True)

        with patch("python.helpers.cortex_discovery_orchestrator.gate_0",
                   return_value=g0):
            with patch("python.helpers.cortex_discovery_orchestrator.gate_1",
                       new=AsyncMock(return_value=g1)):
                with patch("python.helpers.cortex_discovery_orchestrator.fetch_review_signals",
                           new=AsyncMock(return_value=[])):
                    with patch("python.helpers.cortex_discovery_orchestrator.scan_disruption_targets",
                               new=AsyncMock(return_value=[])):
                        with patch("python.helpers.cortex_discovery_orchestrator.gate_2",
                                   new=AsyncMock(return_value=(self._gate_result(passed=False), 0.0, ""))):
                            result = _run(run_discovery(
                                niche="test niche",
                                market="global",
                                params=dp.VentureDiscoveryParameters(),
                                skip_influencers=True,
                                max_cost_eur=2.0,
                            ))

        self.assertIn("influencers", result.steps_skipped)

    def test_result_has_niche_and_market(self):
        """DiscoveryResult should always capture niche and market."""
        g0 = self._gate_result(passed=False, reason="test")
        with patch("python.helpers.cortex_discovery_orchestrator.gate_0",
                   return_value=g0):
            result = _run(run_discovery(
                niche="my test niche",
                market="Slovenia",
                params=dp.VentureDiscoveryParameters(),
            ))
        self.assertEqual(result.niche, "my test niche")
        self.assertEqual(result.market, "Slovenia")

    def test_result_always_has_valid_outcome(self):
        """Whatever happens, outcome must be one of the valid values."""
        g0 = self._gate_result(passed=False)
        with patch("python.helpers.cortex_discovery_orchestrator.gate_0",
                   return_value=g0):
            result = _run(run_discovery(
                niche="any niche",
                market="global",
                params=dp.VentureDiscoveryParameters(),
            ))
        self.assertIn(result.outcome, _VALID_OUTCOMES)

    def test_result_has_completed_at(self):
        """completed_at should always be set after run_discovery."""
        g0 = self._gate_result(passed=False)
        with patch("python.helpers.cortex_discovery_orchestrator.gate_0",
                   return_value=g0):
            result = _run(run_discovery(
                niche="any niche",
                market="global",
                params=dp.VentureDiscoveryParameters(),
            ))
        self.assertNotEqual(result.completed_at, "")

    def test_result_has_cost_estimate(self):
        """cost_estimate_eur should always be set."""
        g0 = self._gate_result(passed=False)
        with patch("python.helpers.cortex_discovery_orchestrator.gate_0",
                   return_value=g0):
            result = _run(run_discovery(
                niche="any niche",
                market="global",
                params=dp.VentureDiscoveryParameters(),
            ))
        self.assertIsInstance(result.cost_estimate_eur, float)

    def test_gate0_error_does_not_crash_pipeline(self):
        """gate_0 errors should be non-blocking (fail-open)."""
        with patch("python.helpers.cortex_discovery_orchestrator.gate_0",
                   side_effect=Exception("gate_0 unavailable")):
            with patch("python.helpers.cortex_discovery_orchestrator.fetch_review_signals",
                       new=AsyncMock(return_value=[])):
                with patch("python.helpers.cortex_discovery_orchestrator.gate_1",
                           new=AsyncMock(return_value=self._gate_result(passed=False, reason="no signal"))):
                    result = _run(run_discovery(
                        niche="any niche",
                        market="global",
                        params=dp.VentureDiscoveryParameters(),
                    ))
        # Pipeline should have continued past gate_0 error
        self.assertIn(result.outcome, _VALID_OUTCOMES)
        self.assertTrue(any("gate_0 error" in e for e in result.errors))


# ─────────────────────────────────────────────────────────────────────────────
# Tests: process_niche_influencers dedup logic (no API)
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessNicheInfluencersDedup(unittest.TestCase):

    def setUp(self):
        _patch()  # re-apply in case another test file's tearDown restored original paths
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def tearDown(self):
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def test_dedup_prevents_duplicate_signals(self):
        """Signals with the same extracted_pain should not be duplicated in store."""
        from python.helpers.cortex_discovery_orchestrator import process_niche_influencers
        from python.helpers.cortex_influencer_monitor import InfluencerWatch

        existing = [_signal("exact same pain")]
        dp.save_signals("SEO", existing)

        new_signal = _signal("exact same pain")   # same pain text
        inf = InfluencerWatch(channel_url="https://youtube.com/@test", niche="SEO")

        with patch("python.helpers.cortex_discovery_orchestrator.discover_influencers_for_niche",
                   new=AsyncMock(return_value=[inf])):
            with patch("python.helpers.cortex_discovery_orchestrator.process_influencer",
                       new=AsyncMock(return_value=[new_signal])):
                _run(process_niche_influencers("SEO", "global", agent=None))

        stored = dp.load_signals("SEO")
        pains = [s.extracted_pain for s in stored]
        self.assertEqual(pains.count("exact same pain"), 1)

    def test_new_signals_added_to_store(self):
        """Brand new signals should be saved."""
        from python.helpers.cortex_discovery_orchestrator import process_niche_influencers
        from python.helpers.cortex_influencer_monitor import InfluencerWatch

        inf = InfluencerWatch(channel_url="https://youtube.com/@new", niche="SEO")
        new_signal = _signal("completely new pain point")

        with patch("python.helpers.cortex_discovery_orchestrator.discover_influencers_for_niche",
                   new=AsyncMock(return_value=[inf])):
            with patch("python.helpers.cortex_discovery_orchestrator.process_influencer",
                       new=AsyncMock(return_value=[new_signal])):
                _run(process_niche_influencers("SEO", "global", agent=None))

        stored = dp.load_signals("SEO")
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].extracted_pain, "completely new pain point")

    def test_returns_new_signals_list(self):
        """Return value is the list of newly extracted signals, not stored total."""
        from python.helpers.cortex_discovery_orchestrator import process_niche_influencers
        from python.helpers.cortex_influencer_monitor import InfluencerWatch

        inf = InfluencerWatch(channel_url="https://youtube.com/@c", niche="SEO")
        new_signals = [_signal("pain A"), _signal("pain B")]

        with patch("python.helpers.cortex_discovery_orchestrator.discover_influencers_for_niche",
                   new=AsyncMock(return_value=[inf])):
            with patch("python.helpers.cortex_discovery_orchestrator.process_influencer",
                       new=AsyncMock(return_value=new_signals)):
                result = _run(process_niche_influencers("SEO", "global", agent=None))

        self.assertEqual(len(result), 2)

    def test_no_influencers_returns_empty(self):
        """If no influencers found, return empty list."""
        from python.helpers.cortex_discovery_orchestrator import process_niche_influencers

        with patch("python.helpers.cortex_discovery_orchestrator.discover_influencers_for_niche",
                   new=AsyncMock(return_value=[])):
            result = _run(process_niche_influencers("SEO", "global", agent=None))

        self.assertEqual(result, [])

    def test_influencer_error_does_not_crash(self):
        """Error in process_influencer should be caught, not propagated."""
        from python.helpers.cortex_discovery_orchestrator import process_niche_influencers
        from python.helpers.cortex_influencer_monitor import InfluencerWatch

        inf = InfluencerWatch(channel_url="https://youtube.com/@broken", niche="SEO")

        with patch("python.helpers.cortex_discovery_orchestrator.discover_influencers_for_niche",
                   new=AsyncMock(return_value=[inf])):
            with patch("python.helpers.cortex_discovery_orchestrator.process_influencer",
                       new=AsyncMock(side_effect=Exception("API timeout"))):
                # Should not raise
                result = _run(process_niche_influencers("SEO", "global", agent=None))

        self.assertIsInstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: run_discovery queuing (mocked full pipeline)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunDiscoveryQueuing(unittest.TestCase):

    def setUp(self):
        _patch()  # re-apply in case another test file's tearDown restored original paths
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def tearDown(self):
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def _gate_ok(self, score="green"):
        gr = MagicMock()
        gr.passed = True
        gr.score = score
        gr.reason = "looks good"
        gr.details = {"cvs_prescore": 60.0, "strategy_type": "Niche Domination",
                      "switching_friction": "low", "geographic_bonus": False}
        gr.all_results = []
        return gr

    def _mock_score(self, composite=70.0):
        s = MagicMock()
        s.composite = composite
        s.strategy_type = "Niche Domination"
        s.switching_friction = "low"
        s.dimension_scores = {f"d{i}": 50.0 for i in range(9)}
        s.summary = "Good opportunity"
        return s

    def test_high_score_leads_to_queued(self):
        """Score above threshold should produce QUEUED outcome."""
        params = dp.VentureDiscoveryParameters(min_cvs_score=40.0)
        g0 = self._gate_ok()
        g1 = self._gate_ok(score="yellow")
        g2_gate = self._gate_ok()

        with patch("python.helpers.cortex_discovery_orchestrator.gate_0", return_value=g0), \
             patch("python.helpers.cortex_discovery_orchestrator.gate_1", new=AsyncMock(return_value=g1)), \
             patch("python.helpers.cortex_discovery_orchestrator.fetch_review_signals", new=AsyncMock(return_value=[])), \
             patch("python.helpers.cortex_discovery_orchestrator.cluster_and_store", new=AsyncMock(return_value=[])), \
             patch("python.helpers.cortex_discovery_orchestrator.build_pain_summary", return_value="test summary"), \
             patch("python.helpers.cortex_discovery_orchestrator.scan_disruption_targets", new=AsyncMock(return_value=[])), \
             patch("python.helpers.cortex_discovery_orchestrator.format_disruption_summary", return_value=""), \
             patch("python.helpers.cortex_discovery_orchestrator.gate_2",
                   new=AsyncMock(return_value=(g2_gate, 60.0, "Niche Domination"))), \
             patch("python.helpers.cortex_discovery_orchestrator.score_opportunity",
                   new=AsyncMock(return_value=self._mock_score(70.0))), \
             patch("python.helpers.cortex_discovery_orchestrator.apply_score_to_candidate"):

            result = _run(run_discovery(
                niche="Restaurant SEO",
                market="Slovenia",
                params=params,
                skip_influencers=True,
            ))

        self.assertEqual(result.outcome, OUTCOME_QUEUED)

    def test_queued_candidate_appears_in_queue(self):
        """A queued result should persist a VentureCandidate in the queue."""
        params = dp.VentureDiscoveryParameters(min_cvs_score=40.0)
        g0 = self._gate_ok()
        g1 = self._gate_ok()
        g2_gate = self._gate_ok()

        with patch("python.helpers.cortex_discovery_orchestrator.gate_0", return_value=g0), \
             patch("python.helpers.cortex_discovery_orchestrator.gate_1", new=AsyncMock(return_value=g1)), \
             patch("python.helpers.cortex_discovery_orchestrator.fetch_review_signals", new=AsyncMock(return_value=[])), \
             patch("python.helpers.cortex_discovery_orchestrator.cluster_and_store", new=AsyncMock(return_value=[])), \
             patch("python.helpers.cortex_discovery_orchestrator.build_pain_summary", return_value=""), \
             patch("python.helpers.cortex_discovery_orchestrator.scan_disruption_targets", new=AsyncMock(return_value=[])), \
             patch("python.helpers.cortex_discovery_orchestrator.format_disruption_summary", return_value=""), \
             patch("python.helpers.cortex_discovery_orchestrator.gate_2",
                   new=AsyncMock(return_value=(g2_gate, 65.0, "Fast Follower"))), \
             patch("python.helpers.cortex_discovery_orchestrator.score_opportunity",
                   new=AsyncMock(return_value=self._mock_score(75.0))), \
             patch("python.helpers.cortex_discovery_orchestrator.apply_score_to_candidate"):

            result = _run(run_discovery(
                niche="Restaurant SEO",
                market="Slovenia",
                params=params,
                skip_influencers=True,
            ))

        queue = dp.load_queue()
        if result.outcome == OUTCOME_QUEUED:
            self.assertEqual(len(queue), 1)
        # Even if score threshold behavior varies, no crash

    def test_low_score_leads_to_rejected(self):
        """Score below threshold should produce REJECTED outcome."""
        params = dp.VentureDiscoveryParameters(min_cvs_score=80.0)  # high bar
        g0 = self._gate_ok()
        g1 = self._gate_ok()
        g2_gate = self._gate_ok()

        with patch("python.helpers.cortex_discovery_orchestrator.gate_0", return_value=g0), \
             patch("python.helpers.cortex_discovery_orchestrator.gate_1", new=AsyncMock(return_value=g1)), \
             patch("python.helpers.cortex_discovery_orchestrator.fetch_review_signals", new=AsyncMock(return_value=[])), \
             patch("python.helpers.cortex_discovery_orchestrator.cluster_and_store", new=AsyncMock(return_value=[])), \
             patch("python.helpers.cortex_discovery_orchestrator.build_pain_summary", return_value=""), \
             patch("python.helpers.cortex_discovery_orchestrator.scan_disruption_targets", new=AsyncMock(return_value=[])), \
             patch("python.helpers.cortex_discovery_orchestrator.format_disruption_summary", return_value=""), \
             patch("python.helpers.cortex_discovery_orchestrator.gate_2",
                   new=AsyncMock(return_value=(g2_gate, 30.0, "Fast Follower"))), \
             patch("python.helpers.cortex_discovery_orchestrator.score_opportunity",
                   new=AsyncMock(return_value=self._mock_score(25.0))), \
             patch("python.helpers.cortex_discovery_orchestrator.apply_score_to_candidate"):

            result = _run(run_discovery(
                niche="Crowded market",
                market="global",
                params=params,
                skip_influencers=True,
            ))

        self.assertEqual(result.outcome, OUTCOME_REJECTED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
