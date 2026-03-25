from python.helpers.extension import Extension


class CortexRegisterSchedulers(Extension):
    async def execute(self, **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex"):
            return

        try:
            from python.helpers.cortex_weekly_digest import register_weekly_digest_task
            register_weekly_digest_task()
        except Exception:
            pass

        try:
            from python.helpers.cortex_proactive_engine import register_proactive_task
            register_proactive_task()
        except Exception:
            pass
