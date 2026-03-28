from python.cortex.extension import Extension
from python.helpers.defer import DeferredTask, THREAD_BACKGROUND
from python.cortex.loop_data import LoopData


class CortexGraphitiUpdate(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        graphiti_url = getattr(agent.config, "cortex_graphiti_url", "") or ""
        if not graphiti_url:
            return

        log_item = agent.context.log.log(  # H2: replace with CortexLogger when AZ UI removed
            type="util",
            heading="CORTEX Graphiti update",
            content="Forwarding extracted knowledge to temporal graph...",
        )

        task = DeferredTask(thread_name=THREAD_BACKGROUND)
        task.start_task(_update_graphiti, agent, log_item)


async def _update_graphiti(agent, log_item):
    try:
        from python.helpers.cortex_graphiti_client import CortexGraphitiClient

        client = CortexGraphitiClient.from_agent_config(agent)
        if not client.is_configured():
            return

        is_healthy = await client.health_check()
        if not is_healthy:
            log_item.update(content="Graphiti not reachable, skipping L2 update.")
            return

        history_text = agent.concat_messages(agent.history) if agent.history else ""
        if not history_text.strip():
            return

        recent = history_text[-3000:] if len(history_text) > 3000 else history_text

        from datetime import datetime
        await client.add_episode(
            text=recent,
            source="cortex_session",
            timestamp=datetime.now(),
        )

        log_item.update(content="Graphiti L2 updated with latest extraction.")

        try:
            from python.helpers.cortex_self_model import CortexSelfModel
            self_model = CortexSelfModel.load(agent)
            self_model.update_capability("knowledge_retrieval", True)
            self_model.save(agent)
        except Exception:
            pass

        await client.close()

    except Exception as e:
        from python.helpers import errors
        log_item.update(content=f"Graphiti update failed: {errors.format_error(e)}")
