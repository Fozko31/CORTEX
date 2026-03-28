from python.cortex.extension import Extension
from python.cortex.loop_data import LoopData
from python.cortex.state import CortexState
from python.cortex.logger import CortexLogger
from python.cortex.config import CortexConfig


class CortexSelfModelLoad(Extension):
    async def execute(self, **kwargs) -> None:
        agent = self.agent
        profile = CortexConfig.from_agent_config(agent.config).profile
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        try:
            from python.helpers.cortex_self_model import CortexSelfModel
            from python.helpers.cortex_surfsense_router import CortexSurfSenseRouter

            self_model = CortexSelfModel.load(agent)
            self_model.increment_session()
            self_model.save(agent)

            CortexState.for_agent(agent).set("cortex_self_model", self_model.data)
            CortexState.for_agent(agent).set("cortex_self_summary", self_model.get_self_summary())

            routing_index = CortexSurfSenseRouter.load_routing_index(agent)
            CortexState.for_agent(agent).set("cortex_space_index", routing_index)

        except Exception as e:
            from python.helpers import errors
            CortexLogger.for_agent(agent).warning("CORTEX self-model load failed", error=errors.format_error(e))
