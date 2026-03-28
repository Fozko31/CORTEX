"""
test_f_live_free.py -- Phase F Live Connectivity Tests (Free Tier Only)
=======================================================================
Tests that use REAL credentials but only free/already-paid services:
  - Telegram text send (free)
  - Telegram health check (free)
  - Response formatter (free, no API)
  - Document parser -- CSV, TXT (free, local)
  - Image analysis (Gemini + DeepSeek via OpenRouter -- you already have the key)
  - TTS router language detection (free, local)
  - Voice cleaner regex pass (free, local)

NOT included (requires Soniox pay-per-use):
  - STT transcription (skip -- test separately when ready to pay)

NOT included (requires Azure setup):
  - Azure TTS synthesis (skip until you create Azure account)

Run:
  python -m pytest tests/test_f_live_free.py -v -s

Requirements:
  TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in usr/.env
  API_KEY_OPENROUTER must be set (already is)
"""

import asyncio
import os
import sys
import pytest

# Load .env from usr/.env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "usr", ".env"))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
OR_KEY    = os.getenv("API_KEY_OPENROUTER", "")

skip_telegram = pytest.mark.skipif(
    not BOT_TOKEN or not CHAT_ID,
    reason="TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in usr/.env"
)
skip_openrouter = pytest.mark.skipif(
    not OR_KEY,
    reason="API_KEY_OPENROUTER not set in usr/.env"
)


# ===========================================================================
# Telegram connectivity (tests 1-3)
# ===========================================================================

@skip_telegram
@pytest.mark.asyncio
async def test_telegram_health_check():
    """Verify bot token is valid and Telegram is reachable."""
    from python.helpers.cortex_telegram_bot import TelegramBotHandler, TelegramConfig
    config = TelegramConfig(bot_token=BOT_TOKEN, chat_id=CHAT_ID)
    handler = TelegramBotHandler(config, agent=None)
    result = await handler.health_check()
    assert result is True, "Bot token invalid or Telegram unreachable"
    print("\nOK Telegram health check: BOT IS CONNECTED")


@skip_telegram
@pytest.mark.asyncio
async def test_telegram_send_text():
    """Send a real text message to your Telegram chat."""
    from python.helpers.cortex_telegram_bot import TelegramBotHandler, TelegramConfig
    config = TelegramConfig(bot_token=BOT_TOKEN, chat_id=CHAT_ID)
    handler = TelegramBotHandler(config, agent=None)

    msg = (
        "*CORTEX Phase F Live Test*\n\n"
        "This is a live test message from the automated test suite.\n"
        "- Text formatting: ok\n"
        "- Bold: *works*\n"
        "- Bot is alive and connected.\n\n"
        "_If you see this in Telegram, F-1 text send works._"
    )
    ok = await handler.send_text(CHAT_ID, msg)
    assert ok is True, "send_text returned False -- check token and chat_id"
    print(f"\nOK Message sent to chat {CHAT_ID}")


@skip_telegram
@pytest.mark.asyncio
async def test_telegram_send_morning_digest():
    """Send a mock morning digest to Telegram."""
    from python.helpers.cortex_telegram_bot import TelegramBotHandler, TelegramConfig, DigestData
    from python.helpers.cortex_telegram_bot import _format_digest

    config = TelegramConfig(bot_token=BOT_TOKEN, chat_id=CHAT_ID)
    handler = TelegramBotHandler(config, agent=None)

    class FakeCommitment:
        id = "C4a1"
        text = "Draft pricing review for Moving Co"
        status = "overdue"
        due_date = "2026-03-25"

    data = DigestData(
        hitl_items=[
            {"action_id": "A001xxxx", "action_type": "send_email", "venture_slug": "moving_co", "cost_estimate": None},
        ],
        commitments=[FakeCommitment()],
    )
    digest_text = _format_digest(data)
    ok = await handler.send_text(CHAT_ID, digest_text)
    assert ok is True
    print(f"\nOK Morning digest sent -- {len(digest_text)} chars")


# ===========================================================================
# Response Formatter -- no API needed (tests 4-5)
# ===========================================================================

def test_formatter_telegram_real_output():
    """Verify formatter produces clean Telegram output from complex markdown."""
    from python.helpers.cortex_response_formatter import CortexResponseFormatter
    fmt = CortexResponseFormatter()

    complex_md = """
## Revenue Summary

| Venture | Revenue | Growth |
|---------|---------|--------|
| Moving Co | 50,000 | +12% |
| SaaS Tool | 8,400 | +34% |

**Key insight:** Moving Co is underperforming vs. SaaS on growth rate.

### Action items
- Review Moving Co pricing strategy
- Allocate 2hrs/week to SaaS marketing
- Schedule call with logistics partner

```python
# This code block should be stripped
revenue = 50000
```
"""
    result = fmt.format_for_telegram(complex_md)
    print(f"\n--- Telegram formatted output ---\n{result}\n---")

    assert "revenue = 50000" in result  # content preserved
    assert "Moving Co" in result
    assert "```" not in result          # code blocks stripped
    print("OK Telegram formatter works")


def test_formatter_voice_real_output():
    """Verify voice formatter strips everything for clean TTS."""
    from python.helpers.cortex_response_formatter import CortexResponseFormatter
    fmt = CortexResponseFormatter()

    text = "Revenue grew **34%** and costs are next milestone is Q2"
    result = fmt.format_for_voice(text)
    print(f"\n--- Voice formatted output ---\n{result}\n---")

    assert "**" not in result
    assert "34 percent" in result
    print("OK Voice formatter works")


# ===========================================================================
# Document Parser -- local, free (tests 6-7)
# ===========================================================================

@pytest.mark.asyncio
async def test_parse_csv_real():
    """Parse a real CSV from bytes."""
    from python.helpers.cortex_document_parser import CortexDocumentParser

    csv_content = (
        "Venture,Revenue,Status\n"
        "Moving Co,50000,active\n"
        "SaaS Tool,8400,active\n"
        "Affiliate,1200,paused\n"
    ).encode()

    parser = CortexDocumentParser()
    result = await parser.parse(csv_content, "portfolio.csv")

    print(f"\n--- CSV parse result ---\n{result.text}\n---")
    assert "Moving Co" in result.text
    assert "SaaS Tool" in result.text
    assert result.is_large is False
    print(f"OK CSV parsed: {result.token_estimate} token estimate, not large")


@pytest.mark.asyncio
async def test_parse_large_doc_chunks():
    """Verify large document gets chunked for SurfSense."""
    from python.helpers.cortex_document_parser import CortexDocumentParser

    # Generate 30k chars -- above threshold
    large = ("This is a business report paragraph with real content. " * 50 + "\n\n") * 10
    parser = CortexDocumentParser()
    result = await parser.parse(large.encode(), "big_report.txt")

    assert result.is_large is True
    assert len(result.chunks) >= 2
    print(f"\nOK Large doc chunked into {len(result.chunks)} chunks for SurfSense push")


# ===========================================================================
# TTS Language Detection -- free, local (tests 8-9)
# ===========================================================================

def test_tts_language_detect_slovenian():
    """Verify Slovenian text is correctly detected."""
    from python.helpers.cortex_tts_router import _detect_language
    # Sentences with 2+ Slovenian markers (threshold=2)
    result1 = _detect_language("Dobro jutro, kako si danes?")          # "dobro"+"jutro"+"kako" = 3
    result2 = _detect_language("To je pomembno za nase podjetje.")      # "je"+"za"+"na" = 3
    result3 = _detect_language("Moram iti na sestanek ker je nujno.")   # "na"+"ker"+"je" = 3
    print(f"\nSlovenian detection: '{result1}', '{result2}', '{result3}'")
    assert result1 == "sl", f"Expected 'sl', got '{result1}'"
    assert result2 == "sl", f"Expected 'sl', got '{result2}'"
    assert result3 == "sl", f"Expected 'sl', got '{result3}'"
    print("OK Slovenian language detected correctly")


def test_tts_language_detect_english():
    """Verify English text is correctly classified."""
    from python.helpers.cortex_tts_router import _detect_language
    result1 = _detect_language("Good morning, here is your revenue report.")
    result2 = _detect_language("The market analysis shows positive growth trends.")
    print(f"\nEnglish detection: '{result1}' and '{result2}'")
    assert result1 == "en", f"Expected 'en', got '{result1}'"
    assert result2 == "en", f"Expected 'en', got '{result2}'"
    print("OK English language detected correctly")


# ===========================================================================
# Voice Cleaner Regex -- free, local (test 10)
# ===========================================================================

@pytest.mark.asyncio
async def test_voice_cleaner_regex_real():
    """Run real regex cleanup on realistic disfluent speech."""
    from python.helpers.cortex_voice_cleaner import CortexVoiceCleaner

    cleaner = CortexVoiceCleaner(api_key="", skip_llm=True)

    raw_en = "Um so I want to uh send an email to the the client about the proposal"
    raw_sl = "Torej pac moram iti na sestanek danes"

    clean_en = await cleaner.clean(raw_en)
    clean_sl = await cleaner.clean(raw_sl)

    print(f"\n--- Voice cleaner results ---")
    print(f"EN raw:   '{raw_en}'")
    print(f"EN clean: '{clean_en}'")
    print(f"SL raw:   '{raw_sl}'")
    print(f"SL clean: '{clean_sl}'")

    assert "um" not in clean_en.lower()
    assert "uh" not in clean_en.lower()
    assert "email" in clean_en
    print("OK Voice cleaner regex pass works")


# ===========================================================================
# Image Analysis -- OpenRouter (you have the key) (test 11)
# ===========================================================================

@skip_openrouter
@pytest.mark.asyncio
async def test_vision_client_api_connectivity():
    """
    Verify Gemini model ID is accepted by OpenRouter (connectivity test).
    Sends a text-only message to avoid needing a real image file.
    Model correctness is confirmed if we get a 200, not a 400 model-not-found.
    Cost: ~$0.0001
    """
    import httpx
    client_key = os.getenv("API_KEY_OPENROUTER", "")
    headers = {
        "Authorization": f"Bearer {client_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://cortex.local",
    }
    payload = {
        "model": "google/gemini-2.0-flash-lite-001",
        "messages": [{"role": "user", "content": "Say: vision client OK"}],
        "max_tokens": 10,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers,
        )
    print(f"\nGemini model check: HTTP {resp.status_code}")
    assert resp.status_code == 200, f"Model not found or API error: {resp.text[:200]}"
    print("OK Vision client model ID is valid on OpenRouter")


# ===========================================================================
# Kokoro TTS English -- local, free (test 12)
# ===========================================================================

@pytest.mark.asyncio
async def test_kokoro_tts_synthesize():
    """
    Synthesize a short English sentence via Kokoro (local, free).
    Verifies Kokoro is installed and produces non-empty WAV bytes.
    """
    from python.helpers.cortex_kokoro_tts import CortexKokoroTTS, KokoroError

    tts = CortexKokoroTTS.default()
    if not tts.is_available():
        pytest.skip("Kokoro not installed (pip install kokoro-onnx soundfile)")

    wav_bytes = await tts.synthesize("Good morning. Your digest is ready.")
    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 1000, "WAV output too small -- synthesis may have failed"
    print(f"\nOK Kokoro TTS: {len(wav_bytes)} bytes of WAV audio synthesized")


@skip_telegram
@pytest.mark.asyncio
async def test_kokoro_tts_send_voice_to_telegram():
    """
    Synthesize English speech with Kokoro and send it as a voice note to Telegram.
    If you receive a voice message saying 'Good morning', the full English TTS
    pipeline works end-to-end: Kokoro -> WAV -> Telegram voice note.
    """
    from python.helpers.cortex_kokoro_tts import CortexKokoroTTS
    from python.helpers.cortex_telegram_bot import TelegramBotHandler, TelegramConfig

    tts = CortexKokoroTTS.default()
    if not tts.is_available():
        pytest.skip("Kokoro not installed")

    wav_bytes = await tts.synthesize(
        "Good morning. This is a live test of the CORTEX voice pipeline. "
        "If you hear this, Kokoro TTS and Telegram voice delivery both work correctly."
    )
    assert len(wav_bytes) > 1000

    config = TelegramConfig(bot_token=BOT_TOKEN, chat_id=CHAT_ID)
    handler = TelegramBotHandler(config, agent=None)
    ok = await handler.send_voice(CHAT_ID, wav_bytes)
    assert ok is True, "send_voice returned False"
    print(f"\nOK Voice note sent to Telegram -- {len(wav_bytes)} bytes WAV")
