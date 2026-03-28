from python.cortex.extension import Extension
from python.cortex.loop_data import LoopData


class CortexSelfModelLoad(Extension):
    async def execute(self, **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        try:
            from python.helpers.cortex_self_model import CortexSelfModel
            from python.helpers.cortex_surfsense_router import CortexSurfSenseRouter

            self_model = CortexSelfModel.load(agent)
            self_model.increment_session()
            self_model.save(agent)

            agent.set_data("cortex_self_model", self_model.data)
            agent.set_data("cortex_self_summary", self_model.get_self_summary())

            routing_index = CortexSurfSenseRouter.load_routing_index(agent)
            agent.set_data("cortex_space_index", routing_index)

        except Exception as e:
            from python.helpers import errors
            agent.context.log.log(
                type="warning",
                heading="CORTEX self-model load failed",
                content=errors.format_error(e),
            )
