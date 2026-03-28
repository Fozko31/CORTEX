"""
cortex_azure_tts.py — Azure Neural TTS (Slovenian + English fallback)
======================================================================
Synthesizes speech via Azure Cognitive Services Neural TTS.

Why Azure for Slovenian:
  - sl-SI voices: RokNeural (male), PetraNeural (female)
  - Free tier: 0.5M characters/month — covers all realistic async usage
  - Westeurope region: closest to Slovenia, lowest latency
  - ~400ms TTFB for streaming (future real-time use)

Environment variables:
  AZURE_SPEECH_KEY      — Azure Cognitive Services key
  AZURE_SPEECH_REGION   — e.g. "westeurope" (default)

Voices:
  Slovenian:   sl-SI-RokNeural (male), sl-SI-PetraNeural (female)
  English:     en-US-AriaNeural, en-GB-SoniaNeural

Output format:
  audio-24khz-96kbitrate-mono-mp3 — compatible with Telegram voice notes
"""

import io
import os
from typing import Optional


# Supported voices
VOICES = {
    "sl": {
        "male":   "sl-SI-RokNeural",
        "female": "sl-SI-PetraNeural",
        "default": "sl-SI-RokNeural",
    },
    "en": {
        "male":   "en-US-GuyNeural",
        "female": "en-US-AriaNeural",
        "default": "en-US-AriaNeural",
    },
}

_DEFAULT_REGION = "westeurope"
_OUTPUT_FORMAT  = "audio-24khz-96kbitrate-mono-mp3"


class AzureTTSError(Exception):
    """Raised when Azure TTS returns a non-2xx response."""


class CortexAzureTTS:
    """
    Azure Neural TTS synthesizer.

    Primary use: Slovenian speech (sl-SI voices).
    Also handles English as a fallback when Kokoro is unavailable.

    Usage:
        tts = CortexAzureTTS.from_env()
        mp3_bytes = await tts.synthesize("Dobro jutro.", language="sl")
    """

    def __init__(
        self,
        api_key: str,
        region: str = _DEFAULT_REGION,
        gender: str = "male",
    ):
        self._api_key = api_key
        self._region = region
        self._gender = gender  # "male" | "female"

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "CortexAzureTTS":
        key = os.getenv("AZURE_SPEECH_KEY", "")
        region = os.getenv("AZURE_SPEECH_REGION", _DEFAULT_REGION)
        return cls(api_key=key, region=region)

    @classmethod
    def from_agent_config(cls, agent) -> "CortexAzureTTS":
        key = ""
        region = _DEFAULT_REGION
        try:
            if agent and hasattr(agent, "config"):
                cfg = agent.config
                if hasattr(cfg, "get_api_key"):
                    key = cfg.get_api_key("AZURE_SPEECH_KEY") or ""
                region = os.getenv("AZURE_SPEECH_REGION", _DEFAULT_REGION)
        except Exception:
            pass
        if not key:
            key = os.getenv("AZURE_SPEECH_KEY", "")
        return cls(api_key=key, region=region)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def synthesize(
        self,
        text: str,
        language: str = "sl",
        voice: Optional[str] = None,
    ) -> bytes:
        """
        Synthesize text to MP3 bytes.

        Args:
            text:     Text to synthesize.
            language: "sl" or "en".
            voice:    Full Azure voice name override (e.g. "sl-SI-PetraNeural").

        Returns:
            MP3 audio bytes.

        Raises:
            AzureTTSError if the API call fails.
        """
        import asyncio
        import functools

        voice_name = voice or self._resolve_voice(language)
        ssml = _build_ssml(text, voice_name, language)

        loop = asyncio.get_event_loop()
        mp3_bytes = await loop.run_in_executor(
            None,
            functools.partial(self._synthesize_sync, ssml),
        )
        return mp3_bytes

    def is_available(self) -> bool:
        """Return True if AZURE_SPEECH_KEY is configured."""
        return bool(self._api_key)

    async def health_check(self) -> bool:
        """Verify the key + region are valid by hitting the voices list endpoint."""
        import httpx
        url = f"https://{self._region}.tts.speech.microsoft.com/cognitiveservices/voices/list"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url,
                    headers={"Ocp-Apim-Subscription-Key": self._api_key},
                )
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_voice(self, language: str) -> str:
        lang_voices = VOICES.get(language, VOICES["en"])
        return lang_voices.get(self._gender, lang_voices["default"])

    def _synthesize_sync(self, ssml: str) -> bytes:
        """Blocking Azure TTS call — runs in executor."""
        import httpx

        endpoint = (
            f"https://{self._region}.tts.speech.microsoft.com"
            "/cognitiveservices/v1"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": self._api_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": _OUTPUT_FORMAT,
            "User-Agent": "CORTEX-TTS",
        }

        resp = httpx.post(endpoint, content=ssml.encode("utf-8"), headers=headers, timeout=30)

        if resp.status_code != 200:
            raise AzureTTSError(
                f"Azure TTS failed: HTTP {resp.status_code} — {resp.text[:200]}"
            )
        return resp.content


def _build_ssml(text: str, voice_name: str, language: str) -> str:
    """Build minimal SSML for Azure TTS."""
    lang_tag = "sl-SI" if language == "sl" else "en-US"
    # Escape XML special chars
    safe_text = (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return (
        f'<speak version="1.0" xml:lang="{lang_tag}" '
        f'xmlns="http://www.w3.org/2001/10/synthesis">'
        f'<voice name="{voice_name}">{safe_text}</voice>'
        f"</speak>"
    )
