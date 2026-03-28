"""
CORTEX Venture Context Injection (Phase C — C-6)
==================================================

Fires at monologue_start. If a venture is active, injects a 200-token DNA
summary into extras_persistent["cortex_venture_context"].

Ensures CORTEX always knows which venture is active and its key facts,
without reading the full DNA on every turn (only loads what it needs).
"""

from python.cortex.extension import Extension
from python.cortex.loop_data import LoopData


class CortexVentureContextLoad(Extension):
    async def execute(self, loop_data: LoopData = None, **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        active_venture_name = agent.get_data("active_venture_name") or ""
        active_venture_id = agent.get_data("active_venture") or ""

        if not active_venture_name and not active_venture_id:
            # No active venture — clear any stale context
            if loop_data and hasattr(loop_data, "extras_persistent"):
                loop_data.extras_persistent.pop("cortex_venture_context", None)
            return

        try:
            from python.helpers.cortex_venture_dna import load_venture
            dna = load_venture(active_venture_name or active_venture_id, agent)
            if not dna:
                return

            summary = dna.brief_summary(max_chars=200)
            cvs = dna.cvs_score.composite_cvs()
            open_q_count = len(dna.open_questions)

            context_block = (
                f"[ACTIVE VENTURE]\n"
                f"{summary}\n"
                f"Open questions: {open_q_count} | "
                f"AI Setup Autonomy: {dna.cvs_score.ai_setup_autonomy:.0f}% | "
                f"AI Run Autonomy: {dna.cvs_score.ai_run_autonomy:.0f}%\n"
                f"SurfSense spaces: {dna.surfsense_dna_space_name}, {dna.surfsense_ops_space_name}"
            )

            if loop_data and hasattr(loop_data, "extras_persistent"):
                loop_data.extras_persistent["cortex_venture_context"] = context_block

        except Exception:
            pass
