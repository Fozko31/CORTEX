"""
cortex_tts_router.py — TTS Language Router
===========================================
Routes text-to-speech synthesis to the correct engine based on:
  1. Per-chat TTS preference (stored in PersonalityModel)
  2. Language detection of the text
  3. Engine availability

Routing logic:
  English text  → Kokoro TTS (local, zero cost)
  Slovenian text → Azure Neural TTS sl-SI (cloud, 0.5M chars free/month)
  Unknown lang  → match_input preference → detected language
  Explicit pref → honor it ("answer in Slovenian" / "odgovori v angleščini")

Preference commands (natural language → stored preference):
  "answer in Slovenian" / "odgovori v slovenščini" → force_sl
  "answer in English" / "odgovori v angleščini"    → force_en
  "match my language" / "match input"               → match_input  (default)

Preference key in PersonalityModel: "tts_language_pref"
Values: "force_sl" | "force_en" | "match_input"
"""

import os
import re
from typing import Optional


# Language detection triggers
_FORCE_SL_RE = re.compile(
    r"(answer|respond|reply|speak|odgovori|govori).{0,20}(sloven|slovensko|slovenščin)",
    re.IGNORECASE,
)
_FORCE_EN_RE = re.compile(
    r"(answer|respond|reply|speak|odgovori|govori).{0,20}(english|angleško|angleščin)",
    re.IGNORECASE,
)
_MATCH_INPUT_RE = re.compile(
    r"(match|use|follow).{0,15}(my language|input|what I (say|speak|write))",
    re.IGNORECASE,
)

# Pref values
PREF_KEY        = "tts_language_pref"
PREF_FORCE_SL   = "force_sl"
PREF_FORCE_EN   = "force_en"
PREF_MATCH_INPUT = "match_input"   # default


class CortexTTSRouter:
    """
    Route TTS synthesis to Kokoro (English) or Azure (Slovenian).

    Usage:
        audio_bytes = await CortexTTSRouter.route(text, language_hint, agent)

    The classmethod interface keeps the call site simple — callers don't need
    to instantiate anything. The router builds the correct engine internally.
    """

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    @classmethod
    async def route(
        cls,
        text: str,
        language_hint: Optional[str] = None,
        agent=None,
    ) -> bytes:
        """
        Synthesize text to audio bytes.

        Args:
            text:          Text to speak.
            language_hint: "sl" | "en" | None (auto-detect).
            agent:         Agent instance for PersonalityModel preference lookup.

        Returns:
            Audio bytes (WAV from Kokoro, MP3 from Azure).
        """
        lang = cls._resolve_language(text, language_hint, agent)

        if lang == "sl":
            return await cls._azure(text, agent)
        else:
            return await cls._kokoro(text, agent)

    # ------------------------------------------------------------------
    # Preference management (called by TelegramBotHandler on command text)
    # ------------------------------------------------------------------

    @classmethod
    def detect_pref_command(cls, text: str) -> Optional[str]:
        """
        Check if a message is a TTS preference command.

        Returns:
            New pref value ("force_sl" / "force_en" / "match_input")
            or None if text is not a pref command.
        """
        if _FORCE_SL_RE.search(text):
            return PREF_FORCE_SL
        if _FORCE_EN_RE.search(text):
            return PREF_FORCE_EN
        if _MATCH_INPUT_RE.search(text):
            return PREF_MATCH_INPUT
        return None

    @classmethod
    def set_pref(cls, new_pref: str, agent) -> bool:
        """
        Persist TTS language preference to PersonalityModel.

        Returns:
            True if saved successfully.
        """
        try:
            from python.helpers.cortex_personality_model import PersonalityModel
            model = PersonalityModel.load(agent)
            model.set_preference(PREF_KEY, new_pref)
            model.save(agent)
            return True
        except Exception:
            return False

    @classmethod
    def get_pref(cls, agent) -> str:
        """
        Read TTS language preference from PersonalityModel.

        Returns:
            Pref value string, or "match_input" if not set.
        """
        try:
            from python.helpers.cortex_personality_model import PersonalityModel
            model = PersonalityModel.load(agent)
            return model.get_preference(PREF_KEY, default=PREF_MATCH_INPUT)
        except Exception:
            return PREF_MATCH_INPUT

    # ------------------------------------------------------------------
    # Internal: language resolution
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_language(
        cls,
        text: str,
        hint: Optional[str],
        agent,
    ) -> str:
        """Determine target language for synthesis."""
        # 1. Check stored preference (always call get_pref — it handles None agent internally)
        pref = cls.get_pref(agent)

        if pref == PREF_FORCE_SL:
            return "sl"
        if pref == PREF_FORCE_EN:
            return "en"

        # 2. match_input → use hint or auto-detect
        if hint in ("sl", "en"):
            return hint

        return _detect_language(text)

    # ------------------------------------------------------------------
    # Internal: engine dispatch
    # ------------------------------------------------------------------

    @classmethod
    async def _kokoro(cls, text: str, agent) -> bytes:
        """Synthesize English via Kokoro (local)."""
        from python.helpers.cortex_kokoro_tts import CortexKokoroTTS, KokoroError
        tts = CortexKokoroTTS.default()
        if not tts.is_available():
            # Fallback to Azure English if Kokoro not installed
            return await cls._azure(text, agent, language="en")
        try:
            return await tts.synthesize(text)
        except KokoroError:
            return await cls._azure(text, agent, language="en")

    @classmethod
    async def _azure(cls, text: str, agent, language: str = "sl") -> bytes:
        """Synthesize via Azure Neural TTS. Returns empty bytes if unavailable (text-only fallback)."""
        from python.helpers.cortex_azure_tts import CortexAzureTTS, AzureTTSError
        tts = CortexAzureTTS.from_agent_config(agent) if agent else CortexAzureTTS.from_env()
        if not tts.is_available():
            # Text-only fallback: return empty bytes — caller sends text response instead
            return b""
        return await tts.synthesize(text, language=language)


# ------------------------------------------------------------------
# Language detection (fast heuristic — not ML, keeps import fast)
# ------------------------------------------------------------------

# Slovenian-specific characters and common words
_SL_MARKERS = re.compile(
    r"[čšžČŠŽ]|"
    r"\b(je|in|da|so|se|za|na|pri|po|iz|do|kot|ali|ker|če|bo|bi|ima|smo|ste|so|tudi|"
    r"dobro|jutro|hvala|prosim|lep|dan|pozdravljeni|kdaj|kje|kdo|kaj|kako)\b",
    re.IGNORECASE,
)

_SL_THRESHOLD = 2   # 2+ Slovenian markers → classify as Slovenian


def _detect_language(text: str) -> str:
    """
    Heuristic language detection for Slovenian vs English.
    Returns "sl" or "en".
    """
    matches = _SL_MARKERS.findall(text)
    if len(matches) >= _SL_THRESHOLD:
        return "sl"
    # Try langdetect if available (optional install)
    try:
        from langdetect import detect
        lang = detect(text)
        if lang == "sl":
            return "sl"
    except Exception:
        pass
    return "en"
