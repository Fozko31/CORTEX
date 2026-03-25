"""
Graphiti (L2) consciousness pull.

Queries Zep Cloud's temporal knowledge graph for semantically relevant
episodes, facts, and entity relationships based on the current user message.
This is the "neuron memory" layer — graph edges represent knowledge that
has been extracted across all past sessions, with temporal context.

Fires before SurfSense pull (_20) — graph memory is faster and more targeted.
Result is injected into extras_persistent["cortex_graph_memory"].
"""
from python.helpers.extension import Extension
from agent import LoopData


_MIN_MESSAGE_LENGTH = 15
_RESULT_LIMIT = 8

# Trivial one-word acknowledgements — not worth a Zep API call
_TRIVIAL_PHRASES = frozenset({
    "hi", "hello", "hey", "ok", "okay", "sure", "yes", "no", "thanks",
    "thank you", "got it", "great", "good", "nice", "cool", "perfect",
    "continue", "go on", "proceed", "next", "done", "stop", "bye",
})


class CortexGraphitiPull(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        graphiti_url = getattr(agent.config, "cortex_graphiti_url", "") or ""
        if not graphiti_url:
            return

        try:
            query = ""
            if loop_data.user_message:
                query = loop_data.user_message.output_text()
            if not query or len(query.strip()) < _MIN_MESSAGE_LENGTH:
                return

            # Skip trivial acknowledgements — saves Zep API calls
            stripped = query.strip().lower().rstrip(".,!?")
            if stripped in _TRIVIAL_PHRASES:
                return

            from python.helpers.cortex_graphiti_client import CortexGraphitiClient
            client = CortexGraphitiClient.from_agent_config(agent)
            if not client.is_configured():
                return

            results = await client.search(query=query, limit=_RESULT_LIMIT)
            if not results:
                return

            # Filter out empty/low-signal results
            useful = [r for r in results if r.content and len(r.content) > 10]
            if not useful:
                return

            lines = []
            for r in useful[:_RESULT_LIMIT]:
                if r.entity and r.related_entity:
                    lines.append(
                        f"• {r.entity} → {r.relationship} → {r.related_entity}"
                        + (f"\n  {r.content}" if r.content != r.relationship else "")
                    )
                else:
                    lines.append(f"• {r.content}")

            context = "\n".join(lines)
            loop_data.extras_persistent["cortex_graph_memory"] = (
                f"## CORTEX Graph Memory (L2 — Zep)\n{context}"
            )
            # Clear any previous down-alert now that Zep is responding
            agent.set_data("cortex_l2_down_alerted", False)

            await client.close()

        except Exception as e:
            from python.helpers import errors
            agent.context.log.log(
                type="warning",
                heading="CORTEX Graphiti pull failed",
                content=errors.format_error(e),
            )
            # Inject a one-time service alert so CORTEX can inform the user
            if not agent.get_data("cortex_l2_down_alerted"):
                agent.set_data("cortex_l2_down_alerted", True)
                loop_data.extras_persistent["cortex_service_status"] = (
                    "⚠️ SERVICE ALERT: Zep Cloud (L2 graph memory) is currently unreachable. "
                    "You are operating on L1 FAISS only this session. "
                    "Briefly inform the user that L2 is offline."
                )
