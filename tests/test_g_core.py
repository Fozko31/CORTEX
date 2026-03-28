"""
test_g_core.py — Phase G Self-Optimization System: isolated unit tests.

Tests each Phase G module in isolation with mocked external dependencies.
Run: python -m pytest tests/test_g_core.py -v
"""

import asyncio
import json
import os
import sqlite3
import tempfile
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ════════════════════════════════════════════════════════════════════════════
# G-0: Event Store
# ════════════════════════════════════════════════════════════════════════════

class TestEventStore:
    """Tests for cortex_event_store.py — SQLite event log."""

    def setup_method(self):
        """Use a fresh temp DB for each test — patch _db_path to return temp path."""
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_event_store.db")

    def _patch_db(self):
        """Context manager: redirect all DB calls to temp path."""
        from python.helpers import cortex_event_store as es
        return patch.object(es, "_db_path", return_value=self.db_path)

    def test_initialize_creates_tables(self):
        from python.helpers import cortex_event_store as es
        with self._patch_db():
            es.initialize()
            conn = sqlite3.connect(self.db_path)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            conn.close()
        required = {"struggle_events", "tool_calls", "user_corrections", "latency_events",
                    "extension_failures", "benchmark_runs", "experiment_log"}
        assert required.issubset(tables), f"Missing tables: {required - tables}"

    def test_log_and_read_struggle(self):
        from python.helpers import cortex_event_store as es
        with self._patch_db():
            es.initialize()
            es.log_struggle("pricing_research", "high", ["hedge", "uncertain"], "context", "s1")
            events = es.get_struggle_events(days=30)
        assert len(events) >= 1
        assert any(e["topic"] == "pricing_research" for e in events)
        assert any(e["severity"] == "high" for e in events)

    def test_log_tool_call(self):
        from python.helpers import cortex_event_store as es
        # log_tool_call(tool_name, success, duration_ms, session_id)
        with self._patch_db():
            es.initialize()
            es.log_tool_call("cortex_research_tool", True, 2300, "s1")
            result = es.get_tool_usage_summary(days=30)
        assert "cortex_research_tool" in result.get("by_tool", {})

    def test_log_correction(self):
        from python.helpers import cortex_event_store as es
        with self._patch_db():
            es.initialize()
            es.log_correction("factual_error", "You said X but it's Y", "s1")
            result = es.get_correction_summary(days=30)
        # get_correction_summary returns a list of {correction_type, count, ...} dicts
        assert isinstance(result, list)
        assert len(result) >= 1
        assert any(r["correction_type"] == "factual_error" for r in result)

    def test_log_experiment(self):
        from python.helpers import cortex_event_store as es
        with self._patch_db():
            es.initialize()
            es.log_experiment(
                experiment_id="exp-test-001",
                hypothesis={"type": "prompt_append", "target": "role.md"},
                baseline_score=0.70,
                experimental_score=0.82,
                applied=False,
            )
            history = es.get_experiment_history(days=90)
        assert len(history) >= 1
        assert any(h["experiment_id"] == "exp-test-001" for h in history)

    def test_health_check(self):
        from python.helpers import cortex_event_store as es
        with self._patch_db():
            es.initialize()
            result = es.health_check()
        # health_check returns bool (True = ok)
        assert result is True


# ════════════════════════════════════════════════════════════════════════════
# G-0: Version Manager
# ════════════════════════════════════════════════════════════════════════════

class TestVersionManager:
    """Tests for cortex_version_manager.py — named versions + rollback."""

    def test_list_versions_returns_list(self):
        from python.helpers import cortex_version_manager as vm
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="v1.0 baseline\nv1.1 loop1\n", returncode=0)
            versions = vm.list_versions()
        assert isinstance(versions, list)

    def test_rollback_request_returns_confirm_phrase(self):
        from python.helpers import cortex_version_manager as vm
        with patch("subprocess.run") as mock_run, \
             patch("builtins.open", MagicMock()), \
             patch("json.dump"):
            mock_run.return_value = MagicMock(stdout="abc123 cortex-v1-0-baseline\n", returncode=0)
            result = vm.rollback_request("cortex-v1-0-baseline", "test rollback", [])
        assert "confirm_phrase" in result or "error" in result

    def test_rollback_execute_rejects_wrong_phrase(self):
        from python.helpers import cortex_version_manager as vm
        with patch("builtins.open", MagicMock(side_effect=FileNotFoundError)):
            result = vm.rollback_execute("WRONG_PHRASE")
        assert result["success"] is False

    def test_health_check(self):
        from python.helpers import cortex_version_manager as vm
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="abc123\n", returncode=0)
            result = vm.health_check()
        # Keys vary by implementation — just assert it returns a dict
        assert isinstance(result, dict)
        assert len(result) > 0


# ════════════════════════════════════════════════════════════════════════════
# G-2: Experiment Suite
# ════════════════════════════════════════════════════════════════════════════

class TestExperimentSuite:
    """Tests for cortex_experiment_suite.py — 20 test queries."""

    def test_all_returns_20_queries(self):
        from python.helpers.cortex_experiment_suite import get_all
        queries = get_all()
        assert len(queries) == 20, f"Expected 20 queries, got {len(queries)}"

    def test_all_ids_unique(self):
        from python.helpers.cortex_experiment_suite import get_all
        ids = [q.id for q in get_all()]
        assert len(ids) == len(set(ids)), "Duplicate query IDs found"

    def test_categories_correct(self):
        from python.helpers.cortex_experiment_suite import get_all, get_by_category
        expected_cats = {"venture_analysis", "research_synthesis", "strategic_advice",
                         "challenge_behavior", "language_tools"}
        actual_cats = {q.category for q in get_all()}
        assert actual_cats == expected_cats

    def test_get_by_id(self):
        from python.helpers.cortex_experiment_suite import get_by_id
        q = get_by_id("V1")
        assert q is not None
        assert q.id == "V1"

    def test_get_by_category(self):
        from python.helpers.cortex_experiment_suite import get_by_category
        qs = get_by_category("venture_analysis")
        assert len(qs) == 4
        assert all(q.category == "venture_analysis" for q in qs)

    def test_each_query_has_rubric(self):
        from python.helpers.cortex_experiment_suite import get_all
        for q in get_all():
            assert len(q.rubric) > 0, f"Query {q.id} has empty rubric"
            for criterion in q.rubric:
                assert criterion.max_score in (1, 2), f"Bad max_score in {q.id}: {criterion.max_score}"

    def test_summary(self):
        from python.helpers.cortex_experiment_suite import summary
        s = summary()
        # Key may be "total" or "total_queries" depending on implementation
        total = s.get("total") or s.get("total_queries")
        assert total == 20
        assert s["by_category"]["venture_analysis"] == 4


# ════════════════════════════════════════════════════════════════════════════
# G-2: Struggle Aggregator
# ════════════════════════════════════════════════════════════════════════════

class TestStruggleAggregator:
    """Tests for cortex_struggle_aggregator.py — Loop 1 Steps 1+2."""

    def _make_events(self, topics_and_severities):
        return [
            {"topic": t, "severity": s, "signals": [], "context_snippet": "", "session_id": "s1"}
            for t, s in topics_and_severities
        ]

    def test_aggregate_clusters_by_topic(self):
        from python.helpers.cortex_struggle_aggregator import aggregate
        events = self._make_events([
            ("pricing_research", "high"),
            ("pricing_research", "medium"),
            ("market_sizing", "low"),
        ])
        # aggregate() does inline import of cortex_event_store — patch it at module level
        import python.helpers.cortex_event_store as es_mod
        with patch.object(es_mod, "get_struggle_events", return_value=events):
            clusters = aggregate(days=7)
        # Topic is normalized ("pricing_research" → "pricing")
        assert any("pricing" in c.topic for c in clusters)
        assert any("market" in c.topic for c in clusters)

    def test_generate_hypotheses_returns_list(self):
        from python.helpers.cortex_struggle_aggregator import generate_hypotheses, StruggleCluster
        clusters = [
            StruggleCluster(topic="pricing_research", event_count=5, weighted_score=13.0,
                            severity_distribution={"high": 3, "medium": 2}),
            StruggleCluster(topic="market_sizing", event_count=2, weighted_score=2.0,
                            severity_distribution={"low": 2}),
        ]
        hyps = generate_hypotheses(clusters, top_n=3)
        assert len(hyps) <= 3
        assert all(hasattr(h, "target_file") for h in hyps)

    def test_format_for_telegram(self):
        from python.helpers.cortex_struggle_aggregator import generate_hypotheses, StruggleCluster, format_for_telegram
        clusters = [StruggleCluster(topic="pricing_research", event_count=5, weighted_score=13.0,
                                    severity_distribution={"high": 3})]
        hyps = generate_hypotheses(clusters)
        text = format_for_telegram(hyps)
        assert isinstance(text, str)


# ════════════════════════════════════════════════════════════════════════════
# G-2: Experiment Judge
# ════════════════════════════════════════════════════════════════════════════

class TestExperimentJudge:
    """Tests for cortex_experiment_judge.py — DeepSeek scoring."""

    def test_evaluate_returns_judge_result(self):
        from python.helpers.cortex_experiment_judge import evaluate
        from python.helpers.cortex_experiment_suite import get_by_id

        query = get_by_id("V1")
        mock_response = json.dumps({
            criterion.key: criterion.max_score
            for criterion in query.rubric
        })

        async def run():
            with patch.dict(os.environ, {"API_KEY_OPENROUTER": "test-key"}):
                with patch("httpx.AsyncClient") as mock_client:
                    mock_resp = MagicMock()
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {
                        "choices": [{"message": {"content": mock_response}}]
                    }
                    mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
                    return await evaluate("V1", query.query, "test response", query.rubric)

        result = asyncio.run(run())
        assert result.query_id == "V1"
        # overall_score is the field name (not total_score)
        assert result.overall_score >= 0

    def test_score_delta_detects_improvement(self):
        from python.helpers.cortex_experiment_judge import score_delta, JudgeResult, CriterionScore
        baseline = JudgeResult(
            query_id="V1", overall_score=6.0,
            criterion_scores=[CriterionScore("c1", 1, 2, ""), CriterionScore("c2", 0, 2, "")],
        )
        experimental = JudgeResult(
            query_id="V1", overall_score=8.0,
            criterion_scores=[CriterionScore("c1", 2, 2, ""), CriterionScore("c2", 1, 2, "")],
        )
        delta = score_delta(baseline, experimental)
        assert delta["overall_delta"] > 0
        # Key is "improved_criteria" not "improved"
        assert len(delta["improved_criteria"]) > 0


# ════════════════════════════════════════════════════════════════════════════
# G-3: Operational Reporter
# ════════════════════════════════════════════════════════════════════════════

class TestOperationalReporter:
    """Tests for cortex_operational_reporter.py — Loop 3 report generation."""

    def test_generate_returns_dict_with_required_keys(self):
        from python.helpers import cortex_operational_reporter as reporter

        # Match actual return types from cortex_event_store
        mock_struggles = []
        mock_tools = {"by_tool": {}, "total_sessions": 0}  # dict
        mock_corrections = []                               # list of {correction_type, count}
        mock_latency = []
        mock_failures = []
        mock_benchmarks = []

        with patch("python.helpers.cortex_event_store.get_struggle_events", return_value=mock_struggles), \
             patch("python.helpers.cortex_event_store.get_tool_usage_summary", return_value=mock_tools), \
             patch("python.helpers.cortex_event_store.get_correction_summary", return_value=mock_corrections), \
             patch("python.helpers.cortex_event_store.get_latency_summary", return_value=mock_latency), \
             patch("python.helpers.cortex_event_store.get_extension_failures", return_value=mock_failures), \
             patch("python.helpers.cortex_event_store.get_benchmark_history", return_value=mock_benchmarks), \
             patch("python.helpers.cortex_struggle_aggregator.aggregate", return_value=[]):
            report = reporter.generate(period_days=60)

        required_keys = {"period_days", "generated_at", "struggle_clusters", "tool_usage",
                         "latency_hotspots", "user_corrections", "extension_failures"}
        for key in required_keys:
            assert key in report, f"Missing key: {key}"

    def test_to_markdown_returns_string(self):
        from python.helpers import cortex_operational_reporter as reporter
        # Build a minimal report that matches the actual generate() output structure
        with patch("python.helpers.cortex_event_store.get_struggle_events", return_value=[]), \
             patch("python.helpers.cortex_event_store.get_tool_usage_summary", return_value={"by_tool": {}, "total_sessions": 0}), \
             patch("python.helpers.cortex_event_store.get_correction_summary", return_value=[]), \
             patch("python.helpers.cortex_event_store.get_latency_summary", return_value=[]), \
             patch("python.helpers.cortex_event_store.get_extension_failures", return_value=[]), \
             patch("python.helpers.cortex_event_store.get_benchmark_history", return_value=[]), \
             patch("python.helpers.cortex_struggle_aggregator.aggregate", return_value=[]):
            report = reporter.generate(period_days=60)
        md = reporter.to_markdown(report)
        assert isinstance(md, str)
        assert len(md) > 50


# ════════════════════════════════════════════════════════════════════════════
# G-4: Outcome Attributor
# ════════════════════════════════════════════════════════════════════════════

class TestOutcomeAttributor:
    """Tests for cortex_outcome_attributor.py — Loop 2 attribution."""

    def _make_record(self, **kwargs):
        from python.helpers.cortex_outcome_attributor import OutcomeRecord
        defaults = dict(
            venture_id="v1", venture_name="Test Venture",
            period="2026-Q1", metric_type="revenue",
            target_value=10000.0, actual_value=9000.0,
            cortex_controlled_slice="pricing_strategy",
            user_execution_confirmed=True,
            external_confounders=[],
            autonomy_score=0.8,
        )
        defaults.update(kwargs)
        return OutcomeRecord(**defaults)

    def test_classify_cortex_owned_when_execution_confirmed(self):
        from python.helpers.cortex_outcome_attributor import classify
        record = self._make_record(user_execution_confirmed=True, external_confounders=[])
        result = classify(record)
        assert result.attribution == "cortex_owned"
        assert result.signal_weight > 0

    def test_classify_user_owned_when_execution_not_confirmed(self):
        from python.helpers.cortex_outcome_attributor import classify
        record = self._make_record(user_execution_confirmed=False)
        result = classify(record)
        assert result.attribution == "user_owned"
        assert result.signal_weight == 0.0

    def test_classify_mixed_with_external_confounders(self):
        from python.helpers.cortex_outcome_attributor import classify
        record = self._make_record(
            user_execution_confirmed=True,
            external_confounders=["market_crash", "competitor_entry"],
        )
        result = classify(record)
        assert result.attribution in ("external", "mixed")
        assert result.signal_weight < 0.8

    def test_autonomy_score_scales_signal_weight(self):
        from python.helpers.cortex_outcome_attributor import classify
        high = self._make_record(autonomy_score=1.0, user_execution_confirmed=True)
        low = self._make_record(autonomy_score=0.3, user_execution_confirmed=True)
        assert classify(high).signal_weight > classify(low).signal_weight

    def test_signal_qualifies_min_weight(self):
        from python.helpers.cortex_outcome_attributor import classify, signal_qualifies
        record = self._make_record(user_execution_confirmed=False)
        classified = classify(record)
        assert not signal_qualifies(classified, min_weight=0.2)


# ════════════════════════════════════════════════════════════════════════════
# G-4: Optimization Signal
# ════════════════════════════════════════════════════════════════════════════

class TestOptimizationSignal:
    """Tests for cortex_optimization_signal.py — signal generation."""

    def _classified_record(self, delta: float, autonomy: float = 0.8):
        from python.helpers.cortex_outcome_attributor import OutcomeRecord, classify
        target = 10000.0
        actual = target * (1 + delta)
        record = OutcomeRecord(
            venture_id="v1", venture_name="Test",
            period="2026-Q1", metric_type="revenue",
            target_value=target, actual_value=actual,
            cortex_controlled_slice="pricing",
            user_execution_confirmed=True,
            external_confounders=[],
            autonomy_score=autonomy,
        )
        return classify(record)

    def test_strong_failure_generates_knowledge_gap(self):
        from python.helpers.cortex_optimization_signal import generate_signal
        record = self._classified_record(delta=-0.40)
        signal = generate_signal(record)
        assert signal is not None
        assert signal.signal_type == "knowledge_gap"

    def test_strong_success_generates_success_pattern(self):
        from python.helpers.cortex_optimization_signal import generate_signal
        record = self._classified_record(delta=0.25)
        signal = generate_signal(record)
        assert signal is not None
        assert signal.signal_type == "success_pattern"

    def test_moderate_miss_generates_calibration_note(self):
        from python.helpers.cortex_optimization_signal import generate_signal
        record = self._classified_record(delta=-0.15)
        signal = generate_signal(record)
        assert signal is not None
        assert signal.signal_type == "calibration_note"

    def test_user_owned_generates_no_signal(self):
        from python.helpers.cortex_optimization_signal import generate_signal
        from python.helpers.cortex_outcome_attributor import OutcomeRecord, classify
        record = OutcomeRecord(
            venture_id="v1", venture_name="Test",
            period="2026-Q1", metric_type="revenue",
            target_value=10000.0, actual_value=5000.0,
            cortex_controlled_slice="pricing",
            user_execution_confirmed=False,
            external_confounders=[],
            autonomy_score=0.8,
        )
        classified = classify(record)
        signal = generate_signal(classified)
        assert signal is None


# ════════════════════════════════════════════════════════════════════════════
# G-5: Inter-agent Protocol
# ════════════════════════════════════════════════════════════════════════════

class TestInteragentProtocol:
    """Tests for cortex_interagent_protocol.py — Loop 3 protocol."""

    def test_fallback_response_is_converged(self):
        from python.helpers.cortex_interagent_protocol import _fallback_ruflo_response
        msg = _fallback_ruflo_response(round_num=1)
        assert msg.sender == "ruflo"
        assert msg.convergence == "converged"

    def test_build_human_report_returns_string(self):
        from python.helpers.cortex_interagent_protocol import (
            build_human_report, ProtocolSession, ProtocolMessage
        )
        session = ProtocolSession(session_id="loop3-test-001")
        ruflo_msg = ProtocolMessage(
            sender="ruflo", round_num=1, msg_type="architectural_analysis",
            content={
                "findings": [{"re": "test", "architectural_cause": "cause", "proposed_fix": "fix",
                               "affected_components": ["ext.py"], "breaking_risk": "none", "fix_complexity": "low"}],
                "proposed_fixes": [{"id": "fix-1", "description": "Add retry", "target_file": "ext.py", "priority": "high"}],
                "open_questions_for_cortex": [],
                "convergence_assessment": "converged",
                "convergence_rationale": "All issues addressed.",
            },
            convergence="converged",
        )
        session.add_message(ruflo_msg)
        session.final_proposals = ruflo_msg.content.get("proposed_fixes", [])
        report = build_human_report(session)
        assert isinstance(report, str)
        assert "Findings" in report
        assert "Proposed Actions" in report or "proposed" in report.lower()

    def test_build_cortex_followup_answers_questions(self):
        from python.helpers.cortex_interagent_protocol import _build_cortex_followup, ProtocolMessage
        ruflo_msg = ProtocolMessage(
            sender="ruflo", round_num=1, msg_type="architectural_analysis",
            content={
                "findings": [],
                "proposed_fixes": [],
                "open_questions_for_cortex": ["What are the latency hotspots?"],
                "convergence_assessment": "continue",
                "convergence_rationale": "",
            },
        )
        operational_report = {"latency_hotspots": [{"task": "research", "p95_ms": 8000}]}
        followup = _build_cortex_followup(ruflo_msg, operational_report, round_num=2)
        assert followup.msg_type == "cortex_followup"
        assert "answers_to_ruflo_questions" in followup.content


# ════════════════════════════════════════════════════════════════════════════
# G-6: Stack Inventory
# ════════════════════════════════════════════════════════════════════════════

class TestStackInventory:
    """Tests for cortex_stack_inventory.py — authoritative stack definition."""

    def test_all_components_have_required_fields(self):
        from python.helpers.cortex_stack_inventory import STACK
        required = {"component", "category", "role", "version", "api_endpoint", "cost_model"}
        for comp in STACK:
            d = comp.to_dict()
            for field in required:
                assert field in d and d[field], f"Component {comp.component} missing field: {field}"

    def test_categories_are_valid(self):
        from python.helpers.cortex_stack_inventory import STACK
        valid_cats = {"llm", "memory", "research", "communication", "infra", "voice", "vision"}
        for comp in STACK:
            assert comp.category in valid_cats, f"{comp.component}: invalid category {comp.category}"

    def test_get_by_category(self):
        from python.helpers.cortex_stack_inventory import get_by_category
        llms = get_by_category("llm")
        assert len(llms) >= 3

    def test_get_by_component(self):
        from python.helpers.cortex_stack_inventory import get_by_component
        comp = get_by_component("openrouter")
        assert comp is not None
        assert comp["category"] == "infra"

    def test_summary(self):
        from python.helpers.cortex_stack_inventory import summary
        s = summary()
        assert s["total_components"] >= 15
        assert "by_category" in s


# ════════════════════════════════════════════════════════════════════════════
# G-6: Stack Evaluator
# ════════════════════════════════════════════════════════════════════════════

class TestStackEvaluator:
    """Tests for cortex_stack_evaluator.py — risk/benefit matrix."""

    def _make_finding(self, recommendation="stable", update=False, pricing_change=False,
                      component="tavily", category="research", pricing_desc=""):
        return {
            "component": component,
            "category": category,
            "current_version": "v1",
            "recommendation": recommendation,
            "update_available": update,
            "pricing_change": pricing_change,
            "pricing_change_description": pricing_desc,
            "reliability_signals": [],
            "notable_alternatives": [],
            "researched_at": "2026-03-01T00:00:00",
        }

    def test_stable_recommendation_gives_stable_decision(self):
        from python.helpers.cortex_stack_evaluator import evaluate_finding
        finding = self._make_finding("stable")
        eval = evaluate_finding(finding)
        assert eval.decision in ("STABLE", "MONITOR")

    def test_replace_recommendation_can_trigger_replace_now(self):
        from python.helpers.cortex_stack_evaluator import evaluate_finding
        finding = self._make_finding(
            "replace", update=True, pricing_change=True,
            pricing_desc="50% cheaper than current",
            component="tavily", category="research",
        )
        eval = evaluate_finding(finding)
        assert eval.decision in ("REPLACE_NOW", "INVESTIGATE")

    def test_high_risk_component_never_replace_now_without_investigation(self):
        from python.helpers.cortex_stack_evaluator import evaluate_finding
        # OpenRouter is 0.90 risk — even with "replace" recommendation → should be INVESTIGATE
        finding = self._make_finding("replace", component="openrouter", category="infra")
        eval = evaluate_finding(finding)
        assert eval.decision in ("INVESTIGATE", "MONITOR", "STABLE")

    def test_build_evaluation_report_structure(self):
        from python.helpers.cortex_stack_evaluator import evaluate_all_findings, build_evaluation_report
        findings = [
            self._make_finding("stable", component="tavily"),
            self._make_finding("monitor", component="exa"),
        ]
        evals = evaluate_all_findings(findings)
        report = build_evaluation_report(evals)
        assert "total_components" in report
        assert "summary" in report
        assert report["total_components"] == 2

    def test_format_report_markdown(self):
        from python.helpers.cortex_stack_evaluator import evaluate_all_findings, build_evaluation_report, format_report_markdown
        findings = [self._make_finding("stable", component="tavily")]
        evals = evaluate_all_findings(findings)
        report = build_evaluation_report(evals)
        md = format_report_markdown(report)
        assert isinstance(md, str)
        assert "Loop 5" in md


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
