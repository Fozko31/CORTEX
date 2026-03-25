from python.helpers.extension import Extension


class CortexMemorySync(Extension):

    async def execute(self, **kwargs) -> None:
        agent = self.agent
        if not agent or not agent.config or not agent.context:
            return

        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        subdir = getattr(agent.config, "memory_subdir", "") or ""
        if subdir and subdir != "default":
            agent.context.config.memory_subdir = subdir
