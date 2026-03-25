"""
Fix 9: Move tool state injection from system_prompt to message_loop_prompts_after.

Injects tool state into extras_persistent only when it has changed.
Saves ~100 tokens/turn on turns where tool state is unchanged (most turns).
"""
import hashlib
from typing import Any
from python.helpers.extension import Extension
from agent import LoopData

_CACHE_KEY = "_cortex_tool_state_hash"
_EXTRAS_KEY = "cortex_tool_state"


class CortexToolStateLoop(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs: Any):
        try:
            from python.helpers.cortex_tool_router import build_tool_state_prompt

            context = build_tool_state_prompt(self.agent)
            if not context:
                return

            state_hash = hashlib.md5(context.encode()).hexdigest()
            cached_hash = self.agent.get_data(_CACHE_KEY)

            if state_hash == cached_hash:
                # State unchanged — extras_persistent already has it from last update
                return

            # State changed (or first run) — update persistent context and cache
            self.agent.set_data(_CACHE_KEY, state_hash)
            loop_data.extras_persistent[_EXTRAS_KEY] = (
                f"## Active Tool State\n{context}"
            )

        except Exception:
            pass
