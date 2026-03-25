# Fix 9: Tool state moved to message_loop_prompts_after/_19_cortex_tool_state.py
# Injected per-turn with change detection (~100 token savings on unchanged turns).
# This file is kept as a no-op to avoid breaking extension discovery.
from python.helpers.extension import Extension
from agent import LoopData


class CortexToolStatePrompt(Extension):
    async def execute(self, **kwargs):
        pass
