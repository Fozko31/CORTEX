"""
CORTEX Venture Discover Tool -- Phase D, D-9
=============================================

Agent-callable tool that runs the full discovery pipeline (D-8 orchestrator)
for a given niche and market.

Usage by agent:
    venture_discover(
        niche="local SEO for restaurants",
        market="Slovenia",
        mode="full"          # "full" | "fast" | "scan_only"
        max_cost_eur=0.10    # optional budget cap
    )

Modes:
    full        All steps including D-4 influencer monitoring (~EUR 0.05-0.09)
    fast        Skip influencer monitoring, still runs D-2/D-3/D-5/gates (~EUR 0.02-0.03)
    scan_only   Only disruption scan (D-5) for a tool the agent already has in mind
"""

import json
from python.cortex.tool import Tool, Response
from python.helpers.print_style import PrintStyle


class VentureDiscover(Tool):

    async def execute(
        self,
        niche: str = "",
        market: str = "global",
        mode: str = "fast",
        max_cost_eur: float = 0.5,
        **kwargs,
    ):
        # Resolve args (agent may pass via self.args dict)
        niche = niche or self.args.get("niche", "")
        market = market or self.args.get("market", "global")
        mode = mode or self.args.get("mode", "fast")
        max_cost_eur = float(self.args.get("max_cost_eur", max_cost_eur))

        if not niche:
            return Response(
                message=(
                    "venture_discover requires a `niche` argument. "
                    "Example: venture_discover(niche='local SEO for restaurants', market='Slovenia')"
                ),
                break_loop=False,
            )

        valid_modes = {"full", "fast", "scan_only"}
        if mode not in valid_modes:
            return Response(
                message=f"Invalid mode '{mode}'. Valid modes: {', '.join(sorted(valid_modes))}",
                break_loop=False,
            )

        PrintStyle(font_color="#A8D8A8", bold=True).print(
            f"CORTEX Venture Discover [{mode.upper()}]: '{niche}' | {market} | budget EUR {max_cost_eur:.2f}"
        )

        try:
            from python.helpers.cortex_discovery_orchestrator import run_discovery
            from python.helpers.cortex_discovery_params import VentureDiscoveryParameters

            params = VentureDiscoveryParameters.load() or VentureDiscoveryParameters()
            skip_influencers = (mode != "full")

            result = await run_discovery(
                niche=niche,
                market=market,
                params=params,
                agent=self.agent,
                skip_influencers=skip_influencers,
                max_cost_eur=max_cost_eur,
            )

            return Response(
                message=_format_result(result),
                break_loop=False,
            )

        except Exception as e:
            return Response(
                message=f"venture_discover failed: {e}",
                break_loop=False,
            )


def _format_result(result) -> str:
    """Format DiscoveryResult into a concise agent-readable summary."""
    lines = [
        f"## Venture Discovery: '{result.niche}' | {result.market}",
        f"**Outcome:** {result.outcome.upper()}",
        f"**Reason:** {result.reason}",
        "",
    ]

    if result.final_score is not None:
        lines.append(f"**CVS Score:** {result.final_score:.1f}/100")
    if result.strategy_type:
        lines.append(f"**Strategy:** {result.strategy_type}")

    lines.append(f"**Signals collected:** {len(result.signals)}")
    if result.clusters:
        lines.append(f"**Pain clusters:** {len(result.clusters)}")

    if result.pain_summary:
        lines += ["", "**Pain Summary:**", result.pain_summary]

    if result.disruption_summary:
        lines += ["", "**Disruption Targets:**", result.disruption_summary]

    if result.candidate:
        lines += ["", f"**Candidate ID:** {result.candidate.id} (use this to accept or park)"]

    lines += [
        "",
        f"**Steps:** {', '.join(result.steps_completed)}",
        f"**Skipped:** {', '.join(result.steps_skipped) or 'none'}",
        f"**Est. cost:** EUR {result.cost_estimate_eur:.4f}",
    ]

    if result.errors:
        lines += ["", f"**Warnings:** {'; '.join(result.errors[:3])}"]

    return "\n".join(lines)
