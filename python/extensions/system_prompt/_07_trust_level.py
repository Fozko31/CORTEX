from python.cortex.extension import Extension
from python.cortex.loop_data import LoopData
from python.cortex.state import CortexState
from python.cortex.config import CortexConfig


class CortexTrustRefresh(Extension):

    async def execute(self, system_prompt: list[str], loop_data, **kwargs):
        agent = self.agent
        if not agent or not agent.config:
            return

        profile = CortexConfig.from_agent_config(agent.config).profile
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        try:
            from python.helpers.cortex_trust_engine import TrustEngine

            engine = TrustEngine.load(agent)
            CortexState.for_agent(agent).set("cortex_trust_levels", engine.format_for_prompt())

        except Exception:
            pass
