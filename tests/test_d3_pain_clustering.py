"""
Phase D -- Test D-3: Pain Clustering
=====================================
Tests: cluster_signals (keyword fallback), build_pain_summary, PainCluster model.
No API calls -- uses use_llm=False throughout.
Graphiti store is tested for graceful failure when unconfigured.
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from python.helpers.cortex_discovery_params import PainSignal
from python.helpers.cortex_pain_clustering import (
    PainCluster,
    build_pain_summary,
    cluster_and_store,
    cluster_signals,
    store_clusters_to_graphiti,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_signals():
    return [
        PainSignal(source="reddit",   paying_evidence=True,  strength=2,
                   extracted_pain="This tool is so expensive, paying $200/month for basic features",
                   raw_text="pricing is outrageous"),
        PainSignal(source="g2",       paying_evidence=True,  strength=3,
                   extracted_pain="Costs way too much for what you get, looking for alternatives",
                   raw_text="overpriced, switching"),
        PainSignal(source="capterra", paying_evidence=False, strength=1,
                   extracted_pain="I wish it had better reporting features, missing export option",
                   raw_text="missing features"),
        PainSignal(source="reddit",   paying_evidence=False, strength=1,
                   extracted_pain="No way to export data, feature has been requested for years",
                   raw_text="feature request"),
        PainSignal(source="twitter",  paying_evidence=True,  strength=2,
                   extracted_pain="Support is terrible, takes 3 days to respond",
                   raw_text="slow support"),
        PainSignal(source="g2",       paying_evidence=False, strength=1,
                   extracted_pain="App crashes constantly, very unreliable",
                   raw_text="bug crash"),
    ]


class TestPainClusterModel(unittest.TestCase):

    def test_cluster_signal_count(self):
        sigs = make_signals()[:3]
        c = PainCluster(
            theme="Test",
            signals=sigs,
            strength=6,
            paying_count=2,
            representative_pain="test pain",
            sources=["reddit", "g2"],
        )
        self.assertEqual(c.signal_count, 3)

    def test_paying_ratio(self):
        sigs = make_signals()[:4]
        c = PainCluster(
            theme="Test",
            signals=sigs,
            strength=7,
            paying_count=2,
            representative_pain="test",
            sources=["reddit"],
        )
        self.assertAlmostEqual(c.paying_ratio, 0.5)

    def test_to_dict_keys(self):
        sigs = make_signals()[:2]
        c = PainCluster(theme="T", signals=sigs, strength=3, paying_count=1,
                        representative_pain="p", sources=["reddit"])
        d = c.to_dict()
        for key in ["theme", "signal_count", "strength", "paying_count",
                    "paying_ratio", "representative_pain", "sources"]:
            self.assertIn(key, d)


class TestKeywordClustering(unittest.TestCase):

    def test_returns_list_of_pain_clusters(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test niche", agent=None, use_llm=False))
        self.assertIsInstance(clusters, list)
        self.assertTrue(len(clusters) > 0)
        self.assertIsInstance(clusters[0], PainCluster)

    def test_all_signals_assigned(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test niche", agent=None, use_llm=False))
        total = sum(c.signal_count for c in clusters)
        self.assertEqual(total, len(sigs))

    def test_sorted_paying_first(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test niche", agent=None, use_llm=False))
        # First cluster should have paying_count >= last cluster
        if len(clusters) > 1:
            self.assertGreaterEqual(clusters[0].paying_count, clusters[-1].paying_count)

    def test_sources_unique_per_cluster(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test niche", agent=None, use_llm=False))
        for c in clusters:
            self.assertEqual(len(c.sources), len(set(c.sources)))

    def test_strength_sum_correct(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test niche", agent=None, use_llm=False))
        for c in clusters:
            expected = sum(s.strength for s in c.signals)
            self.assertEqual(c.strength, expected)

    def test_paying_count_correct(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test niche", agent=None, use_llm=False))
        for c in clusters:
            expected = sum(1 for s in c.signals if s.paying_evidence)
            self.assertEqual(c.paying_count, expected)

    def test_representative_pain_is_string(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test niche", agent=None, use_llm=False))
        for c in clusters:
            self.assertIsInstance(c.representative_pain, str)

    def test_empty_signals_returns_empty(self):
        clusters = run(cluster_signals([], "test niche", agent=None, use_llm=False))
        self.assertEqual(clusters, [])

    def test_single_signal(self):
        sigs = [make_signals()[0]]
        clusters = run(cluster_signals(sigs, "test niche", agent=None, use_llm=False))
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].signal_count, 1)

    def test_pricing_keyword_cluster(self):
        """Signals with 'expensive'/'cost' keywords should land in pricing cluster."""
        sigs = [
            PainSignal(source="reddit", paying_evidence=True, strength=1,
                       extracted_pain="way too expensive", raw_text="expensive overpriced"),
        ]
        clusters = run(cluster_signals(sigs, "test", agent=None, use_llm=False))
        self.assertIn("Pricing", clusters[0].theme)

    def test_missing_feature_cluster(self):
        sigs = [
            PainSignal(source="g2", paying_evidence=False, strength=1,
                       extracted_pain="missing export feature wish it existed", raw_text="missing wish"),
        ]
        clusters = run(cluster_signals(sigs, "test", agent=None, use_llm=False))
        self.assertIn("Missing", clusters[0].theme)

    def test_switching_cluster(self):
        sigs = [
            PainSignal(source="reddit", paying_evidence=True, strength=2,
                       extracted_pain="looking for alternative to this tool", raw_text="alternative switch"),
        ]
        clusters = run(cluster_signals(sigs, "test", agent=None, use_llm=False))
        self.assertIn("Switching", clusters[0].theme)


class TestBuildPainSummary(unittest.TestCase):

    def test_returns_string(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test", agent=None, use_llm=False))
        summary = build_pain_summary(clusters)
        self.assertIsInstance(summary, str)

    def test_non_empty_with_clusters(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test", agent=None, use_llm=False))
        summary = build_pain_summary(clusters)
        self.assertTrue(len(summary) > 0)

    def test_respects_max_chars(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test", agent=None, use_llm=False))
        summary = build_pain_summary(clusters, max_chars=100)
        self.assertLessEqual(len(summary), 100)

    def test_empty_clusters_returns_empty(self):
        self.assertEqual(build_pain_summary([]), "")

    def test_contains_theme_names(self):
        sigs = make_signals()
        clusters = run(cluster_signals(sigs, "test", agent=None, use_llm=False))
        summary = build_pain_summary(clusters)
        # At least one cluster theme should appear in the summary
        found = any(c.theme[:10] in summary for c in clusters)
        self.assertTrue(found)


class TestGraphitiStoreFallback(unittest.TestCase):

    def test_no_graphiti_key_returns_false(self):
        """Without ZEP_API_KEY, store should return False gracefully."""
        import os
        orig = os.environ.pop("ZEP_API_KEY", None)
        orig2 = os.environ.pop("GRAPHITI_API_KEY", None)
        try:
            sigs = make_signals()
            clusters = run(cluster_signals(sigs, "test", agent=None, use_llm=False))
            result = run(store_clusters_to_graphiti(clusters, "test niche", "global", agent=None))
            self.assertFalse(result)
        finally:
            if orig:
                os.environ["ZEP_API_KEY"] = orig
            if orig2:
                os.environ["GRAPHITI_API_KEY"] = orig2

    def test_cluster_and_store_returns_clusters_even_without_graphiti(self):
        """cluster_and_store should return clusters even when Graphiti unavailable."""
        import os
        orig = os.environ.pop("ZEP_API_KEY", None)
        orig2 = os.environ.pop("GRAPHITI_API_KEY", None)
        try:
            sigs = make_signals()
            clusters = run(cluster_and_store(sigs, "test niche", agent=None, use_llm=False))
            self.assertIsInstance(clusters, list)
            self.assertTrue(len(clusters) > 0)
        finally:
            if orig:
                os.environ["ZEP_API_KEY"] = orig
            if orig2:
                os.environ["GRAPHITI_API_KEY"] = orig2


if __name__ == "__main__":
    unittest.main(verbosity=2)
