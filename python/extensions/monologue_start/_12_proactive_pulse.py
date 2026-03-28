"""
_12_proactive_pulse.py — Run the proactive pulse on a 30-minute throttle.

Fires run_proactive_pulse() in the background if 30+ minutes have passed since
the last pulse. Results are stored in agent.set_data("cortex_awareness_feed")
and surfaced to CORTEX by _22_proactive_awareness.py at message_loop_prompts_after.

Runs asynchronously via asyncio.ensure_future so it doesn't block the monologue.
"""

import asyncio
import time

from python.cortex.extension import Extension

_PULSE_INTERVAL_SECS = 1800  # 30 minutes


class CortexProactivePulse(Extension):
    async def execute(self, **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex"):
            return

        try:
            # Throttle: only fire if interval has elapsed
            last_pulse = agent.get_data("cortex_last_pulse_ts") or 0
            now = time.time()
            if now - last_pulse < _PULSE_INTERVAL_SECS:
                return

            # Mark fired immediately to prevent double-fire in concurrent monologues
            agent.set_data("cortex_last_pulse_ts", now)

            # Run in background so monologue is not blocked
            from python.helpers.cortex_proactive_engine import run_proactive_pulse
            asyncio.ensure_future(run_proactive_pulse(agent))

        except Exception:
            pass
