"""
Phase D — Test D-1: Discovery data structures + persistence
Tests: VentureDiscoveryParameters, PainSignal, InfluencerWatch, VentureCandidate,
       all queue operations (add, reject, park, unpark, accept), signal persistence.
All pure Python — no API calls, no agent required.
"""

import os
import sys
import json
import shutil
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Point discovery storage to a temp dir for tests
import python.helpers.cortex_discovery_params as dp

_ORIG_DISCOVERY_DIR = dp._DISCOVERY_DIR
_TEST_DIR = os.path.join("usr", "memory", "cortex_main", "_test_discovery")


def _patch_paths(test_dir: str):
    dp._DISCOVERY_DIR = test_dir
    dp._PARAMS_FILE = os.path.join(test_dir, "params.json")
    dp._PARAMS_HISTORY_DIR = os.path.join(test_dir, "params_history")
    dp._QUEUE_FILE = os.path.join(test_dir, "queue.json")
    dp._REJECTED_FILE = os.path.join(test_dir, "rejected.json")
    dp._PARKED_FILE = os.path.join(test_dir, "parked.json")
    dp._ACCEPTED_FILE = os.path.join(test_dir, "accepted.json")
    dp._INFLUENCERS_FILE = os.path.join(test_dir, "influencers.json")
    dp._SIGNALS_DIR = os.path.join(test_dir, "signals")


def _restore_paths():
    _patch_paths(_ORIG_DISCOVERY_DIR)


class TestVentureDiscoveryParameters(unittest.TestCase):

    def setUp(self):
        _patch_paths(_TEST_DIR)
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def tearDown(self):
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)
        _restore_paths()

    def test_default_creation(self):
        p = dp.VentureDiscoveryParameters()
        self.assertEqual(p.geography, "global")
        self.assertEqual(p.min_cvs_score, 45.0)
        self.assertEqual(p.version, 1)
        self.assertEqual(p.languages, ["en"])

    def test_round_trip(self):
        p = dp.VentureDiscoveryParameters(
            market_domains=["SaaS", "content"],
            geography="EU",
            min_cvs_score=55.0,
            max_capital_requirement=1500.0,
            strategy_preferences=["SaaS Wrapper", "Geographic Rollout"],
        )
        restored = dp.VentureDiscoveryParameters.from_dict(p.to_dict())
        self.assertEqual(restored.geography, "EU")
        self.assertEqual(restored.min_cvs_score, 55.0)
        self.assertEqual(restored.max_capital_requirement, 1500.0)
        self.assertEqual(restored.strategy_preferences, ["SaaS Wrapper", "Geographic Rollout"])

    def test_save_and_load(self):
        p = dp.VentureDiscoveryParameters(geography="Slovenia", min_cvs_score=60.0)
        p.save()
        loaded = dp.VentureDiscoveryParameters.load()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.geography, "Slovenia")
        self.assertEqual(loaded.min_cvs_score, 60.0)

    def test_load_returns_none_when_missing(self):
        result = dp.VentureDiscoveryParameters.load()
        self.assertIsNone(result)

    def test_update_increments_version(self):
        p = dp.VentureDiscoveryParameters(geography="EU", version=1)
        p2 = p.update(geography="Slovenia", min_cvs_score=50.0)
        self.assertEqual(p2.version, 2)
        self.assertEqual(p2.geography, "Slovenia")
        self.assertEqual(p.geography, "EU")   # original unchanged

    def test_save_and_archive(self):
        p1 = dp.VentureDiscoveryParameters(geography="global", version=1)
        p1.save()
        p2 = p1.update(geography="EU")
        p2.save_and_archive()

        # Current params should be v2
        loaded = dp.VentureDiscoveryParameters.load()
        self.assertEqual(loaded.geography, "EU")
        self.assertEqual(loaded.version, 2)

        # History should have v1
        history_dir = dp._PARAMS_HISTORY_DIR
        history_files = os.listdir(history_dir)
        self.assertEqual(len(history_files), 1)
        self.assertTrue(history_files[0].startswith("v1__"))

    def test_summary_string(self):
        p = dp.VentureDiscoveryParameters(
            market_domains=["SaaS"],
            geography="EU",
            min_cvs_score=50.0,
        )
        s = p.summary()
        self.assertIn("EU", s)
        self.assertIn("SaaS", s)
        self.assertIn("50", s)


class TestPainSignal(unittest.TestCase):

    def test_creation_and_round_trip(self):
        s = dp.PainSignal(
            source="reddit",
            source_url="https://reddit.com/r/test/123",
            raw_text="I pay $50/month for X but it can't do Y",
            extracted_pain="X tool missing Y feature despite paid subscription",
            tool_mentioned="X",
            paying_evidence=True,
            strength=3,
        )
        restored = dp.PainSignal.from_dict(s.to_dict())
        self.assertEqual(restored.source, "reddit")
        self.assertTrue(restored.paying_evidence)
        self.assertEqual(restored.strength, 3)
        self.assertEqual(restored.tool_mentioned, "X")

    def test_default_id_generated(self):
        s1 = dp.PainSignal()
        s2 = dp.PainSignal()
        self.assertNotEqual(s1.id, s2.id)


class TestInfluencerWatch(unittest.TestCase):

    def setUp(self):
        _patch_paths(_TEST_DIR)
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def tearDown(self):
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)
        _restore_paths()

    def test_round_trip(self):
        w = dp.InfluencerWatch(
            platform="youtube",
            handle="TestChannel",
            channel_url="https://youtube.com/c/testchannel",
            niche="SaaS tools",
        )
        restored = dp.InfluencerWatch.from_dict(w.to_dict())
        self.assertEqual(restored.handle, "TestChannel")
        self.assertEqual(restored.niche, "SaaS tools")
        self.assertTrue(restored.active)

    def test_add_influencer_dedup(self):
        w1 = dp.InfluencerWatch(
            platform="youtube",
            channel_url="https://youtube.com/c/same",
            niche="tools",
        )
        w2 = dp.InfluencerWatch(
            platform="youtube",
            channel_url="https://youtube.com/c/same",
            niche="tools",
        )
        dp.add_influencer(w1)
        dp.add_influencer(w2)   # should not duplicate
        all_inf = dp.load_influencers()
        self.assertEqual(len(all_inf), 1)

    def test_load_empty_returns_list(self):
        result = dp.load_influencers()
        self.assertEqual(result, [])


class TestVentureCandidate(unittest.TestCase):

    def _make_candidate(self, name="Test Venture", cvs=65.0):
        signals = [
            dp.PainSignal(source="reddit", paying_evidence=True, extracted_pain="missing X"),
            dp.PainSignal(source="g2", paying_evidence=True, extracted_pain="lacks Y"),
        ]
        return dp.VentureCandidate(
            name=name,
            source="pain_mining",
            source_signals=signals,
            niche="project management SaaS",
            market="EU",
            strategy_type="Fast Follower",
            gate_scores={"gate_0": "pass", "gate_1": "pass", "gate_2": "pass"},
            cvs_prescore=cvs,
            opportunity_summary="Strong pain signal, clear switching intent.",
        )

    def test_round_trip(self):
        c = self._make_candidate()
        restored = dp.VentureCandidate.from_dict(c.to_dict())
        self.assertEqual(restored.name, "Test Venture")
        self.assertEqual(restored.strategy_type, "Fast Follower")
        self.assertEqual(len(restored.source_signals), 2)
        self.assertTrue(restored.source_signals[0].paying_evidence)

    def test_short_summary(self):
        c = self._make_candidate()
        s = c.short_summary()
        self.assertIn("Test Venture", s)
        self.assertIn("Fast Follower", s)
        self.assertIn("65", s)


class TestQueueOperations(unittest.TestCase):

    def setUp(self):
        _patch_paths(_TEST_DIR)
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def tearDown(self):
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)
        _restore_paths()

    def _make_candidate(self, name="Test", cvs=60.0):
        return dp.VentureCandidate(
            name=name,
            source="autonomous",
            niche=name.lower(),
            market="EU",
            cvs_prescore=cvs,
        )

    def test_add_and_load_queue(self):
        c = self._make_candidate("Alpha", cvs=70.0)
        dp.add_to_queue(c)
        q = dp.load_queue()
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0].name, "Alpha")

    def test_queue_sorted_by_cvs_descending(self):
        dp.add_to_queue(self._make_candidate("Low", cvs=40.0))
        dp.add_to_queue(self._make_candidate("High", cvs=80.0))
        dp.add_to_queue(self._make_candidate("Mid", cvs=60.0))
        q = dp.load_queue()
        scores = [c.cvs_prescore for c in q]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_add_dedup(self):
        c = self._make_candidate("Alpha")
        dp.add_to_queue(c)
        dp.add_to_queue(c)   # same id — should not duplicate
        self.assertEqual(len(dp.load_queue()), 1)

    def test_remove_from_queue(self):
        c = self._make_candidate("Alpha")
        dp.add_to_queue(c)
        removed = dp.remove_from_queue(c.id)
        self.assertIsNotNone(removed)
        self.assertEqual(len(dp.load_queue()), 0)

    def test_remove_nonexistent_returns_none(self):
        result = dp.remove_from_queue("nonexistent_id")
        self.assertIsNone(result)

    def test_reject_candidate(self):
        c = self._make_candidate("Beta")
        dp.add_to_queue(c)
        result = dp.reject_candidate(c.id, reason="Too competitive")
        self.assertTrue(result)
        self.assertEqual(len(dp.load_queue()), 0)
        rejected = dp.load_rejected()
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].status, "rejected")
        self.assertEqual(rejected[0].rejection_reason, "Too competitive")

    def test_is_already_rejected(self):
        c = self._make_candidate("Beta")
        c.niche = "project management"
        c.market = "EU"
        dp.add_to_queue(c)
        dp.reject_candidate(c.id)
        self.assertTrue(dp.is_already_rejected("project management", "EU"))
        self.assertFalse(dp.is_already_rejected("crm software", "EU"))

    def test_park_and_load(self):
        c = self._make_candidate("Gamma")
        dp.add_to_queue(c)
        result = dp.park_candidate(
            c.id,
            reason="Capital too high now",
            revisit_condition="When capital > €5K",
            revisit_date="2027-01-01",
        )
        self.assertTrue(result)
        self.assertEqual(len(dp.load_queue()), 0)
        parked = dp.load_parked()
        self.assertEqual(len(parked), 1)
        self.assertEqual(parked[0].status, "parked")
        self.assertEqual(parked[0].park_revisit_condition, "When capital > €5K")

    def test_unpark_candidate(self):
        c = self._make_candidate("Gamma")
        dp.add_to_queue(c)
        dp.park_candidate(c.id, reason="Too early")
        dp.unpark_candidate(c.id)
        self.assertEqual(len(dp.load_parked()), 0)
        self.assertEqual(len(dp.load_queue()), 1)

    def test_accept_candidate(self):
        c = self._make_candidate("Delta")
        c.research_context = '{"summary": "Market is strong"}'
        dp.add_to_queue(c)
        accepted = dp.accept_candidate(c.id)
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted.status, "accepted")
        self.assertEqual(accepted.research_context, '{"summary": "Market is strong"}')
        self.assertEqual(len(dp.load_queue()), 0)
        self.assertEqual(len(dp.load_accepted()), 1)

    def test_get_parked_due_for_revisit(self):
        c1 = self._make_candidate("Past")
        c2 = self._make_candidate("Future")
        dp.add_to_queue(c1)
        dp.add_to_queue(c2)
        dp.park_candidate(c1.id, reason="test", revisit_date="2020-01-01")  # past
        dp.park_candidate(c2.id, reason="test", revisit_date="2099-01-01")  # future
        due = dp.get_parked_due_for_revisit()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].name, "Past")


class TestSignalPersistence(unittest.TestCase):

    def setUp(self):
        _patch_paths(_TEST_DIR)
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def tearDown(self):
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)
        _restore_paths()

    def test_save_and_load_signals(self):
        signals = [
            dp.PainSignal(source="reddit", extracted_pain="missing export", source_url="http://a.com/1"),
            dp.PainSignal(source="g2", extracted_pain="no API", source_url="http://b.com/2"),
        ]
        dp.save_signals("project management SaaS", signals)
        loaded = dp.load_signals("project management SaaS")
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].source, "reddit")

    def test_load_signals_missing_returns_empty(self):
        result = dp.load_signals("nonexistent niche")
        self.assertEqual(result, [])

    def test_append_signals_dedup(self):
        s1 = dp.PainSignal(source="reddit", source_url="http://same.com/1", extracted_pain="pain A")
        s2 = dp.PainSignal(source="g2", source_url="http://same.com/1", extracted_pain="pain B")  # same URL
        s3 = dp.PainSignal(source="g2", source_url="http://different.com/2", extracted_pain="pain C")

        dp.append_signals("test niche", [s1])
        dp.append_signals("test niche", [s2, s3])   # s2 should be deduped

        loaded = dp.load_signals("test niche")
        self.assertEqual(len(loaded), 2)   # s1 + s3 only

    def test_niche_slug_isolation(self):
        dp.save_signals("SaaS tools", [dp.PainSignal(source="reddit", extracted_pain="A")])
        dp.save_signals("content creation", [dp.PainSignal(source="g2", extracted_pain="B")])
        a = dp.load_signals("SaaS tools")
        b = dp.load_signals("content creation")
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)
        self.assertNotEqual(a[0].source, b[0].source)


class TestGate0(unittest.TestCase):

    def setUp(self):
        from python.helpers.cortex_discovery_gates import gate_0
        self.gate_0 = gate_0

    def test_passes_clean_niche(self):
        result = self.gate_0("local SEO agency", "Help restaurants rank on Google")
        self.assertTrue(result.passed)
        self.assertEqual(result.score, "pass")

    def test_fails_regulatory(self):
        result = self.gate_0("financial advice platform", "Give investment advice to retail investors")
        self.assertFalse(result.passed)
        self.assertIn("Regulatory", result.reason)

    def test_fails_hardware(self):
        result = self.gate_0("smart home hardware device", "IoT sensor for energy monitoring")
        self.assertFalse(result.passed)
        self.assertIn("Hardware", result.reason)

    def test_fails_breakthrough_tech(self):
        result = self.gate_0("quantum computing SaaS", "Quantum algorithms as a service")
        self.assertFalse(result.passed)
        self.assertIn("Breakthrough", result.reason)

    def test_fails_capital_cap(self):
        from python.helpers.cortex_discovery_params import VentureDiscoveryParameters
        params = VentureDiscoveryParameters(max_capital_requirement=500.0)
        result = self.gate_0("enterprise software", "", capital_estimate_eur=5000.0, params=params)
        self.assertFalse(result.passed)
        self.assertIn("Capital", result.reason)

    def test_passes_when_capital_within_cap(self):
        from python.helpers.cortex_discovery_params import VentureDiscoveryParameters
        params = VentureDiscoveryParameters(max_capital_requirement=2000.0)
        result = self.gate_0("newsletter tool", "", capital_estimate_eur=300.0, params=params)
        self.assertTrue(result.passed)

    def test_park_condition_provided_on_failure(self):
        result = self.gate_0("pharmaceutical drug platform", "Sell prescription drugs online")
        self.assertFalse(result.passed)
        self.assertIsNotNone(result.park_condition)
        self.assertTrue(len(result.park_condition) > 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
