"""
cortex_soniox_client.py — Soniox STT Client
============================================
Async transcription client for Soniox speech-to-text API.

Why Soniox:
  - Best Slovenian WER at 6.8% (vs Whisper 23.5%, AssemblyAI 55.6%)
  - Pay-as-you-go, ~$0.10/hr async
  - Handles .ogg natively (Telegram voice format)
  - Fallback: Google Chirp_2 (10.8% WER, 14x more expensive — not implemented here)

API reference: https://soniox.com/docs/speech-to-text/api-reference/transcribe-file
"""

import asyncio
import os
import time
from typing import Optional

import httpx
from python.cortex.config import CortexConfig


_SONIOX_BASE = "https://api.soniox.com/v1"
_TRANSCRIBE_URL = f"{_SONIOX_BASE}/transcriptions"
_POLL_INTERVAL = 1.5   # seconds between status polls
_POLL_TIMEOUT  = 120   # seconds before giving up


class SonioxError(Exception):
    """Raised when Soniox returns a non-2xx response or times out."""


class CortexSonioxClient:
    """
    Async Soniox transcription client.

    Usage:
        client = CortexSonioxClient.from_env()
        transcript = await client.transcribe(audio_bytes, language_hint="sl")
    """

    def __init__(self, api_key: str):
        if not api_key:
            raise SonioxError("SONIOX_API_KEY is required")
        self._api_key = api_key
        self._headers = {"Authorization": f"Bearer {api_key}"}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "CortexSonioxClient":
        """Read SONIOX_API_KEY from environment."""
        key = os.getenv("SONIOX_API_KEY", "")
        return cls(api_key=key)

    @classmethod
    def from_agent_config(cls, agent) -> "CortexSonioxClient":
        """
        Read API key from agent vault first, then fall back to env var.
        Keeps credentials out of plain env where possible.
        """
        key = ""
        try:
            if agent and hasattr(agent, "config"):
                key = CortexConfig.from_agent_config(agent.config).get_api_key("SONIOX_API_KEY") or ""
        except Exception:
            pass
        if not key:
            key = os.getenv("SONIOX_API_KEY", "")
        return cls(api_key=key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def transcribe(
        self,
        audio_bytes: bytes,
        language_hint: Optional[str] = None,
        filename: str = "audio.ogg",
    ) -> str:
        """
        Transcribe audio bytes.

        Args:
            audio_bytes:   Raw audio data (ogg, wav, mp3, m4a).
            language_hint: BCP-47 language code, e.g. "sl" or "en".
                           If None, Soniox auto-detects.
            filename:      Hint for MIME type resolution (default "audio.ogg").

        Returns:
            Transcript text string.

        Raises:
            SonioxError on API error or timeout.
        """
        job_id = await self._submit(audio_bytes, language_hint, filename)
        transcript = await self._poll(job_id)
        return transcript

    async def health_check(self) -> bool:
        """
        Verify that the API key is accepted by Soniox.
        Calls GET /transcriptions (expects 200 even with empty list).
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    _TRANSCRIBE_URL,
                    headers=self._headers,
                )
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _submit(
        self,
        audio_bytes: bytes,
        language_hint: Optional[str],
        filename: str,
    ) -> str:
        """Submit audio to Soniox and return the job ID."""
        content_type = _content_type(filename)

        files = {
            "file": (filename, audio_bytes, content_type),
        }
        data: dict = {}
        if language_hint:
            data["language"] = language_hint

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _TRANSCRIBE_URL,
                headers=self._headers,
                files=files,
                data=data,
            )

        if resp.status_code not in (200, 201, 202):
            raise SonioxError(
                f"Soniox submit failed: HTTP {resp.status_code} — {resp.text[:300]}"
            )

        body = resp.json()
        job_id = body.get("id") or body.get("transcription_id")
        if not job_id:
            raise SonioxError(f"Soniox returned no job ID: {body}")
        return job_id

    async def _poll(self, job_id: str) -> str:
        """Poll until the transcription job completes, then return the text."""
        url = f"{_TRANSCRIBE_URL}/{job_id}"
        deadline = time.monotonic() + _POLL_TIMEOUT

        async with httpx.AsyncClient(timeout=15) as client:
            while time.monotonic() < deadline:
                resp = await client.get(url, headers=self._headers)

                if resp.status_code != 200:
                    raise SonioxError(
                        f"Soniox poll failed: HTTP {resp.status_code} — {resp.text[:300]}"
                    )

                body = resp.json()
                status = body.get("status", "").lower()

                if status in ("completed", "succeeded", "done"):
                    return _extract_text(body)

                if status in ("failed", "error"):
                    raise SonioxError(f"Soniox transcription failed: {body.get('error', body)}")

                # Still processing — wait and retry
                await asyncio.sleep(_POLL_INTERVAL)

        raise SonioxError(f"Soniox transcription timed out after {_POLL_TIMEOUT}s (job {job_id})")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _content_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return {
        "ogg":  "audio/ogg",
        "wav":  "audio/wav",
        "mp3":  "audio/mpeg",
        "m4a":  "audio/mp4",
        "flac": "audio/flac",
        "webm": "audio/webm",
    }.get(ext, "application/octet-stream")


def _extract_text(body: dict) -> str:
    """
    Pull plain transcript text from a completed Soniox response.

    Soniox may return:
      body["text"]           — top-level flat transcript
      body["transcript"]     — alias used in some response versions
      body["words"]          — list of word objects with .word fields
    """
    if "text" in body:
        return body["text"].strip()
    if "transcript" in body:
        return body["transcript"].strip()
    # Reconstruct from word list
    words = body.get("words", [])
    if words:
        return " ".join(w.get("word", w.get("text", "")) for w in words).strip()
    return ""
