"""
_64_latency_log.py — Log monologue turn count to cortex_event_store latency_events.

Runs at the end of every monologue to capture how many history turns this
task type required. Feeds Loop 3 latency hotspot analysis.

Turn count is a proxy for task complexity/latency — a task requiring 8+ turns
before resolution is a latency hotspot regardless of wall-clock time.
"""

from python.helpers.extension import Extension


# Tasks that are clearly internal plumbing — don't log these
_SKIP_PATTERNS = (
    "cortex_register_scheduler",
    "cortex_weekly_digest",
    "cortex_memory_backup",
    "cortex_proactive",
)


def _classify_task_type(agent) -> str:
    """Infer task type from recent message content."""
    try:
        if agent.history:
            for msg in reversed(agent.history[-4:]):
                content = ""
                if isinstance(msg, dict):
                    content = str(msg.get("content", "")).lower()
                elif hasattr(msg, "content"):
                    content = str(msg.content).lower()

                if any(w in content for w in ("venture", "business", "startup", "market")):
                    return "venture_analysis"
                if any(w in content for w in ("research", "search", "find", "look up")):
                    return "research"
                if any(w in content for w in ("strategy", "plan", "how should", "recommend")):
                    return "strategic_advice"
                if any(w in content for w in ("price", "pricing", "cost", "revenue")):
                    return "pricing_research"
                if any(w in content for w in ("code", "python", "function", "bug", "error")):
                    return "code_task"
                if any(w in content for w in ("telegram", "voice", "send", "notify")):
                    return "communication"
    except Exception:
        pass
    return "general"


def _count_turns(agent) -> int:
    """Count turns in the current monologue (since last user message)."""
    try:
        history = agent.history
        if not history:
            return 0
        # Count from the last user message forward
        turn_count = 0
        for msg in reversed(history):
            msg_role = ""
            if isinstance(msg, dict):
                msg_role = msg.get("role", "")
            elif hasattr(msg, "role"):
                msg_role = str(msg.role)
            turn_count += 1
            if msg_role == "user" and turn_count > 1:
                break
        return max(1, turn_count - 1)
    except Exception:
        return 1


class CortexLatencyLog(Extension):
    async def execute(self, **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex"):
            return

        try:
            task_type = _classify_task_type(agent)
            turn_count = _count_turns(agent)

            # Skip trivial single-turn exchanges and internal tasks
            if turn_count < 2:
                return

            from python.helpers import cortex_event_store as es
            session_id = str(getattr(agent, "id", ""))
            es.log_latency(
                task_type=task_type,
                turn_count=turn_count,
                session_id=session_id,
            )
        except Exception:
            pass
