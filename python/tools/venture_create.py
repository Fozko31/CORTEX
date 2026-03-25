"""
venture_create — CORTEX Venture Creation Tool (Phase C)
=========================================================

Agent Zero tool that drives deep iterative venture creation.

State machine phases (stored in agent.set_data):
  INITIATION      — parse brief, pull L1/L2/L3 memory context
  EXPLORATION     — Tier 1 research → gap analysis
  BRAIN_PICKING   — ask user targeted gap-filling questions
  TIER2_GATE      — (optional) show cost, confirm Tier 2
  TIER2_RESEARCH  — deep Tier 2 research for high-importance gaps
  SYNTHESIS       — draft VentureDNA with CVS + CORTEX capability lens
  ITERATION       — user reviews → refine specific weak points
  CRYSTALLIZATION — finalize DNA, compute all scores, show visual
  CONFIRMATION    — user confirms → persist → create SurfSense spaces → push Graphiti

The LLM calls this tool with action + parameters:
  {"action": "start", "venture_name": "...", "description": "..."}
  {"action": "continue", "input": "user's answer to current question"}
  {"action": "skip_tier2"}
  {"action": "use_tier2"}  — manual Tier 2 override
  {"action": "confirm"}   — user confirmed in conversation
  {"action": "cancel"}
  {"action": "status"}    — show current session state
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from python.helpers.tool import Tool, Response


class VentureCreate(Tool):

    async def execute(self, **kwargs) -> Response:
        action = kwargs.get("action", "start").lower().strip()
        venture_name = kwargs.get("venture_name", "").strip()
        user_input = kwargs.get("input", kwargs.get("user_input", "")).strip()
        tier_override = kwargs.get("tier_override", "")
        description = kwargs.get("description", kwargs.get("brief", "")).strip()

        try:
            if action == "start":
                return await self._start(venture_name, description, user_input)
            elif action == "continue":
                return await self._continue(user_input)
            elif action == "use_tier2":
                return await self._trigger_tier2(manual=True)
            elif action == "skip_tier2":
                return await self._skip_tier2()
            elif action == "confirm":
                return await self._confirm()
            elif action == "cancel":
                return await self._cancel()
            elif action == "status":
                return await self._status()
            else:
                # Unknown action — treat as continue with whatever input was given
                return await self._continue(user_input or action)
        except Exception as e:
            tb = traceback.format_exc()
            return Response(
                message=f"Venture creation error: {e}\n\n{tb[:300]}",
                break_loop=False,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Phase: INITIATION
    # ─────────────────────────────────────────────────────────────────────────

    async def _start(self, venture_name: str, description: str, extra_input: str) -> Response:
        if not venture_name:
            return Response(
                message="I need a venture name to start. Call again with action='start' and venture_name='...'",
                break_loop=False,
            )

        # Pull existing memory context (L1/L2/L3) before starting research
        memory_context = await self._pull_memory_context(venture_name)

        # Check if venture already exists
        from python.helpers.cortex_venture_dna import load_venture
        existing = load_venture(venture_name, self.agent)
        if existing:
            return Response(
                message=(
                    f"Venture '{venture_name}' already exists (stage={existing.stage}, "
                    f"CVS={existing.cvs_score.composite_cvs():.1f}). "
                    f"Use venture_manage with action='update' to modify it, "
                    f"or start with a different name."
                ),
                break_loop=False,
            )

        # Initialize session state
        session = {
            "phase": "INITIATION",
            "venture_name": venture_name,
            "description": description,
            "memory_context": memory_context,
            "tier1_report": None,
            "tier2_report": None,
            "gap_questions": [],
            "gap_index": 0,
            "user_answers": {},
            "dna_dict": None,
            "iteration_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_session(session)

        # Parse the brief and extract initial facts
        brief_text = description or extra_input or ""
        parsed = await self._parse_brief(venture_name, brief_text, memory_context)
        session.update({
            "phase": "EXPLORATION",
            "venture_type": parsed.get("venture_type", "generic"),
            "market": parsed.get("market", "global"),
            "language": parsed.get("language", "en"),
            "user_goals": parsed.get("goals", []),
            "user_constraints": parsed.get("constraints", []),
            "initial_insights": parsed.get("initial_insights", []),
        })

        # Kick off Tier 1 research
        self._save_session(session)
        log_item = self.agent.context.log.log(
            type="util",
            heading=f"Venture Creation: {venture_name}",
            content="Running Tier 1 market research...",
        )

        report = await self._run_tier1(session)
        session["tier1_report"] = report.to_dict() if report else None
        session["phase"] = "BRAIN_PICKING"

        # Analyze gaps
        if report:
            from python.helpers.cortex_venture_discovery import CortexVentureScanner
            scanner = CortexVentureScanner(self.agent)
            gaps = await scanner.analyze_gaps(report)
            report.gaps = gaps
            session["tier1_report"] = report.to_dict()
            session["gap_questions"] = [g.question for g in gaps if g.importance in ("high", "medium")]

        self._save_session(session)
        log_item.update(content=f"Tier 1 complete. {len(session['gap_questions'])} gaps identified.")

        # Build first response
        return self._response_after_exploration(session, report)

    # ─────────────────────────────────────────────────────────────────────────
    # Phase: CONTINUE (handles brain-picking, iteration, tier2 gate)
    # ─────────────────────────────────────────────────────────────────────────

    async def _continue(self, user_input: str) -> Response:
        session = self._load_session()
        if not session:
            return Response(
                message="No active venture creation session. Start with action='start' and venture_name='...'",
                break_loop=False,
            )

        phase = session.get("phase", "BRAIN_PICKING")

        if phase == "BRAIN_PICKING":
            return await self._handle_brain_picking(session, user_input)
        elif phase == "TIER2_GATE":
            # user answered the cost gate question
            affirmative = any(w in user_input.lower() for w in ("yes", "ok", "proceed", "go", "do it", "tier2", "tier 2"))
            if affirmative:
                return await self._trigger_tier2(manual=False)
            else:
                return await self._skip_tier2()
        elif phase == "SYNTHESIS":
            return await self._handle_synthesis(session, user_input)
        elif phase == "ITERATION":
            return await self._handle_iteration(session, user_input)
        elif phase == "CRYSTALLIZATION":
            # User is reviewing the crystallization output
            if any(w in user_input.lower() for w in ("confirm", "yes", "looks good", "proceed", "approved", "ok", "go")):
                return await self._confirm()
            else:
                # User has feedback — iterate
                session["phase"] = "ITERATION"
                session["iteration_feedback"] = user_input
                self._save_session(session)
                return await self._handle_iteration(session, user_input)
        else:
            return Response(message=f"Unknown phase '{phase}'. Use action='status' to check state.", break_loop=False)

    async def _handle_brain_picking(self, session: dict, answer: str) -> Response:
        gap_index = session.get("gap_index", 0)
        gap_questions = session.get("gap_questions", [])

        # Record the answer to current question
        if gap_index > 0 and gap_index <= len(gap_questions):
            current_q = gap_questions[gap_index - 1]
            session["user_answers"][current_q] = answer

        # Check if we should trigger Tier 2
        from python.helpers.cortex_venture_discovery import CortexVentureScanner, should_gate_tier2
        scanner = CortexVentureScanner(self.agent)

        tier1_dict = session.get("tier1_report", {})
        if tier1_dict:
            from python.helpers.cortex_venture_discovery import TrendReport, ResearchGap
            # Reconstruct confidence from stored dict
            confidence = float(tier1_dict.get("confidence", 0.6))
            gap_count = len([q for q in gap_questions if q not in session.get("user_answers", {})])
            needs_t2 = confidence < 0.6 or gap_count >= 2
        else:
            needs_t2 = False

        # Ask next gap question if we haven't asked them all
        if gap_index < len(gap_questions):
            next_q = gap_questions[gap_index]
            session["gap_index"] = gap_index + 1
            self._save_session(session)

            header = ""
            if answer and gap_index > 0:
                header = f"Noted. "

            # If this is the last question AND we need Tier 2, warn
            if gap_index == len(gap_questions) - 1 and needs_t2:
                should_gate, est_cost = should_gate_tier2()
                tier2_note = (
                    f"\n\n*After your answer, I'll run Tier 2 deep research "
                    f"(est. ${est_cost:.2f}) to fill remaining gaps before synthesis.*"
                )
            else:
                tier2_note = ""

            return Response(
                message=f"{header}**Question {gap_index + 1}/{len(gap_questions)}:** {next_q}{tier2_note}",
                break_loop=False,
            )

        # All questions answered — decide on Tier 2
        session["gap_index"] = len(gap_questions)
        self._save_session(session)

        if needs_t2:
            should_gate, est_cost = should_gate_tier2()
            if should_gate:
                session["phase"] = "TIER2_GATE"
                self._save_session(session)
                return Response(
                    message=(
                        f"Confidence on '{session['venture_name']}' is below 60% after Tier 1 research. "
                        f"Running Tier 2 deep research (est. ${est_cost:.2f} via Perplexity) would significantly improve the analysis. "
                        f"Proceed? (yes/no)"
                    ),
                    break_loop=False,
                )
            else:
                return await self._trigger_tier2(manual=False)
        else:
            # Move to synthesis
            return await self._run_synthesis(session)

    async def _handle_synthesis(self, session: dict, user_input: str) -> Response:
        # User is responding to synthesis review — move to iteration or crystallization
        if any(w in user_input.lower() for w in ("good", "ok", "proceed", "next", "yes", "looks good", "crystallize")):
            return await self._run_crystallization(session)
        else:
            session["phase"] = "ITERATION"
            session["iteration_feedback"] = user_input
            self._save_session(session)
            return await self._handle_iteration(session, user_input)

    async def _handle_iteration(self, session: dict, feedback: str) -> Response:
        session["iteration_count"] = session.get("iteration_count", 0) + 1
        iteration_count = session["iteration_count"]

        if iteration_count > 3:
            # Max iterations reached — move to crystallization
            session["phase"] = "CRYSTALLIZATION"
            self._save_session(session)
            return await self._run_crystallization(session)

        # Use feedback to refine weak points
        dna = self._session_to_dna(session)
        refinement_prompt = (
            f"The user has feedback on the venture '{session['venture_name']}' synthesis:\n"
            f"Feedback: {feedback}\n\n"
            f"Current insights: {'; '.join(dna.key_insights[:5])}\n"
            f"Current CVS: {dna.cvs_score.composite_cvs():.1f}\n"
            f"Open questions: {'; '.join(dna.open_questions[:3])}\n\n"
            "Respond with:\n"
            "1. Which CVS dimension was questioned (if any)\n"
            "2. Your revised assessment (specific, data-driven)\n"
            "3. Whether this changes the recommendation\n"
            "4. Ask one clarifying question if needed, OR say 'ready to crystallize'"
        )

        from python.helpers.cortex_model_router import CortexModelRouter
        response = await CortexModelRouter.call_async("synthesis", refinement_prompt)

        if "ready to crystallize" in response.lower():
            session["phase"] = "CRYSTALLIZATION"
            self._save_session(session)
            return await self._run_crystallization(session)

        session["phase"] = "ITERATION"
        session["last_refinement"] = response
        self._save_session(session)

        return Response(
            message=f"**Iteration {iteration_count}:**\n\n{response}",
            break_loop=False,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Tier 2 gate
    # ─────────────────────────────────────────────────────────────────────────

    async def _trigger_tier2(self, manual: bool = False) -> Response:
        session = self._load_session()
        if not session:
            return Response(message="No active session.", break_loop=False)

        log_item = self.agent.context.log.log(
            type="util",
            heading=f"Venture Creation: {session['venture_name']}",
            content=f"Running Tier 2 deep research{'  (manual)' if manual else ''}...",
        )

        from python.helpers.cortex_venture_discovery import CortexVentureScanner
        scanner = CortexVentureScanner(self.agent)

        tier1_report = None
        tier1_dict = session.get("tier1_report")
        if tier1_dict:
            tier1_report = _dict_to_trend_report(tier1_dict)

        report = await scanner.scan_tier2(
            niche=session["venture_name"],
            market=session.get("market", "global"),
            language=session.get("language", "en"),
            tier1_report=tier1_report,
            manual_override=manual,
        )

        session["tier2_report"] = report.to_dict()
        session["phase"] = "SYNTHESIS"
        self._save_session(session)

        log_item.update(content=f"Tier 2 complete. Confidence: {report.confidence:.0%}")
        return await self._run_synthesis(session)

    async def _skip_tier2(self) -> Response:
        session = self._load_session()
        if not session:
            return Response(message="No active session.", break_loop=False)
        session["phase"] = "SYNTHESIS"
        self._save_session(session)
        return await self._run_synthesis(session)

    # ─────────────────────────────────────────────────────────────────────────
    # Phase: SYNTHESIS
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_synthesis(self, session: dict) -> Response:
        venture_name = session["venture_name"]

        log_item = self.agent.context.log.log(
            type="util",
            heading=f"Venture Synthesis: {venture_name}",
            content="Building VentureDNA with CVS scoring...",
        )

        # Merge all research into DNA
        dna = await self._build_dna_from_session(session)

        # CORTEX capability lens — score AI autonomy dimensions
        dna = await self._apply_capability_lens(dna, session)

        # Update session with DNA
        session["dna_dict"] = dna.to_dict()
        session["phase"] = "SYNTHESIS"
        self._save_session(session)

        log_item.update(content=f"CVS: {dna.cvs_score.composite_cvs():.1f} [{dna.cvs_score.verdict()}]")

        # Build synthesis summary
        synthesis_msg = self._format_synthesis(dna, session)

        return Response(
            message=synthesis_msg + "\n\nDoes this capture the opportunity correctly? Add feedback or say 'proceed' to crystallize.",
            break_loop=False,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Phase: CRYSTALLIZATION
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_crystallization(self, session: dict) -> Response:
        dna = self._session_to_dna(session)

        # Final CVS recompute
        dna.recompute_research_certainty()

        # Save updated DNA dict
        session["dna_dict"] = dna.to_dict()
        session["phase"] = "CRYSTALLIZATION"
        self._save_session(session)

        # Visual output
        cvs_visual = dna.render_cvs()
        health = dna.compute_health_pulse()
        health_visual = health.render()

        open_q_block = ""
        if dna.open_questions:
            open_q_block = "\n\n**Open questions (will track):**\n" + "\n".join(f"- {q}" for q in dna.open_questions[:5])

        msg = (
            f"## Venture DNA: {dna.name}\n\n"
            f"**Type:** {dna.venture_type} | **Stage:** {dna.stage} | "
            f"**Confidence:** {dna.confidence_level:.0%}\n\n"
            f"**Goals:** {'; '.join(dna.user_goals[:3])}\n\n"
            f"**Key Insights:**\n" + "\n".join(f"- {i}" for i in dna.key_insights[:6]) + "\n\n"
            f"```\n{cvs_visual}\n```\n\n"
            f"```\n{health_visual}\n```"
            f"{open_q_block}\n\n"
            "---\n**Type 'confirm' to commit this venture, or share any final adjustments.**"
        )

        return Response(message=msg, break_loop=False)

    # ─────────────────────────────────────────────────────────────────────────
    # Phase: CONFIRMATION
    # ─────────────────────────────────────────────────────────────────────────

    async def _confirm(self) -> Response:
        session = self._load_session()
        if not session:
            return Response(message="No active venture session to confirm.", break_loop=False)

        dna = self._session_to_dna(session)
        venture_name = dna.name

        log_item = self.agent.context.log.log(
            type="util",
            heading=f"Venture Confirmed: {venture_name}",
            content="Persisting DNA, creating SurfSense spaces...",
        )

        errors = []

        # 1. Save to disk
        try:
            from python.helpers.cortex_venture_dna import save_venture
            save_venture(dna, self.agent)
        except Exception as e:
            errors.append(f"disk save: {e}")

        # 2. Record to OutcomeLedger
        try:
            from python.helpers.cortex_outcome_ledger import get_ledger
            ledger = get_ledger(self.agent)
            ledger.record_venture_creation(dna)
        except Exception as e:
            errors.append(f"ledger: {e}")

        # 3. Create SurfSense spaces
        try:
            await self._create_surfsense_spaces(dna)
        except Exception as e:
            errors.append(f"surfsense spaces: {e}")

        # 4. Push to Graphiti
        try:
            await self._push_to_graphiti(dna)
        except Exception as e:
            errors.append(f"graphiti: {e}")

        # 5. Cross-venture synthesis (background)
        try:
            from python.helpers.cortex_venture_dna import list_ventures, synthesize_cross_venture_patterns
            from python.helpers.defer import DeferredTask, THREAD_BACKGROUND
            all_ventures = list_ventures(self.agent)
            if len(all_ventures) >= 2:
                task = DeferredTask(thread_name=THREAD_BACKGROUND)
                task.start_task(_run_cross_venture_synthesis, all_ventures, self.agent)
        except Exception as e:
            errors.append(f"cross-venture: {e}")

        # 6. Set as active venture
        self.agent.set_data("active_venture", dna.venture_id)
        self.agent.set_data("active_venture_name", dna.name)

        # 7. Clear creation session
        self.agent.set_data("venture_creation_session", None)

        log_item.update(content=f"Venture '{venture_name}' committed. Errors: {errors or 'none'}")

        error_note = ""
        if errors:
            error_note = f"\n\n*Note: minor issues: {', '.join(errors)}*"

        return Response(
            message=(
                f"Venture **{venture_name}** is committed.\n\n"
                f"- DNA persisted to disk\n"
                f"- SurfSense spaces created: `{dna.surfsense_dna_space_name}` + `{dna.surfsense_ops_space_name}`\n"
                f"- Logged to OutcomeLedger\n"
                f"- Active venture set\n\n"
                f"CVS: **{dna.cvs_score.composite_cvs():.1f}/100** [{dna.cvs_score.verdict()}]{error_note}"
            ),
            break_loop=False,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    async def _cancel(self) -> Response:
        self.agent.set_data("venture_creation_session", None)
        return Response(message="Venture creation cancelled. No data was saved.", break_loop=False)

    async def _status(self) -> Response:
        session = self._load_session()
        if not session:
            return Response(message="No active venture creation session.", break_loop=False)
        phase = session.get("phase", "?")
        name = session.get("venture_name", "?")
        gaps_answered = len(session.get("user_answers", {}))
        gaps_total = len(session.get("gap_questions", []))
        return Response(
            message=(
                f"**Venture creation in progress:** {name}\n"
                f"Phase: {phase} | "
                f"Gaps: {gaps_answered}/{gaps_total} answered | "
                f"Iterations: {session.get('iteration_count', 0)}"
            ),
            break_loop=False,
        )

    def _save_session(self, session: dict) -> None:
        self.agent.set_data("venture_creation_session", session)

    def _load_session(self) -> Optional[dict]:
        return self.agent.get_data("venture_creation_session")

    async def _pull_memory_context(self, venture_name: str) -> str:
        """Pull existing L1/L2/L3 context relevant to this venture."""
        context_parts = []

        # L1 FAISS recall
        try:
            from python.helpers import memory as memory_module
            mem = memory_module.Memory.get(self.agent)
            results = await mem.search_memory(
                query=venture_name,
                count=5,
                threshold=0.4,
                filter="all",
            )
            if results:
                snippets = [r.get("content", "")[:200] for r in results[:3]]
                context_parts.append("L1 memory: " + " | ".join(snippets))
        except Exception:
            pass

        # L2 Graphiti
        try:
            from python.helpers.cortex_graphiti_client import CortexGraphitiClient
            client = CortexGraphitiClient.from_agent_config(self.agent)
            if client:
                results = await client.search(venture_name, limit=3)
                if results:
                    context_parts.append("L2 graph: " + "; ".join(r.get("content", "")[:100] for r in results[:2]))
                await client.close()
        except Exception:
            pass

        return "\n".join(context_parts) if context_parts else ""

    async def _parse_brief(self, venture_name: str, description: str, memory_context: str) -> dict:
        """Parse the venture brief into structured fields."""
        from python.helpers.cortex_model_router import CortexModelRouter

        prompt = (
            f"Parse this venture brief into structured fields.\n"
            f"Venture name: {venture_name}\n"
            f"Description: {description or '(none provided)'}\n"
            f"Memory context: {memory_context[:500] or '(none)'}\n\n"
            "Return JSON: {venture_type, market, language, goals: [...], "
            "constraints: [...], initial_insights: [...]}"
        )
        try:
            raw = await CortexModelRouter.call_async("classification", prompt)
            import dirtyJson
            return dirtyJson.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return {"venture_type": "generic", "market": "global", "language": "en",
                    "goals": [], "constraints": [], "initial_insights": []}

    async def _run_tier1(self, session: dict):
        """Run Tier 1 research for the current session."""
        try:
            from python.helpers.cortex_venture_discovery import CortexVentureScanner
            scanner = CortexVentureScanner(self.agent)
            report = await scanner.scan_tier1(
                niche=session["venture_name"],
                market=session.get("market", "global"),
                language=session.get("language", "en"),
                context=session.get("description", ""),
            )
            return report
        except Exception:
            return None

    async def _build_dna_from_session(self, session: dict):
        """Build a VentureDNA from the current session state."""
        from python.helpers.cortex_venture_dna import (
            VentureDNA, MarketIntelligence, ICP, CompetitorProfile, ResearchSnapshot,
        )
        from python.helpers.cortex_venture_discovery import TrendReport, merge_trend_report_into_dna

        dna = VentureDNA(
            name=session["venture_name"],
            venture_type=session.get("venture_type", "generic"),
            stage="idea",
            language=session.get("language", "en"),
            user_goals=session.get("user_goals", []),
            user_constraints=session.get("user_constraints", []),
        )

        for insight in session.get("initial_insights", []):
            dna.add_insight(insight)

        # Merge Tier 1 research
        t1 = session.get("tier1_report")
        if t1:
            report = _dict_to_trend_report(t1)
            merge_trend_report_into_dna(dna, report)

        # Merge Tier 2 research
        t2 = session.get("tier2_report")
        if t2:
            report = _dict_to_trend_report(t2)
            merge_trend_report_into_dna(dna, report)

        # Merge user answers into insights
        for question, answer in session.get("user_answers", {}).items():
            dna.add_insight(f"Q: {question[:80]} → A: {answer[:120]}")
            dna.resolve_question(question)

        # Synthesize CVS scores using LLM
        dna = await self._score_cvs_from_llm(dna, session)

        # Update confidence
        cert = dna.recompute_research_certainty()
        dna.set_confidence(min(cert / 100.0, 0.95))

        return dna

    async def _score_cvs_from_llm(self, dna, session: dict):
        """Use DeepSeek V3.2 to score CVS dimensions from research data."""
        from python.helpers.cortex_model_router import CortexModelRouter

        research_summary = (
            f"Market intelligence: {dna.market_intelligence.market_size_estimate}\n"
            f"Key trends: {'; '.join(dna.market_intelligence.key_trends[:5])}\n"
            f"Competitors: {', '.join(c.name for c in dna.competitor_profiles[:5])}\n"
            f"Key insights: {'; '.join(dna.key_insights[:5])}\n"
            f"Goals: {'; '.join(dna.user_goals[:3])}\n"
            f"Constraints: {'; '.join(dna.user_constraints[:3])}\n"
        )

        prompt = (
            f"Score the venture '{dna.name}' on 5 CVS dimensions (0-100 each):\n"
            f"- market_size: How big is the TAM and how fast is it growing?\n"
            f"- problem_severity: How painful is the problem? How frequently experienced?\n"
            f"- solution_uniqueness: How defensible/differentiated is the solution?\n"
            f"- implementation_ease: How easy to build (0=very hard, 100=trivial)?\n"
            f"- distribution_clarity: How clear is the go-to-market path?\n\n"
            f"Research data:\n{research_summary}\n\n"
            "Return JSON: {market_size, problem_severity, solution_uniqueness, implementation_ease, distribution_clarity, scoring_notes: str}"
        )

        try:
            raw = await CortexModelRouter.call_async("classification", prompt)
            import dirtyJson
            scores = dirtyJson.loads(raw) if isinstance(raw, str) else raw
            if isinstance(scores, dict):
                dna.update_cvs(
                    market_size=float(scores.get("market_size", 50)),
                    problem_severity=float(scores.get("problem_severity", 50)),
                    solution_uniqueness=float(scores.get("solution_uniqueness", 50)),
                    implementation_ease=float(scores.get("implementation_ease", 50)),
                    distribution_clarity=float(scores.get("distribution_clarity", 50)),
                )
                dna.cvs_score.scoring_notes = scores.get("scoring_notes", "")
        except Exception:
            dna.update_cvs(
                market_size=50, problem_severity=50, solution_uniqueness=50,
                implementation_ease=50, distribution_clarity=50,
            )

        return dna

    async def _apply_capability_lens(self, dna, session: dict):
        """
        CORTEX capability lens: evaluate venture through CORTEX's own tool set.
        Computes AI Setup Autonomy + AI Run Autonomy + Risk Level scores.
        """
        from python.helpers.cortex_model_router import CortexModelRouter

        prompt = (
            f"Evaluate venture '{dna.name}' ({dna.venture_type}) through CORTEX's capabilities:\n"
            "CORTEX can: web research (Tavily/Exa/Perplexity), code generation, SaaS integrations "
            "(via Composio), web scraping (Firecrawl), GitHub repo management, data analysis.\n\n"
            f"Venture insights: {'; '.join(dna.key_insights[:5])}\n"
            f"Goals: {'; '.join(dna.user_goals[:3])}\n\n"
            "Score 0-100:\n"
            "- ai_setup_autonomy: How much of the setup/build can CORTEX do without the user?\n"
            "- ai_run_autonomy: How much of ongoing operations can CORTEX run autonomously?\n"
            "- risk_level: How low is the total risk? (100=minimal risk: low time+money investment)\n\n"
            "Return JSON: {ai_setup_autonomy, ai_run_autonomy, risk_level, notes: str}"
        )

        try:
            raw = await CortexModelRouter.call_async("classification", prompt)
            import dirtyJson
            scores = dirtyJson.loads(raw) if isinstance(raw, str) else raw
            if isinstance(scores, dict):
                dna.update_cvs(
                    ai_setup_autonomy=float(scores.get("ai_setup_autonomy", 50)),
                    ai_run_autonomy=float(scores.get("ai_run_autonomy", 50)),
                    risk_level=float(scores.get("risk_level", 50)),
                )
                if scores.get("notes"):
                    dna.add_insight(f"[CORTEX lens] {scores['notes'][:200]}")
        except Exception:
            dna.update_cvs(ai_setup_autonomy=50, ai_run_autonomy=50, risk_level=50)

        return dna

    def _session_to_dna(self, session: dict):
        """Load VentureDNA from session's dna_dict."""
        from python.helpers.cortex_venture_dna import VentureDNA
        dna_dict = session.get("dna_dict")
        if dna_dict:
            return VentureDNA.from_dict(dna_dict)
        # If no DNA dict yet, build a minimal one
        from python.helpers.cortex_venture_dna import VentureDNA
        return VentureDNA(
            name=session.get("venture_name", "unknown"),
            user_goals=session.get("user_goals", []),
        )

    async def _create_surfsense_spaces(self, dna) -> None:
        """Create two SurfSense spaces for the venture (DNA + ops)."""
        surfsense_url = getattr(self.agent.config, "cortex_surfsense_url", "") or ""
        if not surfsense_url:
            return

        from python.helpers.cortex_surfsense_client import CortexSurfSenseClient
        client = CortexSurfSenseClient.from_agent_config(self.agent)
        if not client:
            return

        try:
            is_healthy = await client.health_check()
            if is_healthy:
                spaces = [
                    dna.surfsense_dna_space_name,
                    dna.surfsense_ops_space_name,
                ]
                spaces = [s for s in spaces if s]
                await client.ensure_spaces_exist(spaces)

                # Update DNA with space IDs if possible
                from python.helpers.cortex_venture_dna import save_venture
                save_venture(dna, self.agent)
        finally:
            await client.close()

    async def _push_to_graphiti(self, dna) -> None:
        """Push venture creation as an episode to Graphiti L2."""
        try:
            from python.helpers.cortex_graphiti_client import CortexGraphitiClient
            client = CortexGraphitiClient.from_agent_config(self.agent)
            if not client:
                return
            episode_body = (
                f"Venture '{dna.name}' created. "
                f"Type: {dna.venture_type}. "
                f"Goals: {'; '.join(dna.user_goals[:3])}. "
                f"CVS: {dna.cvs_score.composite_cvs():.1f} [{dna.cvs_score.verdict()}]. "
                f"Key insights: {'; '.join(dna.key_insights[:3])}."
            )
            await client.add_episode(
                name=f"Venture created: {dna.name}",
                body=episode_body,
                source_description="venture_create tool",
            )
            await client.close()
        except Exception:
            pass

    def _response_after_exploration(self, session: dict, report) -> Response:
        """Build the first brain-picking message after Tier 1 research."""
        venture_name = session["venture_name"]
        gap_questions = session.get("gap_questions", [])

        if report:
            opp = report.opportunity_summary or "Market opportunity identified."
            top_kws = ", ".join(report.top_keywords[:5]) or "—"
            competitors = ", ".join(report.top_competitors[:4]) or "—"
            conf = f"{report.confidence:.0%}"
        else:
            opp = "Research unavailable — proceeding with manual input."
            top_kws = competitors = conf = "—"

        research_block = (
            f"**Tier 1 research complete** (confidence: {conf})\n"
            f"- Opportunity: {opp}\n"
            f"- Top keywords: {top_kws}\n"
            f"- Competitors: {competitors}\n"
        )

        if gap_questions:
            first_q = gap_questions[0]
            session["gap_index"] = 1
            self._save_session(session)
            return Response(
                message=(
                    f"{research_block}\n\n"
                    f"I have {len(gap_questions)} questions to sharpen the analysis. "
                    f"Let's go:\n\n"
                    f"**Question 1/{len(gap_questions)}:** {first_q}"
                ),
                break_loop=False,
            )
        else:
            session["phase"] = "SYNTHESIS"
            self._save_session(session)
            import asyncio
            return Response(
                message=(
                    f"{research_block}\n\n"
                    f"Research looks solid — moving to synthesis. Stand by..."
                ),
                break_loop=False,
            )

    def _format_synthesis(self, dna, session: dict) -> str:
        """Format synthesis output for user review."""
        cvs = dna.cvs_score.composite_cvs()
        verdict = dna.cvs_score.verdict()
        return (
            f"## Synthesis: {dna.name}\n\n"
            f"**CVS: {cvs:.1f}/100 [{verdict}]** | "
            f"AI Setup: {dna.cvs_score.ai_setup_autonomy:.0f}% | "
            f"AI Run: {dna.cvs_score.ai_run_autonomy:.0f}% | "
            f"Risk: {dna.cvs_score.risk_level:.0f}/100\n\n"
            f"**Key findings:**\n" +
            "\n".join(f"- {i}" for i in dna.key_insights[:6]) +
            (f"\n\n**Open questions:**\n" + "\n".join(f"- {q}" for q in dna.open_questions[:3])
             if dna.open_questions else "")
        )


# ─────────────────────────────────────────────────────────────────────────────
# Background cross-venture synthesis
# ─────────────────────────────────────────────────────────────────────────────

async def _run_cross_venture_synthesis(ventures, agent) -> None:
    """Background task: synthesize patterns across all ventures."""
    try:
        from python.helpers.cortex_venture_dna import synthesize_cross_venture_patterns
        from python.helpers.cortex_ingestion_schema import build_document
        from python.helpers.cortex_surfsense_client import CortexSurfSenseClient

        patterns = await synthesize_cross_venture_patterns(ventures, agent)
        if not patterns:
            return

        surfsense_url = getattr(agent.config, "cortex_surfsense_url", "") or ""
        if not surfsense_url:
            return

        client = CortexSurfSenseClient.from_agent_config(agent)
        if not client:
            return

        try:
            is_healthy = await client.health_check()
            if not is_healthy:
                return

            await client.ensure_spaces_exist(["cortex_cross_venture"])

            for pattern in patterns:
                doc = build_document(
                    content=pattern.description,
                    category="research",
                    source="cross_venture_synthesis",
                    topic=f"Cross-venture {pattern.pattern_type}: {', '.join(pattern.venture_names)}",
                    tags=["cross_venture", pattern.pattern_type],
                    confidence=pattern.confidence,
                )
                await client.push_document("cortex_cross_venture", doc)
        finally:
            await client.close()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dict_to_trend_report(d: dict):
    """Reconstruct a TrendReport from a stored dict."""
    from python.helpers.cortex_venture_discovery import TrendReport, KeywordInsight, ResearchGap
    keywords = [
        KeywordInsight(
            keyword=k.get("keyword", ""),
            monthly_searches=k.get("monthly_searches", 0),
            trend_direction=k.get("trend_direction", "unknown"),
            competition=k.get("competition", "unknown"),
            opportunity_score=float(k.get("opportunity_score", 5.0)),
        )
        for k in d.get("keywords", [])
    ]
    gaps = [
        ResearchGap(question=g.get("question", ""), importance=g.get("importance", "medium"))
        for g in d.get("gaps", [])
    ]
    return TrendReport(
        market=d.get("market", "global"),
        niche=d.get("niche", ""),
        language=d.get("language", "en"),
        keywords=keywords,
        top_competitors=d.get("top_competitors", []),
        opportunity_summary=d.get("opportunity_summary", ""),
        recommended_action=d.get("recommended_action", ""),
        confidence=float(d.get("confidence", 0.5)),
        source=d.get("source", "stored"),
        tier_used=d.get("tier_used", 1),
        source_count=d.get("source_count", 0),
        gaps=gaps,
    )
