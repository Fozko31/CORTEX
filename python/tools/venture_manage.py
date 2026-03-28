"""
venture_manage — CORTEX Venture Management Tool (Phase C)
===========================================================

Actions:
  list                  — list all ventures with health pulse
  status [name]         — full VentureDNA + CVS visual for a venture
  health [name]         — compact health pulse
  activate <name>       — set active venture context
  deactivate            — clear active venture
  delete <name>         — archive/delete a venture
"""

from __future__ import annotations

from python.cortex.tool import Tool, Response


class VentureManage(Tool):

    async def execute(self, **kwargs) -> Response:
        action = kwargs.get("action", "list").lower().strip()
        venture_name = (kwargs.get("venture_name") or kwargs.get("name") or "").strip()

        try:
            if action == "list":
                return await self._list()
            elif action == "status":
                return await self._status(venture_name)
            elif action == "health":
                return await self._health(venture_name)
            elif action == "activate":
                return await self._activate(venture_name)
            elif action == "deactivate":
                return await self._deactivate()
            elif action in ("delete", "archive"):
                return await self._delete(venture_name)
            elif action == "cvs":
                return await self._cvs(venture_name)
            elif action == "kelly":
                return await self._kelly(venture_name)
            else:
                return Response(
                    message=f"Unknown action '{action}'. Available: list, status, health, activate, deactivate, delete, cvs, kelly",
                    break_loop=False,
                )
        except Exception as e:
            return Response(message=f"venture_manage error: {e}", break_loop=False)

    async def _list(self) -> Response:
        from python.helpers.cortex_venture_dna import list_ventures
        from python.helpers.cortex_outcome_ledger import get_ledger

        ventures = list_ventures(self.agent)
        if not ventures:
            return Response(
                message="No ventures yet. Use venture_create to start one.",
                break_loop=False,
            )

        ledger = get_ledger(self.agent)
        active_id = self.agent.get_data("active_venture") or ""

        lines = ["## Ventures\n"]
        for v in ventures:
            pulse = v.compute_health_pulse(
                open_decisions_count=ledger.open_decisions_count(v.venture_id),
                outcomes_count=ledger.outcomes_count(v.venture_id),
            )
            active_flag = " ⬅ ACTIVE" if v.venture_id == active_id else ""
            lines.append(
                f"**{v.name}**{active_flag} | {v.venture_type} | Stage: {v.stage} | "
                f"CVS: {pulse.cvs_composite:.1f} [{pulse.cvs_verdict}] | "
                f"DNA: {pulse.dna_completeness_pct:.0f}% | "
                f"Revenue: €{pulse.estimated_monthly_revenue_eur:,.0f}/mo"
            )

        return Response(message="\n".join(lines), break_loop=False)

    async def _status(self, venture_name: str) -> Response:
        dna = self._load_venture(venture_name)
        if not dna:
            return self._not_found(venture_name)

        from python.helpers.cortex_outcome_ledger import get_ledger
        ledger = get_ledger(self.agent)
        pulse = dna.compute_health_pulse(
            open_decisions_count=ledger.open_decisions_count(dna.venture_id),
            outcomes_count=ledger.outcomes_count(dna.venture_id),
        )

        goals_block = "\n".join(f"  - {g}" for g in dna.user_goals[:5]) or "  (none)"
        insights_block = "\n".join(f"  - {i}" for i in dna.key_insights[:8]) or "  (none)"
        open_q_block = "\n".join(f"  - {q}" for q in dna.open_questions[:5]) or "  (none)"

        msg = (
            f"## {dna.name}\n\n"
            f"**Type:** {dna.venture_type} | **Stage:** {dna.stage} | "
            f"**Status:** {dna.status} | **Language:** {dna.language}\n"
            f"**Confidence:** {dna.confidence_level:.0%} | "
            f"**Autonomy:** {dna.autonomy_level}/4\n\n"
            f"**Goals:**\n{goals_block}\n\n"
            f"**Key Insights:**\n{insights_block}\n\n"
            f"**Open Questions:**\n{open_q_block}\n\n"
            f"```\n{dna.render_cvs()}\n```\n\n"
            f"```\n{pulse.render()}\n```\n\n"
            f"**SurfSense spaces:** `{dna.surfsense_dna_space_name}` + `{dna.surfsense_ops_space_name}`\n"
            f"**Resources:** {len(dna.resources)} connected | "
            f"**Research snapshots:** {len(dna.research_snapshots)}"
        )
        return Response(message=msg, break_loop=False)

    async def _health(self, venture_name: str) -> Response:
        dna = self._load_venture(venture_name)
        if not dna:
            return self._not_found(venture_name)

        from python.helpers.cortex_outcome_ledger import get_ledger
        ledger = get_ledger(self.agent)
        pulse = dna.compute_health_pulse(
            open_decisions_count=ledger.open_decisions_count(dna.venture_id),
            outcomes_count=ledger.outcomes_count(dna.venture_id),
        )
        return Response(message=f"```\n{pulse.render()}\n```", break_loop=False)

    async def _activate(self, venture_name: str) -> Response:
        dna = self._load_venture(venture_name)
        if not dna:
            return self._not_found(venture_name)

        self.agent.set_data("active_venture", dna.venture_id)
        self.agent.set_data("active_venture_name", dna.name)
        dna.last_visited_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()
        from python.helpers.cortex_venture_dna import save_venture
        save_venture(dna, self.agent)

        return Response(
            message=f"Venture **{dna.name}** is now active. "
                    f"CVS: {dna.cvs_score.composite_cvs():.1f} [{dna.cvs_score.verdict()}]",
            break_loop=False,
        )

    async def _deactivate(self) -> Response:
        self.agent.set_data("active_venture", None)
        self.agent.set_data("active_venture_name", None)
        return Response(message="Active venture cleared.", break_loop=False)

    async def _delete(self, venture_name: str) -> Response:
        from python.helpers.cortex_venture_dna import delete_venture
        deleted = delete_venture(venture_name, self.agent)
        if deleted:
            # Clear active if it was this venture
            if self.agent.get_data("active_venture_name") == venture_name:
                self.agent.set_data("active_venture", None)
                self.agent.set_data("active_venture_name", None)
            return Response(message=f"Venture '{venture_name}' deleted.", break_loop=False)
        return self._not_found(venture_name)

    async def _cvs(self, venture_name: str) -> Response:
        dna = self._load_venture(venture_name)
        if not dna:
            return self._not_found(venture_name)
        return Response(message=f"```\n{dna.render_cvs()}\n```", break_loop=False)

    async def _kelly(self, venture_name: str) -> Response:
        dna = self._load_venture(venture_name)
        if not dna:
            return self._not_found(venture_name)

        from python.helpers.cortex_outcome_ledger import get_ledger
        ledger = get_ledger(self.agent)
        signal = ledger.compute_kelly_signal(dna.venture_id)
        if signal.impressions == 0:
            return Response(
                message=f"No outcome data yet for '{dna.name}'. Log revenue/cost events first.",
                break_loop=False,
            )
        return Response(message=f"```\n{signal.render()}\n```", break_loop=False)

    def _load_venture(self, venture_name: str):
        """Load by name or fall back to active venture."""
        from python.helpers.cortex_venture_dna import load_venture, list_ventures

        if venture_name:
            return load_venture(venture_name, self.agent)

        # Try active venture
        active_name = self.agent.get_data("active_venture_name")
        if active_name:
            return load_venture(active_name, self.agent)

        # Last resort: most recently modified
        ventures = list_ventures(self.agent)
        return ventures[0] if ventures else None

    def _not_found(self, venture_name: str) -> Response:
        return Response(
            message=f"Venture '{venture_name}' not found. Use venture_manage action='list' to see all ventures.",
            break_loop=False,
        )
