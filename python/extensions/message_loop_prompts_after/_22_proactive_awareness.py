"""
_22_proactive_awareness.py — Inject unread proactive findings into prompt context.

Reads from CortexState.for_agent(agent).get("cortex_awareness_feed") (populated by run_proactive_pulse)
and injects up to 3 unread findings into the current message loop prompt so CORTEX
can surface them naturally in its next response.

Marks findings as read after injection to avoid repeat surfacing.
"""

from python.cortex.extension import Extension
from python.cortex.loop_data import LoopData
from python.cortex.state import CortexState


class CortexProactiveAwareness(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex"):
            return

        try:
            feed = CortexState.for_agent(agent).get("cortex_awareness_feed") or []
            unread = [f for f in feed if not f.get("read", False)]
            if not unread:
                return

            # Inject up to 3 unread findings
            to_inject = unread[:3]
            lines = ["**Proactive Awareness** — new findings from background scan:"]
            for f in to_inject:
                venture = f.get("venture", "")
                title = f.get("title", "")
                summary = f.get("summary", "")
                label = f"[{venture}] " if venture else ""
                lines.append(f"- {label}{title}: {summary[:200]}")

            # Mark as read
            injected_titles = {f.get("title", "") for f in to_inject}
            for f in feed:
                if f.get("title", "") in injected_titles:
                    f["read"] = True
            CortexState.for_agent(agent).set("cortex_awareness_feed", feed)

            # Inject into loop data extras (persistent so it survives the full loop)
            awareness_text = "\n".join(lines)
            loop_data.extras_persistent["cortex_proactive_awareness"] = awareness_text

        except Exception:
            pass
