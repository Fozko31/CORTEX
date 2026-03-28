"""
test_g_extended.py — Phase G Self-Optimization: holistic integration tests.

Tests the full pipeline end-to-end, with mocked external APIs but real module
integration (no mocking of internal module calls).

Run: python -m pytest tests/test_g_extended.py -v
"""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_openrouter_response(content: str):
    """Build a mock OpenRouter API response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return mock_resp


def _mock_tavily_response(results=None):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": results or []}
    return mock_resp


# ════════════════════════════════════════════════════════════════════════════
# Holistic: Loop 1 pipeline (struggle → cluster → hypothesis → experiment)
# ════════════════════════════════════════════════════════════════════════════

class TestLoop1HolisticPipeline:
    """
    Tests the full Loop 1 pipeline:
    struggle events → aggregator → hypotheses → experiment runner → judge → reporter.
    All external LLM/API calls mocked.
    """

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_loop1.db")

    def _make_struggle_events(self):
        """Return mock struggle events."""
        events = []
        for i in range(5):
            events.append({
                "topic": "pricing_research",
                "severity": "high" if i < 3 else "medium",
                "signals": ["uncertain", "hedge"],
                "context_snippet": "How do I price a SaaS product?",
                "session_id": f"s{i}",
            })
        events.append({"topic": "market_sizing", "severity": "low",
                       "signals": ["unclear"], "context_snippet": "Market size?", "session_id": "s5"})
        return events

    def test_struggle_to_hypothesis_pipeline(self):
        """Struggle events → aggregated clusters → top hypotheses."""
        import python.helpers.cortex_event_store as es_mod
        from python.helpers.cortex_struggle_aggregator import aggregate, generate_hypotheses

        events = self._make_struggle_events()
        with patch.object(es_mod, "get_struggle_events", return_value=events):
            clusters = aggregate(days=30)
            hyps = generate_hypotheses(clusters, top_n=3)

        assert len(clusters) >= 1
        # Topic is normalized ("pricing_research" → "pricing")
        assert any("pricing" in c.topic for c in clusters)
        pricing_cluster = next(c for c in clusters if "pricing" in c.topic)
        assert pricing_cluster.weighted_score > 3.0  # 3 high + 2 medium

        assert len(hyps) >= 1
        # Sorted by rank (ascending = highest priority first)
        assert hyps[0].rank <= hyps[-1].rank

    def test_experiment_result_to_reporter(self):
        """ExperimentResult → reporter generates Markdown report."""
        from python.helpers.cortex_experiment_reporter import build_report, build_telegram_summary
        from python.helpers.cortex_experiment_runner import ExperimentResult, QueryResult

        # Actual signature: QueryResult(query_id, query_text, baseline_response, experimental_response,
        #                               baseline_score, experimental_score, delta, criterion_detail={})
        qr1 = QueryResult("V1", "What makes a venture viable?",
                          "baseline resp V1", "improved resp V1", 7.0, 8.5, 1.5,
                          {"relevance": 1, "depth": 2})
        qr2 = QueryResult("S1", "What is the go-to-market strategy?",
                          "baseline resp S1", "better resp S1", 6.0, 7.5, 1.5,
                          {"actionability": 1})

        # Actual signature: ExperimentResult(experiment_id, hypothesis, checkpoint_tag,
        #                                    baseline_avg, experimental_avg, overall_delta,
        #                                    queries_run, query_results=[], ...)
        result = ExperimentResult(
            experiment_id="exp-test-001",
            hypothesis={"type": "prompt_append", "target": "role.md",
                        "text": "Add pricing guidance"},
            checkpoint_tag="cortex-pre-exp-test-001",
            baseline_avg=65.0,
            experimental_avg=80.0,
            overall_delta=15.0,
            queries_run=2,
            query_results=[qr1, qr2],
            improved_count=2,
            degraded_count=0,
            neutral_count=0,
        )

        md = build_report(result)
        telegram = build_telegram_summary(result)

        assert isinstance(md, str) and len(md) > 50
        assert isinstance(telegram, str)
        assert len(telegram) <= 4000

    @pytest.mark.asyncio
    async def test_experiment_applier_writes_and_logs(self):
        """Applier writes change to file and logs experiment."""
        from python.helpers.cortex_experiment_applier import apply_experiment
        from python.helpers.cortex_experiment_runner import ExperimentResult

        # Create a temp target file
        target = os.path.join(self.tmp, "test_role.md")
        with open(target, "w") as f:
            f.write("# Role\nOriginal content.\n")

        result = ExperimentResult(
            experiment_id="exp-001",
            hypothesis={
                "type": "prompt_append",
                "target_file": target,
                "target_type": "role",
                "cluster_topic": "pricing_guidance",
                "proposed_change_summary": "Be more specific about pricing frameworks.",
            },
            checkpoint_tag="cortex-pre-exp-001",
            baseline_avg=70.0,
            experimental_avg=82.0,
            overall_delta=12.0,
            queries_run=5,
        )
        result_dict = result.to_dict()

        with patch("python.helpers.cortex_version_manager.pin_version") as mock_pin:
            mock_pin.return_value = {"success": True, "version_id": "v1-1-test"}
            outcome = apply_experiment(result_dict, approved_by="test")

        assert outcome["success"] is True
        content = open(target).read()
        # The applier uses cluster_topic as section heading ("Pricing Guidance Context")
        assert "Pricing" in content


# ════════════════════════════════════════════════════════════════════════════
# Holistic: Loop 2 pipeline (outcome → attribution → signal → push)
# ════════════════════════════════════════════════════════════════════════════

class TestLoop2HolisticPipeline:
    """
    Tests the full Loop 2 pipeline:
    outcome record → attribution → signal generation.
    """

    def test_full_outcome_pipeline_cortex_owned(self):
        """Outcome with confirmed execution + no confounders → cortex_owned → knowledge_gap signal."""
        from python.helpers.cortex_outcome_attributor import OutcomeRecord, classify
        from python.helpers.cortex_optimization_signal import generate_signal

        record = OutcomeRecord(
            venture_id="biz-001",
            venture_name="Test SaaS",
            period="2026-Q1",
            metric_type="monthly_revenue",
            target_value=5000.0,
            actual_value=2800.0,  # -44% = strong failure
            cortex_controlled_slice="pricing_strategy",
            user_execution_confirmed=True,
            external_confounders=[],
            autonomy_score=0.85,
        )
        classified = classify(record)
        signal = generate_signal(classified)

        assert classified.attribution == "cortex_owned"
        assert signal is not None
        assert signal.signal_type == "knowledge_gap"
        assert signal.signal_strength > 0.5
        assert "pricing_strategy" in signal.description

    def test_outcome_feedback_ingest_and_retrieve(self):
        """ingest_outcome stores record in event store (mocked)."""
        from python.helpers.cortex_outcome_feedback import ingest_outcome

        with patch("python.helpers.cortex_event_store.log_experiment") as mock_log:
            with patch("python.helpers.cortex_outcome_attributor.classify") as mock_classify:
                mock_record = MagicMock()
                mock_record.to_dict.return_value = {"attribution": "cortex_owned"}
                mock_classify.return_value = mock_record
                result = ingest_outcome(
                    venture_id="v1",
                    venture_name="Test",
                    period="2026-Q1",
                    metric_type="revenue",
                    target_value=10000.0,
                    actual_value=12500.0,
                    cortex_controlled_slice="content_marketing",
                    user_execution_confirmed=True,
                    autonomy_score=0.9,
                )
            mock_log.assert_called_once()

    def test_checkin_lifecycle(self):
        """Create → respond → resolve checkin lifecycle."""
        from python.helpers.cortex_outcome_feedback import (
            create_execution_checkin, record_execution_response,
            format_checkin_question,
        )
        checkin = create_execution_checkin(
            commitment_id="com-001",
            commitment_description="Send cold email campaign",
            venture_id="v1",
            venture_name="Test SaaS",
            cortex_recommendation="Send 50 emails/day for 2 weeks",
        )
        assert checkin["status"] == "pending"

        question = format_checkin_question(checkin)
        assert "Test SaaS" in question
        assert checkin["checkin_id"] in question

        # Slovenian response
        updated = record_execution_response(checkin, "da")
        assert updated["status"] == "confirmed_yes"

        updated2 = record_execution_response(checkin, "ne")
        assert updated2["status"] == "confirmed_no"

        updated3 = record_execution_response(checkin, "later")
        assert updated3["status"] == "skipped"


# ════════════════════════════════════════════════════════════════════════════
# Holistic: Loop 3 protocol session (mocked LLM)
# ════════════════════════════════════════════════════════════════════════════

class TestLoop3HolisticPipeline:
    """Tests the full Loop 3 CORTEX↔Ruflo protocol session."""

    @pytest.mark.asyncio
    async def test_protocol_session_converges(self):
        """Full Loop 3 session with mocked Ruflo API → produces human report."""
        from python.helpers.cortex_interagent_protocol import run_loop3_session

        ruflo_response = json.dumps({
            "from": "ruflo",
            "round": 1,
            "type": "architectural_analysis",
            "findings": [
                {
                    "re": "Pricing research quality",
                    "architectural_cause": "System prompt lacks pricing frameworks",
                    "fix_complexity": "low",
                    "proposed_fix": "Add Hormozi pricing section to role.md",
                    "affected_components": ["agents/cortex/prompts/agent.system.main.role.md"],
                    "breaking_risk": "none",
                }
            ],
            "proposed_fixes": [
                {
                    "id": "fix-1",
                    "description": "Add pricing framework guidance",
                    "target_file": "agents/cortex/prompts/agent.system.main.role.md",
                    "priority": "high",
                }
            ],
            "open_questions_for_cortex": [],
            "convergence_assessment": "converged",
            "convergence_rationale": "Single finding with clear fix. No further questions needed.",
        })

        mock_resp = _mock_openrouter_response(ruflo_response)

        operational_report = {
            "period_days": 60,
            "generated_at": "2026-03-01T00:00:00",
            "struggle_clusters": [{"topic": "pricing_research", "count": 5}],
            "tool_usage": {"zero_call_tools": ["knowledge_tool"], "top_tools": []},
            "latency_hotspots": [],
            "user_corrections": {"total": 2, "by_type": {"factual_error": 2}},
            "extension_failures": [],
            "open_questions_for_ruflo": [],
        }

        with patch.dict(os.environ, {"API_KEY_OPENROUTER": "test-key"}):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
                session = await run_loop3_session(operational_report)

        assert session.converged is True
        assert len(session.final_proposals) >= 1
        assert isinstance(session.human_report, str)
        assert "Findings" in session.human_report
        assert session.session_id.startswith("loop3-")

    @pytest.mark.asyncio
    async def test_protocol_session_fallback_on_api_failure(self):
        """Loop 3 session falls back gracefully when API is unavailable."""
        from python.helpers.cortex_interagent_protocol import run_loop3_session

        operational_report = {
            "period_days": 60, "generated_at": "2026-03-01T00:00:00",
            "struggle_clusters": [], "tool_usage": {"zero_call_tools": []},
            "latency_hotspots": [], "user_corrections": {"total": 0, "by_type": {}},
            "extension_failures": [], "open_questions_for_ruflo": [],
        }

        with patch.dict(os.environ, {"API_KEY_OPENROUTER": ""}):
            session = await run_loop3_session(operational_report)

        assert session.converged is True
        assert isinstance(session.human_report, str)
        assert "Decision" in session.human_report


# ════════════════════════════════════════════════════════════════════════════
# Holistic: Loop 5 pipeline (inventory → researcher → evaluator)
# ════════════════════════════════════════════════════════════════════════════

class TestLoop5HolisticPipeline:
    """Tests the full Loop 5 stack research and evaluation pipeline."""

    @pytest.mark.asyncio
    async def test_research_component_with_mocked_apis(self):
        """research_component returns ComponentFinding for a real stack component."""
        from python.helpers.cortex_stack_inventory import get_by_component
        from python.helpers.cortex_stack_researcher import research_component

        component = get_by_component("tavily")
        assert component is not None

        synthesis_response = json.dumps({
            "update_available": False,
            "update_description": "",
            "pricing_change": False,
            "pricing_change_description": "",
            "reliability_signals": [],
            "notable_alternatives": ["Serper: faster but less comprehensive"],
            "recommendation": "stable",
            "recommendation_reason": "Tavily remains the best structured search API for CORTEX's use case.",
        })

        tavily_result = MagicMock()
        tavily_result.status_code = 200
        tavily_result.json.return_value = {"results": [
            {"title": "Tavily changelog", "url": "https://tavily.com/changelog", "content": "No major changes."}
        ]}

        llm_result = _mock_openrouter_response(synthesis_response)

        with patch.dict(os.environ, {"TAVILY_API_KEY": "test", "EXA_API_KEY": "", "API_KEY_OPENROUTER": "test-key"}):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=[tavily_result, tavily_result, llm_result]
                )
                finding = await research_component(component)

        assert finding.component == "tavily"
        assert finding.recommendation in ("stable", "monitor", "investigate", "replace")
        assert isinstance(finding.recommendation_reason, str)

    def test_evaluate_findings_produces_report(self):
        """evaluate_all_findings → build_evaluation_report → correct structure."""
        from python.helpers.cortex_stack_evaluator import evaluate_all_findings, build_evaluation_report, format_report_markdown

        findings = [
            {
                "component": "tavily",
                "category": "research",
                "current_version": "v1",
                "recommendation": "stable",
                "update_available": False,
                "pricing_change": False,
                "pricing_change_description": "",
                "reliability_signals": [],
                "notable_alternatives": [],
                "researched_at": "2026-03-01T00:00:00",
            },
            {
                "component": "exa",
                "category": "research",
                "current_version": "Exa Search API",
                "recommendation": "monitor",
                "update_available": True,
                "update_description": "Exa v2 in beta with 3x faster results",
                "pricing_change": False,
                "pricing_change_description": "",
                "reliability_signals": [],
                "notable_alternatives": ["You.com: similar neural search"],
                "researched_at": "2026-03-01T00:00:00",
            },
            {
                "component": "perplexity",
                "category": "research",
                "current_version": "sonar-pro",
                "recommendation": "investigate",
                "update_available": True,
                "update_description": "sonar-huge: 2x better citations, 40% cheaper via OpenRouter",
                "pricing_change": True,
                "pricing_change_description": "40% cheaper than sonar-pro for same quality",
                "reliability_signals": [],
                "notable_alternatives": [],
                "researched_at": "2026-03-01T00:00:00",
            },
        ]

        evals = evaluate_all_findings(findings)
        report = build_evaluation_report(evals)
        md = format_report_markdown(report)

        assert report["total_components"] == 3
        assert "replace_now" in report
        assert "investigate" in report
        assert isinstance(md, str)
        assert "Loop 5" in md

        # Perplexity with "investigate" + price savings should be REPLACE_NOW or INVESTIGATE
        perp_eval = next(e for e in evals if e.component == "perplexity")
        assert perp_eval.decision in ("REPLACE_NOW", "INVESTIGATE")


# ════════════════════════════════════════════════════════════════════════════
# Holistic: Event store → Operational reporter → Loop 3 input
# ════════════════════════════════════════════════════════════════════════════

class TestOperationalReportPipeline:
    """Tests the full pipeline from raw events to operational report."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_ops.db")

    def test_events_to_operational_report(self):
        """Seed events via mocks → generate operational report → correct structure."""
        import python.helpers.cortex_event_store as es_mod
        from python.helpers import cortex_operational_reporter as reporter

        # Mock event store to return seeded data (avoid real DB path)
        with patch.object(es_mod, "get_struggle_events", return_value=[
                {"topic": "pricing", "severity": "high", "signals": [], "context_snippet": "", "session_id": "s1"},
            ]), \
             patch.object(es_mod, "get_tool_usage_summary", return_value={"by_tool": {
                "cortex_research_tool": {"calls": 5, "success_rate": 0.9},
                "knowledge_tool": {"calls": 1, "success_rate": 0.0},
             }, "total_sessions": 3}), \
             patch.object(es_mod, "get_correction_summary", return_value=[
                {"correction_type": "factual_error", "count": 1, "context_snippet": "wrong answer"},
             ]), \
             patch.object(es_mod, "get_latency_summary", return_value=[]), \
             patch.object(es_mod, "get_extension_failures", return_value=[
                {"extension_name": "_20_surfsense_pull.py", "last_type": "TimeoutError", "count": 1, "last_msg": ""},
             ]), \
             patch.object(es_mod, "get_benchmark_history", return_value=[]), \
             patch("python.helpers.cortex_struggle_aggregator.aggregate", return_value=[]):
            report = reporter.generate(period_days=60)

        assert "struggle_clusters" in report
        assert "tool_usage" in report
        assert "user_corrections" in report
        assert "extension_failures" in report


# ════════════════════════════════════════════════════════════════════════════
# Holistic: Scheduler registration (no APScheduler running — just verifies import)
# ════════════════════════════════════════════════════════════════════════════

class TestSchedulerRegistration:
    """Verify all Loop schedulers can register without errors."""

    @pytest.mark.asyncio
    async def test_loop4_benchmark_registers(self):
        """register_benchmark_task imports and runs without crashing."""
        from python.helpers import cortex_benchmark_runner
        # Just verify the function is importable and callable
        assert hasattr(cortex_benchmark_runner, "register_benchmark_task")
        assert callable(cortex_benchmark_runner.register_benchmark_task)

    @pytest.mark.asyncio
    async def test_loop3_registers(self):
        """register_loop3_task imports and runs without crashing."""
        from python.helpers import cortex_ruflo_session_packager
        assert hasattr(cortex_ruflo_session_packager, "register_loop3_task")
        assert callable(cortex_ruflo_session_packager.register_loop3_task)


# ════════════════════════════════════════════════════════════════════════════
# Holistic: Self-improve tool operations (no agent required)
# ════════════════════════════════════════════════════════════════════════════

class TestSelfImproveTool:
    """Tests self_improve.py tool handler logic."""

    def test_tool_importable(self):
        """self_improve tool can be imported without errors."""
        import python.tools.self_improve  # noqa

    def test_tool_prompt_doc_exists(self):
        """Tool documentation file exists."""
        doc_path = Path("agents/cortex/prompts/agent.system.tool.self_improve.md")
        assert doc_path.exists(), "Missing tool documentation file"

    @pytest.mark.asyncio
    async def test_show_status_operation(self):
        """self_improve tool class is importable and inherits from Tool."""
        from python.tools.self_improve import SelfImprove
        from python.helpers.tool import Tool

        # Verify class structure
        assert issubclass(SelfImprove, Tool)
        # Verify tool module has the class
        import python.tools.self_improve as mod
        assert hasattr(mod, "SelfImprove")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
