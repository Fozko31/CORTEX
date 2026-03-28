"""
cortex_kokoro_tts.py — Kokoro TTS (English, local inference)
=============================================================
Synthesizes English speech using the Kokoro ONNX model locally.
CPU-viable for async Telegram push (not real-time streaming).

Why Kokoro:
  - StyleTTS2-based, high quality English
  - Local inference — zero cost, zero API calls
  - kokoro-onnx Python package, CPU-acceptable latency
  - English only — Slovenian routes to Azure Neural TTS

Requires:
  pip install kokoro-onnx soundfile
  (model auto-downloaded on first use via kokoro-onnx)

Voice IDs (default: af_heart — American English female):
  af_heart, af_sky, am_adam, am_michael, bf_emma, bm_george
  See: https://huggingface.co/hexgrad/Kokoro-82M
"""

import io
import os
from typing import Optional


# Default voice — American English female, warm tone
_DEFAULT_VOICE = "af_heart"

# Default sample rate from Kokoro
_SAMPLE_RATE = 24_000


class KokoroError(Exception):
    """Raised when Kokoro synthesis fails."""


class CortexKokoroTTS:
    """
    Local Kokoro TTS synthesizer for English.

    Usage:
        tts = CortexKokoroTTS()
        wav_bytes = await tts.synthesize("Good morning, here is your digest.")
    """

    def __init__(self, voice: str = _DEFAULT_VOICE):
        self._voice = voice
        self._pipeline = None   # lazy-loaded on first call

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> "CortexKokoroTTS":
        voice = os.getenv("KOKORO_VOICE", _DEFAULT_VOICE)
        return cls(voice=voice)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """
        Synthesize English text to WAV bytes.

        Args:
            text:  English text to speak.
            voice: Kokoro voice ID override. Uses instance default if None.

        Returns:
            WAV audio bytes (24kHz, mono, float32).

        Raises:
            KokoroError if synthesis fails.
        """
        import asyncio
        import functools

        voice_id = voice or self._voice
        loop = asyncio.get_event_loop()
        # Kokoro inference is CPU-bound — run in executor to avoid blocking
        wav_bytes = await loop.run_in_executor(
            None,
            functools.partial(self._synthesize_sync, text, voice_id),
        )
        return wav_bytes

    def is_available(self) -> bool:
        """Return True if kokoro-onnx is installed."""
        try:
            import kokoro  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Internal (sync — runs in executor)
    # ------------------------------------------------------------------

    def _synthesize_sync(self, text: str, voice_id: str) -> bytes:
        """Blocking Kokoro synthesis — called from run_in_executor."""
        try:
            import soundfile as sf
            from kokoro import KPipeline
        except ImportError as e:
            raise KokoroError(
                "kokoro-onnx or soundfile not installed. "
                "Run: pip install kokoro-onnx soundfile"
            ) from e

        # Lazy-initialize the pipeline (expensive; only done once)
        if self._pipeline is None:
            lang_code = "a"  # American English
            self._pipeline = KPipeline(lang_code=lang_code)

        audio_segments = []
        try:
            generator = self._pipeline(text, voice=voice_id)
            for _, _, audio in generator:
                audio_segments.append(audio)
        except Exception as e:
            raise KokoroError(f"Kokoro synthesis failed: {e}") from e

        if not audio_segments:
            raise KokoroError("Kokoro returned empty audio")

        # Concatenate segments and encode to WAV
        import numpy as np
        combined = np.concatenate(audio_segments)

        buf = io.BytesIO()
        sf.write(buf, combined, _SAMPLE_RATE, format="WAV", subtype="PCM_16")
        buf.seek(0)
        return buf.read()
