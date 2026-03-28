"""
CORTEX Discovery Context Injection -- D-10
==========================================

Injects a brief venture discovery queue summary into the system prompt
so the agent always knows the current pipeline state without querying files.

Kept deliberately brief: queue size, top candidate, parked count.
Full details are available via venture_discover tool on demand.
"""

from python.cortex.extension import Extension


class CortexDiscoveryContext(Extension):

    async def execute(self, system_prompt: list = [], **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex"):
            return

        try:
            from python.helpers.cortex_discovery_params import (
                load_queue,
                load_parked,
                load_accepted,
                VentureDiscoveryParameters,
            )

            queue = load_queue()
            parked = load_parked()
            accepted = load_accepted()

            if not queue and not parked and not accepted:
                # No discovery activity yet — inject minimal hint
                system_prompt.append(
                    "\n## Venture Discovery Pipeline\n"
                    "No ventures in queue yet. Use `venture_discover` to start discovery.\n"
                )
                return

            lines = ["\n## Venture Discovery Pipeline"]

            if queue:
                top = queue[0]
                lines.append(
                    f"**Queue:** {len(queue)} candidate(s) pending review. "
                    f"Top: '{top.niche}' — {top.market} "
                    f"(score {top.cvs_prescore:.0f}/100"
                    + (f", strategy: {top.strategy_type}" if top.strategy_type else "")
                    + f", id: {top.id})"
                )
            else:
                lines.append("**Queue:** Empty")

            if parked:
                lines.append(f"**Parked:** {len(parked)} (use venture status to review)")

            if accepted:
                lines.append(f"**Accepted:** {len(accepted)} venture(s) proceeding")

            # Active niche targets from params
            try:
                params = VentureDiscoveryParameters.load()
                if params and params.target_niches:
                    lines.append(
                        f"**Active targets:** {', '.join(params.target_niches[:3])}"
                        + ("…" if len(params.target_niches) > 3 else "")
                    )
            except Exception:
                pass

            lines.append("")
            system_prompt.append("\n".join(lines))

        except Exception:
            pass  # Non-blocking — never crash system prompt construction
