"""
cortex_voice_cleaner.py — DeepSeek V3.2 STT Cleanup Layer
===========================================================
Removes STT artifacts from raw transcripts without changing meaning.

What it fixes:
  - Filler words / discourse markers (Slovenian + English)
  - False starts ("I want— I want to say" → "I want to say")
  - Self-corrections ("pojdi na— na stran" → "pojdi na stran")
  - Repeated words from disfluency ("the the report" → "the report")
  - Stuttered syllables ("I w-w-want" → "I want")

What it does NOT do:
  - Change meaning or rephrase
  - Add punctuation that wasn't implied
  - Translate
  - Summarize
"""

import os
import re
from typing import Optional

import httpx
from python.cortex.config import CortexConfig


# ---------------------------------------------------------------------------
# Filler / artifact patterns for pre-processing (fast regex pass)
# ---------------------------------------------------------------------------

# Slovenian discourse markers and fillers
_SL_FILLERS = (
    r"\bno\b",           # "no" (Slov.), not "no" (Eng.) — context handled by lang detection
    r"\btorej\b",
    r"\bpač\b",
    r"\bpač\b",
    r"\baja\b",
    r"\boziroma\b",      # "oziroma" used as filler at sentence start
    r"\bpravi\b(?=\s+pravi\b)",   # repeated "pravi pravi" → "pravi"
    r"\bsaj\b(?=\s+saj\b)",
    r"\bhm+\b",
    r"\bmmm+\b",
    r"\beh+\b",
)

# English discourse markers and fillers
_EN_FILLERS = (
    r"\buh+\b",
    r"\bum+\b",
    r"\blike\b(?=\s+like\b)",     # repeated "like like"
    r"\byou know\b",
    r"\bI mean\b",
    r"\bbasically\b(?=\s+basically\b)",
    r"\bactually\b(?=\s+actually\b)",
    r"\bsorry\b(?=\s+sorry\b)",
    r"\bso\b(?=\s+so\b)",
)

_FILLER_RE = re.compile(
    "|".join(_SL_FILLERS + _EN_FILLERS),
    re.IGNORECASE,
)

# Repeated-word disfluency: "the the" → "the"
_REPEAT_RE = re.compile(
    r"\b(\w{2,})\s+\1\b",
    re.IGNORECASE,
)

# False-start em-dash or mid-word break: "pojdi na— na" → "pojdi na"
_FALSE_START_RE = re.compile(
    r"\b(\w+)[-–—]+\s+\1\b",
    re.IGNORECASE,
)

# Stuttered syllables: "w-w-want" → "want" (grab last segment)
_STUTTER_RE = re.compile(
    r"\b(?:\w+-)+(\w{3,})\b"
)


def _regex_cleanup(text: str) -> str:
    """Fast regex pass — catches the obvious patterns before LLM call."""
    text = _FILLER_RE.sub("", text)
    text = _FALSE_START_RE.sub(r"\1", text)
    text = _REPEAT_RE.sub(r"\1", text)
    text = _STUTTER_RE.sub(r"\1", text)
    # Collapse multiple spaces
    text = re.sub(r"  +", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# LLM cleanup via DeepSeek V3.2 (through OpenRouter)
# ---------------------------------------------------------------------------

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEEPSEEK_MODEL = "deepseek/deepseek-chat-v3-0324"   # DeepSeek V3.2 on OpenRouter

_SYSTEM_PROMPT = """\
You are a transcript cleaner. Your only job is to remove speech disfluencies from a raw speech-to-text transcript.

Rules:
1. Remove filler words: uh, um, er, hm, mmm, you know, I mean, basically, pač, torej, aja, no (when used as discourse marker)
2. Remove false starts: if the speaker restarts a phrase, keep only the completed version
3. Remove self-corrections: keep the correction, drop the mistake
4. Remove stuttered syllables and repeated words
5. Fix run-together words only if obviously wrong
6. Do NOT change meaning, rephrase, summarize, or translate
7. Do NOT add punctuation that isn't already implied
8. Return ONLY the cleaned transcript — no explanation, no metadata, no quotes

Language note: the transcript may be Slovenian, English, or a mix. Handle both equally.\
"""


class CortexVoiceCleaner:
    """
    Two-pass STT artifact remover.

    Pass 1: fast regex (fillers, repeats, stutters, false starts)
    Pass 2: DeepSeek V3.2 LLM for anything regex can't catch

    Usage:
        cleaner = CortexVoiceCleaner.from_env()
        clean = await cleaner.clean(raw_transcript)
    """

    def __init__(self, api_key: str, skip_llm: bool = False):
        """
        Args:
            api_key:  OpenRouter API key.
            skip_llm: If True, only run the regex pass (useful for testing / cost control).
        """
        self._api_key = api_key
        self._skip_llm = skip_llm

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "CortexVoiceCleaner":
        key = os.getenv("API_KEY_OPENROUTER", "")
        return cls(api_key=key)

    @classmethod
    def from_agent_config(cls, agent) -> "CortexVoiceCleaner":
        key = ""
        try:
            if agent and hasattr(agent, "config"):
                key = CortexConfig.from_agent_config(agent.config).get_api_key("API_KEY_OPENROUTER") or ""
        except Exception:
            pass
        if not key:
            key = os.getenv("API_KEY_OPENROUTER", "")
        return cls(api_key=key)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def clean(self, raw: str, language_hint: Optional[str] = None) -> str:
        """
        Clean a raw STT transcript.

        Args:
            raw:           Raw transcript from Soniox (or any STT engine).
            language_hint: "sl" / "en" — helps regex selection. If None, both sets run.

        Returns:
            Cleaned transcript string.
        """
        if not raw or not raw.strip():
            return raw

        # Pass 1: regex
        after_regex = _regex_cleanup(raw)

        # If nothing left to clean or LLM disabled, return early
        if self._skip_llm or not self._api_key:
            return after_regex

        # Pass 2: LLM (only if transcript is non-trivial)
        if len(after_regex.split()) < 4:
            return after_regex

        cleaned = await self._llm_clean(after_regex)
        return cleaned.strip() if cleaned else after_regex

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _llm_clean(self, text: str) -> str:
        """Send text to DeepSeek V3.2 via OpenRouter for cleanup."""
        payload = {
            "model": _DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.0,
            "max_tokens": max(len(text.split()) * 2, 256),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://cortex.local",
            "X-Title": "CORTEX Voice Cleaner",
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(_OPENROUTER_URL, json=payload, headers=headers)

            if resp.status_code != 200:
                # Degrade gracefully — return the regex-cleaned version
                return text

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return text
            return choices[0]["message"]["content"]

        except Exception:
            # Never crash the voice pipeline over cleanup failure
            return text
