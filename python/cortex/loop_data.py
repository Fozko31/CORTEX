"""
python/cortex/loop_data.py — LoopData (Prompt Injection State)
==============================================================
Re-exports AZ's LoopData during H1 transition.

LoopData is defined in agent.py and references AZ's history types
(history.Message, history.MessageContent). Full ownership moves here in H4
when we replace the conversation loop.

CORTEX code imports:
    from python.cortex.loop_data import LoopData

Key attributes used by CORTEX extensions:
    loop_data.extras_persistent  — OrderedDict[str, MessageContent]
        Persists across all iterations of a monologue turn.
        Used by: _17_personality_model, _20_surfsense_pull, _22_proactive_awareness, etc.
    loop_data.extras_temporary   — OrderedDict[str, MessageContent]
        Cleared each iteration. Used for per-loop ephemeral injections.
    loop_data.iteration          — int, current loop iteration number
    loop_data.last_response      — str, last LLM response text
"""
from agent import LoopData  # re-export; replaced in H4

__all__ = ["LoopData"]
