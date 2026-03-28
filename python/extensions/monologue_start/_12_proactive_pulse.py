"""
_12_proactive_pulse.py — Run the proactive pulse on a 30-minute throttle.

Fires run_proactive_pulse() in the background if 30+ minutes have passed since
the last pulse. Results are stored in CortexState.for_agent(agent).set("cortex_awareness_feed")
and surfaced to CORTEX by _22_proactive_awareness.py at message_loop_prompts_after.

Runs asynchronously via asyncio.ensure_future so it doesn't block the monologue.
"""

import asyncio
import time

from python.cortex.extension import Extension
from python.cortex.state import CortexState
from python.cortex.config import CortexConfig

_PULSE_INTERVAL_SECS = 1800  # 30 minutes


class CortexProactivePulse(Extension):
    async def execute(self, **kwargs) -> None:
        agent = self.agent
        profile = CortexConfig.from_agent_config(agent.config).profile
        if not profile.startswith("cortex"):
            return

        try:
            # Throttle: only fire if interval has elapsed
            last_pulse = CortexState.for_agent(agent).get("cortex_last_pulse_ts") or 0
            now = time.time()
            if now - last_pulse < _PULSE_INTERVAL_SECS:
                return

            # Mark fired immediately to prevent double-fire in concurrent monologues
            CortexState.for_agent(agent).set("cortex_last_pulse_ts", now)

            # Run in background so monologue is not blocked
            from python.helpers.cortex_proactive_engine import run_proactive_pulse
            asyncio.ensure_future(run_proactive_pulse(agent))

        except Exception:
            pass
