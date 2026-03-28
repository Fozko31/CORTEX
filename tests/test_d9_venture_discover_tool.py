"""
Tests for D-9: VentureDiscover tool (python/tools/venture_discover.py)
and the _format_result helper.

These tests cover:
- Missing niche guard
- Invalid mode guard
- Mode -> skip_influencers mapping
- _format_result for all four outcomes (queued / rejected / parked / error)
- args dict fallback (agent passes args via self.args)

No API calls. All orchestrator calls are mocked.
"""

import asyncio
import sys
import os

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Fake DiscoveryResult (mirrors cortex_discovery_orchestrator.DiscoveryResult) ──

@dataclass
class FakeDiscoveryResult:
    niche: str = "test niche"
    market: str = "global"
    outcome: str = "queued"
    reason: str = "CVS 68 >= threshold 40"
    signals: List[Any] = field(default_factory=list)
    clusters: List[Any] = field(default_factory=list)
    disruption_targets: List[Any] = field(default_factory=list)
    candidate: Optional[Any] = None
    gate_result: Optional[Any] = None
    final_score: Optional[float] = 68.0
    strategy_type: str = "Niche Domination"
    pain_summary: str = "Pain summary text"
    disruption_summary: str = "Disruption summary text"
    cost_estimate_eur: float = 0.025
    steps_completed: List[str] = field(default_factory=lambda: ["gate_0", "signal_ingestion"])
    steps_skipped: List[str] = field(default_factory=lambda: ["influencers"])
    errors: List[str] = field(default_factory=list)
    started_at: str = "2026-03-26T03:00:00"
    completed_at: str = "2026-03-26T03:00:05"

    def to_dict(self):
        return {"niche": self.niche, "outcome": self.outcome}


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_fake_tool(niche="", market="global", mode="fast", max_cost_eur=0.5, args_dict=None):
    """Build a VentureDiscover instance without a real Agent."""
    from python.tools.venture_discover import VentureDiscover

    agent = MagicMock()
    agent.config = MagicMock()
    agent.config.profile = "cortex"

    tool = VentureDiscover.__new__(VentureDiscover)
    tool.agent = agent
    tool.args = args_dict or {}
    # Provide keyword args as if they were passed by the agent framework
    tool._niche = niche
    tool._market = market
    tool._mode = mode
    tool._max_cost_eur = max_cost_eur

    # Patch execute signature binding
    return tool


async def _execute(tool, niche="", market="global", mode="fast", max_cost_eur=0.5):
    return await tool.execute(niche=niche, market=market, mode=mode, max_cost_eur=max_cost_eur)


# ── Tests: input validation ────────────────────────────────────────────────────

class TestInputValidation:

    def test_missing_niche_returns_error(self):
        from python.tools.venture_discover import VentureDiscover
        agent = MagicMock()
        tool = VentureDiscover.__new__(VentureDiscover)
        tool.agent = agent
        tool.args = {}

        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(niche="", market="global", mode="fast")
        )
        assert "niche" in result.message.lower()
        assert result.break_loop is False

    def test_niche_from_args_dict(self):
        """Agent may pass niche via self.args dict, not keyword arg."""
        from python.tools.venture_discover import VentureDiscover
        agent = MagicMock()
        tool = VentureDiscover.__new__(VentureDiscover)
        tool.agent = agent
        tool.args = {"niche": "AI bookkeeping", "market": "EU"}

        # niche="" in kwargs but self.args has it
        # Lazy imports inside execute() — must patch at the source module
        with patch(
            "python.helpers.cortex_discovery_params.VentureDiscoveryParameters"
        ) as MockParams, patch(
            "python.helpers.cortex_discovery_orchestrator.run_discovery",
            new=AsyncMock(return_value=FakeDiscoveryResult(niche="AI bookkeeping"))
        ):
            MockParams.load.return_value = MagicMock(target_niches=[])
            result = asyncio.get_event_loop().run_until_complete(
                tool.execute(niche="", market="global", mode="fast")
            )
        # Should not return the "niche required" error
        assert "requires a `niche`" not in result.message

    def test_invalid_mode_returns_error(self):
        from python.tools.venture_discover import VentureDiscover
        agent = MagicMock()
        tool = VentureDiscover.__new__(VentureDiscover)
        tool.agent = agent
        tool.args = {}

        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(niche="test niche", market="global", mode="turbo")
        )
        assert "invalid mode" in result.message.lower()
        assert "turbo" in result.message
        assert result.break_loop is False

    def test_valid_modes_accepted(self):
        from python.tools.venture_discover import VentureDiscover
        for mode in ("fast", "full", "scan_only"):
            agent = MagicMock()
            tool = VentureDiscover.__new__(VentureDiscover)
            tool.agent = agent
            tool.args = {}

            with patch(
                "python.helpers.cortex_discovery_params.VentureDiscoveryParameters"
            ) as MockParams, patch(
                "python.helpers.cortex_discovery_orchestrator.run_discovery",
                new=AsyncMock(return_value=FakeDiscoveryResult())
            ):
                MockParams.load.return_value = MagicMock(target_niches=[])
                result = asyncio.get_event_loop().run_until_complete(
                    tool.execute(niche="test niche", market="global", mode=mode)
                )
            assert "invalid mode" not in result.message.lower(), f"Mode {mode!r} was rejected"


# ── Tests: mode → skip_influencers mapping ─────────────────────────────────────

class TestModeMapping:

    def _run_with_mode_capture(self, mode):
        """Run execute() and capture the skip_influencers arg passed to run_discovery."""
        from python.tools.venture_discover import VentureDiscover
        agent = MagicMock()
        tool = VentureDiscover.__new__(VentureDiscover)
        tool.agent = agent
        tool.args = {}

        captured = {}

        async def fake_run_discovery(niche, market, params, agent, skip_influencers, max_cost_eur):
            captured["skip_influencers"] = skip_influencers
            return FakeDiscoveryResult()

        # Lazy imports inside execute() — patch at source modules
        with patch(
            "python.helpers.cortex_discovery_params.VentureDiscoveryParameters"
        ) as MockParams, patch(
            "python.helpers.cortex_discovery_orchestrator.run_discovery",
            side_effect=fake_run_discovery
        ):
            MockParams.load.return_value = MagicMock(target_niches=[])
            asyncio.get_event_loop().run_until_complete(
                tool.execute(niche="test niche", market="global", mode=mode)
            )
        return captured.get("skip_influencers")

    def test_mode_full_sets_skip_influencers_false(self):
        assert self._run_with_mode_capture("full") is False

    def test_mode_fast_sets_skip_influencers_true(self):
        assert self._run_with_mode_capture("fast") is True

    def test_mode_scan_only_sets_skip_influencers_true(self):
        assert self._run_with_mode_capture("scan_only") is True


# ── Tests: _format_result ──────────────────────────────────────────────────────

class TestFormatResult:

    def _format(self, **kwargs):
        from python.tools.venture_discover import _format_result
        result = FakeDiscoveryResult(**kwargs)
        return _format_result(result)

    def test_format_contains_niche(self):
        text = self._format(niche="My niche", outcome="queued")
        assert "My niche" in text

    def test_format_contains_outcome_uppercase(self):
        text = self._format(outcome="queued")
        assert "QUEUED" in text

    def test_format_contains_cvs_score(self):
        text = self._format(final_score=72.5)
        assert "72.5" in text

    def test_format_no_score_when_none(self):
        text = self._format(final_score=None)
        assert "CVS Score" not in text

    def test_format_contains_strategy_type(self):
        text = self._format(strategy_type="Fast Follower")
        assert "Fast Follower" in text

    def test_format_contains_pain_summary(self):
        text = self._format(pain_summary="People hate slow exports")
        assert "People hate slow exports" in text

    def test_format_contains_disruption_summary(self):
        text = self._format(disruption_summary="Tool X is vulnerable")
        assert "Tool X is vulnerable" in text

    def test_format_shows_candidate_id(self):
        candidate = MagicMock()
        candidate.id = "cand-abc123"
        text = self._format(candidate=candidate)
        assert "cand-abc123" in text

    def test_format_no_candidate_section_when_none(self):
        text = self._format(candidate=None)
        assert "Candidate ID" not in text

    def test_format_shows_cost_estimate(self):
        text = self._format(cost_estimate_eur=0.0253)
        assert "EUR" in text

    def test_format_shows_errors_when_present(self):
        text = self._format(errors=["Exa timeout", "Rate limit hit"])
        assert "Exa timeout" in text

    def test_format_no_warnings_section_when_empty_errors(self):
        text = self._format(errors=[])
        assert "Warnings" not in text

    def test_format_queued_outcome(self):
        text = self._format(outcome="queued", reason="CVS 68 above threshold")
        assert "QUEUED" in text
        assert "CVS 68" in text

    def test_format_rejected_outcome(self):
        text = self._format(outcome="rejected", reason="Score too low")
        assert "REJECTED" in text

    def test_format_parked_outcome(self):
        text = self._format(outcome="parked", reason="Gate 0 block")
        assert "PARKED" in text

    def test_format_error_outcome(self):
        text = self._format(outcome="error", reason="Orchestrator crash")
        assert "ERROR" in text

    def test_format_shows_steps_completed(self):
        text = self._format(steps_completed=["gate_0", "signal_ingestion", "gate_1"])
        assert "gate_0" in text

    def test_format_shows_skipped_steps(self):
        text = self._format(steps_skipped=["influencers"])
        assert "influencers" in text

    def test_format_none_skipped_shows_none(self):
        text = self._format(steps_skipped=[])
        assert "none" in text.lower()

    def test_format_signals_count(self):
        signals = [MagicMock() for _ in range(17)]
        text = self._format(signals=signals)
        assert "17" in text

    def test_format_pain_clusters_count(self):
        clusters = [MagicMock() for _ in range(4)]
        text = self._format(clusters=clusters)
        assert "4" in text


# ── Tests: exception handling ──────────────────────────────────────────────────

class TestExceptionHandling:

    def test_run_discovery_exception_returns_error_message(self):
        from python.tools.venture_discover import VentureDiscover
        agent = MagicMock()
        tool = VentureDiscover.__new__(VentureDiscover)
        tool.agent = agent
        tool.args = {}

        with patch(
            "python.helpers.cortex_discovery_params.VentureDiscoveryParameters"
        ) as MockParams, patch(
            "python.helpers.cortex_discovery_orchestrator.run_discovery",
            new=AsyncMock(side_effect=RuntimeError("orchestrator exploded"))
        ):
            MockParams.load.return_value = MagicMock(target_niches=[])
            result = asyncio.get_event_loop().run_until_complete(
                tool.execute(niche="test niche", market="global", mode="fast")
            )

        assert "failed" in result.message.lower() or "orchestrator exploded" in result.message
        assert result.break_loop is False


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
