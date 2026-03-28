"""
Phase D -- Test D-4: Influencer Monitor (pure logic only, no API calls)
========================================================================
Tests: VideoCandidate model, score_video, _extract_video_id, _resolve_space,
       _build_surfsense_title, add_to_watchlist, score ordering, age_days.
No network calls, no LLM, no SurfSense.
"""

import asyncio
import os
import sys
import shutil
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import python.helpers.cortex_discovery_params as dp

_TEST_DIR = os.path.join("usr", "memory", "cortex_main", "_test_d4")


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

from python.helpers.cortex_influencer_monitor import (
    VideoCandidate,
    ExtractedIntelligence,
    score_video,
    compute_combined_score,
    _extract_video_id,
    _extract_tags_from_content,
    _resolve_space,
    _build_surfsense_title,
    add_to_watchlist,
)


def _video(title, days_old=30, url="https://youtube.com/watch?v=dQw4w9WgXcQ"):
    v = VideoCandidate(
        video_id=_extract_video_id(url) or "testid",
        title=title,
        url=url,
        published_at=(datetime.utcnow() - timedelta(days=days_old)).strftime("%Y-%m-%d"),
    )
    return v


class TestVideoCandidate(unittest.TestCase):

    def test_age_days_recent(self):
        v = _video("test", days_old=10)
        self.assertIsNotNone(v.age_days)
        self.assertAlmostEqual(v.age_days, 10, delta=1)

    def test_age_days_old(self):
        v = _video("test", days_old=200)
        self.assertGreater(v.age_days, 190)

    def test_age_days_no_date(self):
        v = VideoCandidate(video_id="x", title="t", url="http://example.com")
        self.assertIsNone(v.age_days)


class TestExtractVideoId(unittest.TestCase):

    def test_standard_watch_url(self):
        self.assertEqual(
            _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ"
        )

    def test_short_url(self):
        self.assertEqual(
            _extract_video_id("https://youtu.be/dQw4w9WgXcQ"),
            "dQw4w9WgXcQ"
        )

    def test_shorts_url(self):
        self.assertEqual(
            _extract_video_id("https://www.youtube.com/shorts/abcdefghijk"),
            "abcdefghijk"
        )

    def test_non_youtube_returns_empty(self):
        self.assertEqual(_extract_video_id("https://vimeo.com/12345"), "")

    def test_embed_url(self):
        self.assertEqual(
            _extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ"),
            "dQw4w9WgXcQ"
        )


class TestScoreVideo(unittest.TestCase):

    def test_recent_pain_video_scores_high(self):
        v = _video("The REAL Problem with Local SEO for Restaurants (avoid these mistakes)", days_old=14)
        score = score_video(v, "local SEO for restaurants")
        self.assertGreater(score, 0.6)

    def test_old_irrelevant_video_scores_low(self):
        v = _video("My travel vlog from 2022", days_old=500)
        score = score_video(v, "local SEO for restaurants")
        self.assertLess(score, 0.3)

    def test_recency_impacts_score(self):
        recent = _video("SEO tips for restaurants", days_old=7)
        old = _video("SEO tips for restaurants", days_old=400)
        s_recent = score_video(recent, "SEO restaurants")
        s_old = score_video(old, "SEO restaurants")
        self.assertGreater(s_recent, s_old)

    def test_pain_keywords_boost_score(self):
        pain = _video("Why I stopped using this SEO tool (honest review)", days_old=30)
        bland = _video("SEO tutorial 2025", days_old=30)
        s_pain = score_video(pain, "SEO tools")
        s_bland = score_video(bland, "SEO tools")
        self.assertGreater(s_pain, s_bland)

    def test_niche_fit_boosts_score(self):
        relevant = _video("Restaurant SEO agency problems and alternatives", days_old=30)
        unrelated = _video("Woodworking tips and tricks 2025", days_old=30)
        s_rel = score_video(relevant, "SEO agency for restaurants")
        s_unrel = score_video(unrelated, "SEO agency for restaurants")
        self.assertGreater(s_rel, s_unrel)

    def test_score_is_between_0_and_1(self):
        v = _video("anything", days_old=100)
        score = score_video(v, "some niche")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_returns_float(self):
        v = _video("test", days_old=30)
        self.assertIsInstance(score_video(v, "test niche"), float)


class TestResolveSpace(unittest.TestCase):

    def test_ai_niche_goes_to_cortex_main(self):
        self.assertEqual(_resolve_space("autonomous ai agents"), "cortex_main")

    def test_llm_niche_goes_to_cortex_main(self):
        self.assertEqual(_resolve_space("LLM fine-tuning"), "cortex_main")

    def test_agi_niche_goes_to_cortex_main(self):
        self.assertEqual(_resolve_space("AGI and foundation models"), "cortex_main")

    def test_regular_niche_goes_to_discovery(self):
        self.assertEqual(_resolve_space("local SEO for restaurants"), "discovery")

    def test_saas_niche_goes_to_discovery(self):
        self.assertEqual(_resolve_space("SaaS invoicing tools"), "discovery")


class TestBuildSurfsenseTitle(unittest.TestCase):

    def _make_intel(self, creator, title, niche, paying=1, total=2, tools=None):
        intel = ExtractedIntelligence(
            creator=creator,
            video_title=title,
            niche=niche,
            published_at="2025-06",
            pain_signals=[
                dp.PainSignal(source="youtube", paying_evidence=(i < paying),
                              extracted_pain="test pain")
                for i in range(total)
            ],
            tools_mentioned=tools or [],
        )
        return intel

    def test_title_contains_creator(self):
        intel = self._make_intel("@testcreator", "Test Video", "SEO")
        video = _video("Test Video", days_old=30)
        title = _build_surfsense_title(intel, video)
        self.assertIn("@testcreator", title)

    def test_title_contains_video_title(self):
        intel = self._make_intel("@creator", "My Special Video Title", "SEO")
        video = _video("My Special Video Title", days_old=30)
        title = _build_surfsense_title(intel, video)
        self.assertIn("My Special Video Title", title)

    def test_title_contains_signal_count(self):
        intel = self._make_intel("@c", "Video", "SEO", paying=2, total=3)
        video = _video("Video", days_old=30)
        title = _build_surfsense_title(intel, video)
        self.assertIn("3 signals", title)
        self.assertIn("2 paying", title)

    def test_title_contains_tools_when_present(self):
        intel = self._make_intel("@c", "V", "SEO", tools=["Semrush", "Ahrefs"])
        video = _video("V", days_old=30)
        title = _build_surfsense_title(intel, video)
        self.assertIn("Semrush", title)

    def test_title_is_string(self):
        intel = self._make_intel("@c", "V", "niche")
        video = _video("V")
        self.assertIsInstance(_build_surfsense_title(intel, video), str)


class TestAddToWatchlist(unittest.TestCase):

    def setUp(self):
        _patch()  # re-apply in case another test file's tearDown restored original paths
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def tearDown(self):
        if os.path.exists(_TEST_DIR):
            shutil.rmtree(_TEST_DIR)

    def test_add_influencer_persists(self):
        iw = add_to_watchlist(
            "https://youtube.com/@testchannel",
            niche="local SEO",
            handle="@testchannel",
        )
        loaded = dp.load_influencers()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].channel_url, "https://youtube.com/@testchannel")

    def test_dedup_by_url(self):
        add_to_watchlist("https://youtube.com/@chan", niche="SEO", handle="@chan")
        add_to_watchlist("https://youtube.com/@chan", niche="SEO", handle="@chan")
        loaded = dp.load_influencers()
        self.assertEqual(len(loaded), 1)

    def test_returns_influencer_watch(self):
        from python.helpers.cortex_discovery_params import InfluencerWatch
        iw = add_to_watchlist("https://youtube.com/@c", niche="SEO")
        self.assertIsInstance(iw, InfluencerWatch)

    def test_core_intel_niche_stored_correctly(self):
        add_to_watchlist(
            "https://youtube.com/@airesearcher",
            niche="autonomous ai agents",
            handle="@airesearcher",
        )
        loaded = dp.load_influencers()
        self.assertEqual(loaded[0].niche, "autonomous ai agents")
        # Confirm space resolves to cortex_main
        self.assertEqual(_resolve_space(loaded[0].niche), "cortex_main")


class TestComputeCombinedScore(unittest.TestCase):
    """Tests for the two-pass combined scoring formula."""

    def _scan(self, pain=False, paying=False, switching=False, delivers=True, confidence=50):
        return {
            "has_specific_pain": pain,
            "paying_evidence": paying,
            "switching_intent": switching,
            "content_delivers": delivers,
            "confidence": confidence,
        }

    def test_returns_float(self):
        s = compute_combined_score(0.5, self._scan())
        self.assertIsInstance(s, float)

    def test_score_between_0_and_1(self):
        for pain in [True, False]:
            for paying in [True, False]:
                s = compute_combined_score(0.5, self._scan(pain=pain, paying=paying))
                self.assertGreaterEqual(s, 0.0)
                self.assertLessEqual(s, 1.0)

    def test_all_flags_true_scores_higher(self):
        high = compute_combined_score(0.8, self._scan(True, True, True, True, 90))
        low = compute_combined_score(0.2, self._scan(False, False, False, True, 10))
        self.assertGreater(high, low)

    def test_clickbait_penalty_applied(self):
        """content_delivers=False should significantly reduce score."""
        delivers = compute_combined_score(0.8, self._scan(True, True, True, True, 90))
        clickbait = compute_combined_score(0.8, self._scan(True, True, True, False, 90))
        self.assertGreater(delivers, clickbait)
        # Penalty is 0.6x multiplier
        self.assertAlmostEqual(clickbait / delivers, 0.6, delta=0.05)

    def test_switching_intent_boosts_score(self):
        without = compute_combined_score(0.5, self._scan(True, True, False, True, 60))
        with_ = compute_combined_score(0.5, self._scan(True, True, True, True, 60))
        self.assertGreater(with_, without)

    def test_paying_evidence_boosts_more_than_switching(self):
        paying = compute_combined_score(0.5, self._scan(False, True, False, True, 50))
        switching = compute_combined_score(0.5, self._scan(False, False, True, True, 50))
        self.assertGreater(paying, switching)

    def test_high_confidence_matters(self):
        high_conf = compute_combined_score(0.5, self._scan(confidence=90))
        low_conf = compute_combined_score(0.5, self._scan(confidence=10))
        self.assertGreater(high_conf, low_conf)

    def test_video_score_zero_still_scores_from_scan(self):
        """Even zero metadata score gets a score from scan flags."""
        s = compute_combined_score(0.0, self._scan(True, True, True, True, 80))
        self.assertGreater(s, 0.0)

    def test_perfect_input_near_1(self):
        s = compute_combined_score(1.0, self._scan(True, True, True, True, 100))
        self.assertGreaterEqual(s, 0.95)


class TestScoreVideoWithTags(unittest.TestCase):

    def test_tags_boost_niche_fit(self):
        """Tags containing niche keywords should boost the score."""
        v = _video("General video title", days_old=30)
        score_no_tags = score_video(v, "restaurant SEO")
        score_with_tags = score_video(v, "restaurant SEO", tags="restaurant SEO local search")
        self.assertGreaterEqual(score_with_tags, score_no_tags)

    def test_tags_boost_pain_signal(self):
        """Tags with pain keywords boost title_signal component."""
        v = _video("Interview with expert", days_old=30)
        score_plain = score_video(v, "SEO tools")
        score_with_pain_tags = score_video(v, "SEO tools", tags="mistake avoid alternative switch")
        self.assertGreater(score_with_pain_tags, score_plain)

    def test_empty_tags_backward_compatible(self):
        """score_video with no tags arg should work identically to before."""
        v = _video("Test video", days_old=60)
        s1 = score_video(v, "SEO")
        s2 = score_video(v, "SEO", tags="")
        self.assertEqual(s1, s2)


class TestExtractTagsFromContent(unittest.TestCase):

    def test_finds_comma_separated_tags(self):
        content = "Video about SEO strategies.\nseo, local search, google maps, restaurant marketing"
        tags = _extract_tags_from_content(content)
        self.assertIn("seo", tags.lower())

    def test_returns_empty_when_no_tags(self):
        content = "This is a long paragraph about something with no comma lists at all."
        tags = _extract_tags_from_content(content)
        self.assertIsInstance(tags, str)

    def test_returns_string_always(self):
        self.assertIsInstance(_extract_tags_from_content(""), str)
        self.assertIsInstance(_extract_tags_from_content("a, b, c"), str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
