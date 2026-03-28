"""
_62_tool_usage_log.py — Logs tool calls from each monologue turn to SQLite.

Runs at monologue_end. Reads tool call records set by the agent during the turn,
then flushes them to cortex_event_store. Falls through silently on any error.
"""

from python.cortex.extension import Extension
from python.cortex.loop_data import LoopData
from python.cortex.state import CortexState


class CortexToolUsageLog(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        try:
            from python.helpers import cortex_event_store as es
            session_id = str(getattr(agent, "id", ""))

            # Read tool calls accumulated during this turn via agent data
            tool_calls = CortexState.for_agent(agent).get("cortex_tool_calls_this_turn") or []

            for call in tool_calls:
                es.log_tool_call(
                    tool_name=call.get("name", "unknown"),
                    success=call.get("success", True),
                    duration_ms=call.get("duration_ms", 0),
                    session_id=session_id,
                )

            # Clear accumulator
            if tool_calls:
                CortexState.for_agent(agent).set("cortex_tool_calls_this_turn", [])

            # Also try to extract from recent history (best-effort)
            _log_from_history(agent, session_id, es)

        except Exception:
            pass


def _log_from_history(agent, session_id: str, es) -> None:
    """
    Best-effort: scan the last few history messages for tool_use content.
    Agent Zero messages may expose tool name in content blocks.
    """
    try:
        history = agent.history
        if not history:
            return

        # Look at last message only — avoid double-counting older turns
        last = history[-1]
        content = ""
        if hasattr(last, "output_text"):
            content = last.output_text()
        elif hasattr(last, "content"):
            content = str(last.content)

        # Detect tool call patterns in content (Agent Zero wraps tool names)
        import re
        tool_pattern = re.compile(r'"tool_name"\s*:\s*"([^"]+)"', re.IGNORECASE)
        found = tool_pattern.findall(content)
        for name in set(found):
            es.log_tool_call(tool_name=name, success=True, session_id=session_id)
    except Exception:
        pass
