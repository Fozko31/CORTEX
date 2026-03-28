"""
_09_correction_detect.py — Detects user correction signals in the incoming message.

Runs at monologue_start (before CORTEX processes the message), after comprehension
check (_08). Logs correction type to SQLite for Loop 3 operational reports.
Falls through silently on any error.
"""

import re
from python.cortex.extension import Extension
from python.cortex.loop_data import LoopData


# Correction signal patterns → correction type label
_CORRECTION_PATTERNS = [
    (re.compile(r"\b(that('s| is) (wrong|incorrect|not right|not what i (said|meant|asked)))\b", re.IGNORECASE), "factual_error"),
    (re.compile(r"\b(you misunderstood|you didn't understand|that's not what i (meant|asked|said|wanted))\b", re.IGNORECASE), "misunderstanding"),
    (re.compile(r"\b(too (generic|vague|general)|not specific enough|be more specific)\b", re.IGNORECASE), "too_generic"),
    (re.compile(r"\b(too (formal|stiff|corporate)|be more (casual|direct|natural))\b", re.IGNORECASE), "wrong_tone"),
    (re.compile(r"\b(wrong (tool|approach|method)|you (should|shouldn't) (have )?used)\b", re.IGNORECASE), "wrong_tool"),
    (re.compile(r"\b(not (relevant|what i needed|helpful)|off topic|missed the point)\b", re.IGNORECASE), "irrelevant"),
    (re.compile(r"\b(that('s| is) not (what i|the) (want|asked|need)|no,? that'?s? not)\b", re.IGNORECASE), "general_correction"),
    (re.compile(r"^(no[,.]?\s+|wrong[,.]?\s+|incorrect[,.]?\s+)", re.IGNORECASE), "general_correction"),
]


class CortexCorrectionDetect(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        try:
            user_msg = ""
            if loop_data.user_message:
                user_msg = loop_data.user_message.output_text() if hasattr(loop_data.user_message, "output_text") else str(loop_data.user_message)

            if not user_msg or len(user_msg) < 4:
                return

            correction_type = _detect_correction(user_msg)
            if not correction_type:
                return

            from python.helpers import cortex_event_store as es
            session_id = str(getattr(agent, "id", ""))
            es.log_correction(
                correction_type=correction_type,
                context_snippet=user_msg[:300],
                session_id=session_id,
            )

        except Exception:
            pass


def _detect_correction(text: str) -> str:
    """Returns correction type label or empty string."""
    for pattern, label in _CORRECTION_PATTERNS:
        if pattern.search(text):
            return label
    return ""
