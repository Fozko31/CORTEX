from python.cortex.extension import Extension
from python.cortex.loop_data import LoopData


class CortexTrustRefresh(Extension):

    async def execute(self, system_prompt: list[str], loop_data, **kwargs):
        agent = self.agent
        if not agent or not agent.config:
            return

        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        try:
            from python.helpers.cortex_trust_engine import TrustEngine

            engine = TrustEngine.load(agent)
            agent.set_data("cortex_trust_levels", engine.format_for_prompt())

        except Exception:
            pass
