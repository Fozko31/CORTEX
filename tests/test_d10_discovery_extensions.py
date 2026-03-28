"""
Tests for D-10: Discovery Extensions
  - python/extensions/system_prompt/_10_discovery_context.py
  - python/helpers/cortex_discovery_scheduler.py

Both modules use lazy imports inside their functions (from X import Y inside execute/run_*).
All patches target the SOURCE module attributes (python.helpers.cortex_discovery_params.*,
python.helpers.cortex_discovery_orchestrator.run_discovery) so they intercept the import
at lookup time.

Covers:
  Context extension:
    - Non-cortex profile → skip
    - Empty queue/parked/accepted → minimal hint
    - Queue with items → top candidate formatted
    - Parked items → parked count shown
    - Accepted items → accepted count shown
    - Target niches → first 3 shown with ellipsis if >3
    - Exception → silently swallowed (never crashes)

  Scheduler:
    - run_discovery_loop with no target niches → early exit, no calls
    - run_discovery_loop with niches → calls run_discovery per niche
    - run_discovery_loop respects max_niches cap
    - run_discovery_loop handles per-niche exceptions gracefully
    - register_discovery_task without env var → does nothing
    - register_discovery_task module-level guard (_registered) prevents double-register

No API calls.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_agent(profile="cortex"):
    agent = MagicMock()
    agent.config = MagicMock()
    agent.config.profile = profile
    return agent


def make_candidate(niche="test niche", market="EU", score=72.0, strategy="Niche Domination",
                   candidate_id="cand-001"):
    c = MagicMock()
    c.niche = niche
    c.market = market
    c.cvs_prescore = score
    c.strategy_type = strategy
    c.id = candidate_id
    return c


# ── Context Extension Tests ────────────────────────────────────────────────────

class TestDiscoveryContextExtension:
    """
    Extension uses lazy imports inside execute():
        from python.helpers.cortex_discovery_params import load_queue, ...
    Patch targets must be on the source module: python.helpers.cortex_discovery_params.*
    """

    _PARAMS_MOD = "python.helpers.cortex_discovery_params"

    def _run_extension(self, agent, queue=None, parked=None, accepted=None,
                       params=None, system_prompt=None):
        """Run extension with mocked storage functions."""
        from python.extensions.system_prompt._10_discovery_context import CortexDiscoveryContext

        ext = CortexDiscoveryContext.__new__(CortexDiscoveryContext)
        ext.agent = agent
        sp = system_prompt if system_prompt is not None else []

        mock_params = params if params is not None else MagicMock(target_niches=[])

        with patch(f"{self._PARAMS_MOD}.load_queue", return_value=queue or []), \
             patch(f"{self._PARAMS_MOD}.load_parked", return_value=parked or []), \
             patch(f"{self._PARAMS_MOD}.load_accepted", return_value=accepted or []), \
             patch(f"{self._PARAMS_MOD}.VentureDiscoveryParameters") as MockParams:
            MockParams.load.return_value = mock_params
            asyncio.get_event_loop().run_until_complete(
                ext.execute(system_prompt=sp)
            )
        return sp

    # -- profile gate

    def test_non_cortex_profile_skips_injection(self):
        agent = make_agent(profile="default")
        sp = self._run_extension(agent)
        assert sp == []

    def test_cortex_profile_injects(self):
        agent = make_agent(profile="cortex")
        sp = self._run_extension(agent)
        assert len(sp) > 0

    def test_cortex_subprofile_injects(self):
        # Profile names like "cortex_v2" should also trigger (startswith check)
        agent = make_agent(profile="cortex_v2")
        sp = self._run_extension(agent)
        assert len(sp) > 0

    # -- empty pipeline

    def test_empty_pipeline_injects_minimal_hint(self):
        agent = make_agent()
        sp = self._run_extension(agent, queue=[], parked=[], accepted=[])
        assert any("venture_discover" in block for block in sp)
        assert any("No ventures in queue" in block for block in sp)

    # -- queue populated

    def test_queue_shows_top_candidate(self):
        candidate = make_candidate(niche="AI bookkeeping", score=75.0)
        sp = self._run_extension(make_agent(), queue=[candidate])
        text = "\n".join(sp)
        assert "AI bookkeeping" in text

    def test_queue_shows_score(self):
        candidate = make_candidate(score=65.0)
        sp = self._run_extension(make_agent(), queue=[candidate])
        text = "\n".join(sp)
        assert "65" in text

    def test_queue_shows_strategy(self):
        candidate = make_candidate(strategy="Fast Follower")
        sp = self._run_extension(make_agent(), queue=[candidate])
        text = "\n".join(sp)
        assert "Fast Follower" in text

    def test_queue_shows_candidate_id(self):
        candidate = make_candidate(candidate_id="cand-xyz")
        sp = self._run_extension(make_agent(), queue=[candidate])
        text = "\n".join(sp)
        assert "cand-xyz" in text

    def test_queue_shows_count(self):
        candidates = [make_candidate(niche=f"niche {i}") for i in range(5)]
        sp = self._run_extension(make_agent(), queue=candidates)
        text = "\n".join(sp)
        assert "5" in text

    def test_empty_queue_shows_empty(self):
        parked = [MagicMock()]  # non-empty so injection fires
        sp = self._run_extension(make_agent(), queue=[], parked=parked)
        text = "\n".join(sp)
        assert "Empty" in text

    # -- parked

    def test_parked_shows_count(self):
        parked = [MagicMock(), MagicMock(), MagicMock()]
        candidate = make_candidate()
        sp = self._run_extension(make_agent(), queue=[candidate], parked=parked)
        text = "\n".join(sp)
        assert "3" in text
        assert "Parked" in text or "parked" in text

    # -- accepted

    def test_accepted_shows_count(self):
        accepted = [MagicMock(), MagicMock()]
        candidate = make_candidate()
        sp = self._run_extension(make_agent(), queue=[candidate], accepted=accepted)
        text = "\n".join(sp)
        assert "2" in text
        assert "Accepted" in text or "accepted" in text

    # -- target niches

    def test_target_niches_first_three_shown(self):
        params = MagicMock()
        params.target_niches = ["Niche A", "Niche B", "Niche C", "Niche D"]
        candidate = make_candidate()
        sp = self._run_extension(make_agent(), queue=[candidate], params=params)
        text = "\n".join(sp)
        assert "Niche A" in text
        assert "Niche B" in text
        assert "Niche C" in text

    def test_target_niches_ellipsis_when_more_than_three(self):
        params = MagicMock()
        params.target_niches = ["A", "B", "C", "D", "E"]
        candidate = make_candidate()
        sp = self._run_extension(make_agent(), queue=[candidate], params=params)
        text = "\n".join(sp)
        assert "…" in text

    def test_target_niches_no_ellipsis_when_three_or_fewer(self):
        params = MagicMock()
        params.target_niches = ["A", "B"]
        candidate = make_candidate()
        sp = self._run_extension(make_agent(), queue=[candidate], params=params)
        text = "\n".join(sp)
        assert "…" not in text

    def test_no_target_niches_section_when_empty(self):
        params = MagicMock()
        params.target_niches = []
        candidate = make_candidate()
        sp = self._run_extension(make_agent(), queue=[candidate], params=params)
        text = "\n".join(sp)
        assert "Active targets" not in text

    # -- exception resilience

    def test_load_queue_exception_swallowed(self):
        """Extension must never crash system prompt construction."""
        from python.extensions.system_prompt._10_discovery_context import CortexDiscoveryContext

        ext = CortexDiscoveryContext.__new__(CortexDiscoveryContext)
        ext.agent = make_agent()
        sp = []

        with patch(f"{self._PARAMS_MOD}.load_queue",
                   side_effect=RuntimeError("disk error")):
            # Should not raise — extension swallows all exceptions
            asyncio.get_event_loop().run_until_complete(ext.execute(system_prompt=sp))

    def test_params_load_exception_swallowed(self):
        """Params load failure → niche targets silently skipped."""
        from python.extensions.system_prompt._10_discovery_context import CortexDiscoveryContext

        ext = CortexDiscoveryContext.__new__(CortexDiscoveryContext)
        ext.agent = make_agent()
        sp = []
        candidate = make_candidate()

        with patch(f"{self._PARAMS_MOD}.load_queue", return_value=[candidate]), \
             patch(f"{self._PARAMS_MOD}.load_parked", return_value=[]), \
             patch(f"{self._PARAMS_MOD}.load_accepted", return_value=[]), \
             patch(f"{self._PARAMS_MOD}.VentureDiscoveryParameters") as MockParams:
            MockParams.load.side_effect = RuntimeError("params file corrupt")
            asyncio.get_event_loop().run_until_complete(ext.execute(system_prompt=sp))

        # Extension ran, sp may contain queue info but no target niches
        text = "\n".join(sp)
        assert "Active targets" not in text


# ── Scheduler Tests ────────────────────────────────────────────────────────────

class TestDiscoveryScheduler:
    """
    Scheduler uses lazy imports inside run_discovery_loop():
        from python.helpers.cortex_discovery_params import VentureDiscoveryParameters
        from python.helpers.cortex_discovery_orchestrator import run_discovery
    Patch targets: source module attributes.
    """

    _PARAMS_MOD = "python.helpers.cortex_discovery_params"
    _ORCH_MOD = "python.helpers.cortex_discovery_orchestrator"

    def _make_fake_result(self, outcome="queued", score=65.0):
        r = MagicMock()
        r.outcome = outcome
        r.final_score = score
        return r

    def _make_params(self, niches, geography="global"):
        p = MagicMock()
        p.target_niches = niches
        p.geography = geography
        return p

    def test_run_discovery_loop_no_niches_exits_early(self):
        """If target_niches is empty, loop exits immediately without calling run_discovery."""
        import python.helpers.cortex_discovery_scheduler as sched

        mock_run = AsyncMock()

        with patch(f"{self._PARAMS_MOD}.VentureDiscoveryParameters") as MockParams, \
             patch(f"{self._ORCH_MOD}.run_discovery", mock_run):
            MockParams.load.return_value = self._make_params([])
            asyncio.get_event_loop().run_until_complete(
                sched.run_discovery_loop(agent=None)
            )

        mock_run.assert_not_called()

    def test_run_discovery_loop_calls_run_discovery_per_niche(self):
        """run_discovery called once per niche in target_niches."""
        import python.helpers.cortex_discovery_scheduler as sched

        mock_run = AsyncMock(return_value=self._make_fake_result())

        with patch(f"{self._PARAMS_MOD}.VentureDiscoveryParameters") as MockParams, \
             patch(f"{self._ORCH_MOD}.run_discovery", mock_run):
            MockParams.load.return_value = self._make_params(["A", "B", "C"])
            asyncio.get_event_loop().run_until_complete(
                sched.run_discovery_loop(agent=None, max_niches=10)
            )

        assert mock_run.call_count == 3

    def test_run_discovery_loop_respects_max_niches(self):
        """Only first max_niches niches are processed."""
        import python.helpers.cortex_discovery_scheduler as sched

        mock_run = AsyncMock(return_value=self._make_fake_result("rejected", 30.0))

        with patch(f"{self._PARAMS_MOD}.VentureDiscoveryParameters") as MockParams, \
             patch(f"{self._ORCH_MOD}.run_discovery", mock_run):
            MockParams.load.return_value = self._make_params(["A", "B", "C", "D", "E"])
            asyncio.get_event_loop().run_until_complete(
                sched.run_discovery_loop(agent=None, max_niches=3)
            )

        assert mock_run.call_count == 3

    def test_run_discovery_loop_uses_fast_mode(self):
        """Autonomous loop always runs with skip_influencers=True (fast mode)."""
        import python.helpers.cortex_discovery_scheduler as sched

        mock_run = AsyncMock(return_value=self._make_fake_result())

        with patch(f"{self._PARAMS_MOD}.VentureDiscoveryParameters") as MockParams, \
             patch(f"{self._ORCH_MOD}.run_discovery", mock_run):
            MockParams.load.return_value = self._make_params(["Test Niche"])
            asyncio.get_event_loop().run_until_complete(
                sched.run_discovery_loop(agent=None)
            )

        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("skip_influencers") is True

    def test_run_discovery_loop_per_niche_exception_handled(self):
        """Exception in one niche run should not stop the remaining niches."""
        import python.helpers.cortex_discovery_scheduler as sched

        call_count = 0

        async def fake_run(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("API timeout on Niche B")
            return self._make_fake_result()

        with patch(f"{self._PARAMS_MOD}.VentureDiscoveryParameters") as MockParams, \
             patch(f"{self._ORCH_MOD}.run_discovery", side_effect=fake_run):
            MockParams.load.return_value = self._make_params(["A", "B", "C"])
            # Should not raise
            asyncio.get_event_loop().run_until_complete(
                sched.run_discovery_loop(agent=None, max_niches=10)
            )

        assert call_count == 3  # All three attempted despite Niche B failing

    def test_run_discovery_loop_passes_market_from_params(self):
        """Market is read from params.geography, not hardcoded to 'global'."""
        import python.helpers.cortex_discovery_scheduler as sched

        mock_run = AsyncMock(return_value=self._make_fake_result())

        with patch(f"{self._PARAMS_MOD}.VentureDiscoveryParameters") as MockParams, \
             patch(f"{self._ORCH_MOD}.run_discovery", mock_run):
            MockParams.load.return_value = self._make_params(["Test Niche"], geography="Slovenia")
            asyncio.get_event_loop().run_until_complete(
                sched.run_discovery_loop(agent=None)
            )

        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("market") == "Slovenia"

    def test_register_discovery_task_no_env_var_does_nothing(self):
        """Without CORTEX_DISCOVERY_AUTO=1, cron registration is skipped."""
        import python.helpers.cortex_discovery_scheduler as sched

        original = sched._registered
        sched._registered = False

        try:
            env_without_var = {k: v for k, v in os.environ.items()
                               if k != "CORTEX_DISCOVERY_AUTO"}
            with patch.dict(os.environ, env_without_var, clear=True):
                with patch("crontab.CronTab") as MockCron:
                    sched.register_discovery_task()
                    MockCron.assert_not_called()
        finally:
            sched._registered = original

    def test_register_discovery_task_module_guard_prevents_double_register(self):
        """_registered guard: second call to register_discovery_task is a no-op."""
        import python.helpers.cortex_discovery_scheduler as sched

        original = sched._registered
        sched._registered = True  # Simulate already registered

        try:
            with patch.dict(os.environ, {"CORTEX_DISCOVERY_AUTO": "1"}):
                with patch("crontab.CronTab") as MockCron:
                    sched.register_discovery_task()
                    MockCron.assert_not_called()
        finally:
            sched._registered = original

    def test_run_discovery_loop_params_load_failure_uses_defaults(self):
        """If params.load() raises, fall back to empty defaults → no runs."""
        import python.helpers.cortex_discovery_scheduler as sched

        mock_run = AsyncMock()

        with patch(f"{self._PARAMS_MOD}.VentureDiscoveryParameters") as MockParams, \
             patch(f"{self._ORCH_MOD}.run_discovery", mock_run):
            MockParams.load.side_effect = Exception("file not found")
            # VentureDiscoveryParameters() default instance
            MockParams.return_value = MagicMock(target_niches=[], geography="global")

            asyncio.get_event_loop().run_until_complete(
                sched.run_discovery_loop(agent=None)
            )

        mock_run.assert_not_called()  # No niches → no runs

    def test_run_discovery_loop_max_cost_eur_conservative(self):
        """Autonomous loop uses max_cost_eur=0.10 (conservative budget)."""
        import python.helpers.cortex_discovery_scheduler as sched

        mock_run = AsyncMock(return_value=self._make_fake_result())

        with patch(f"{self._PARAMS_MOD}.VentureDiscoveryParameters") as MockParams, \
             patch(f"{self._ORCH_MOD}.run_discovery", mock_run):
            MockParams.load.return_value = self._make_params(["Test Niche"])
            asyncio.get_event_loop().run_until_complete(
                sched.run_discovery_loop(agent=None)
            )

        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("max_cost_eur") == 0.10


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
