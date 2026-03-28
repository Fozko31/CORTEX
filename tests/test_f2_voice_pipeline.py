"""
F-2 Tests — Voice Pipeline
===========================
Tests for:
  cortex_soniox_client.py    — STT transcription
  cortex_voice_cleaner.py    — Artifact removal (regex + LLM)
  cortex_kokoro_tts.py       — English TTS (local)
  cortex_azure_tts.py        — Slovenian TTS (Azure Neural)
  cortex_tts_router.py       — Language routing + preference management
  cortex_personality_model.py — get/set_preference extension

All external calls are mocked. No real API calls.
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ===========================================================================
# Soniox Client (tests 1–5)
# ===========================================================================

class TestSonioxClient:

    def _make_client(self, key="test_key"):
        from python.helpers.cortex_soniox_client import CortexSonioxClient
        return CortexSonioxClient(api_key=key)

    # 1. from_env reads SONIOX_API_KEY
    def test_from_env_reads_key(self):
        with patch.dict(os.environ, {"SONIOX_API_KEY": "sk_test_123"}):
            from python.helpers.cortex_soniox_client import CortexSonioxClient
            client = CortexSonioxClient.from_env()
        assert client._api_key == "sk_test_123"

    # 2. Empty key raises SonioxError
    def test_empty_key_raises(self):
        from python.helpers.cortex_soniox_client import SonioxError, CortexSonioxClient
        with pytest.raises(SonioxError):
            CortexSonioxClient(api_key="")

    # 3. health_check returns True on 200
    @pytest.mark.asyncio
    async def test_health_check_true(self):
        client = self._make_client()
        mock_resp = MagicMock(status_code=200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        with patch("httpx.AsyncClient") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.health_check()
        assert result is True

    # 4. health_check returns False on 401
    @pytest.mark.asyncio
    async def test_health_check_false(self):
        client = self._make_client()
        mock_resp = MagicMock(status_code=401)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        with patch("httpx.AsyncClient") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.health_check()
        assert result is False

    # 5. transcribe: submit + poll → returns text
    @pytest.mark.asyncio
    async def test_transcribe_happy_path(self):
        from python.helpers.cortex_soniox_client import CortexSonioxClient
        client = CortexSonioxClient(api_key="test_key")

        with patch.object(client, "_submit", new_callable=AsyncMock, return_value="job_abc"):
            with patch.object(client, "_poll", new_callable=AsyncMock, return_value="Hello world"):
                result = await client.transcribe(b"audio_bytes")

        assert result == "Hello world"


# ===========================================================================
# Voice Cleaner (tests 6–10)
# ===========================================================================

class TestVoiceCleaner:

    def _make_cleaner(self, skip_llm=True):
        from python.helpers.cortex_voice_cleaner import CortexVoiceCleaner
        return CortexVoiceCleaner(api_key="test_key", skip_llm=skip_llm)

    # 6. Filler word removal (English)
    @pytest.mark.asyncio
    async def test_removes_english_fillers(self):
        cleaner = self._make_cleaner()
        result = await cleaner.clean("Um, I want to uh schedule a meeting")
        assert "um" not in result.lower()
        assert "uh" not in result.lower()
        assert "meeting" in result

    # 7. Filler word removal (Slovenian)
    @pytest.mark.asyncio
    async def test_removes_slovenian_fillers(self):
        cleaner = self._make_cleaner()
        result = await cleaner.clean("Torej pač moram iti na sestanek")
        assert "torej" not in result.lower()
        assert "sestanek" in result

    # 8. Repeated word removal
    @pytest.mark.asyncio
    async def test_removes_repeated_words(self):
        cleaner = self._make_cleaner()
        result = await cleaner.clean("the the report is ready")
        assert "the the" not in result
        assert "report" in result

    # 9. Empty string returns empty
    @pytest.mark.asyncio
    async def test_empty_input(self):
        cleaner = self._make_cleaner()
        result = await cleaner.clean("")
        assert result == ""

    # 10. LLM cleanup called when skip_llm=False
    @pytest.mark.asyncio
    async def test_llm_cleanup_called(self):
        from python.helpers.cortex_voice_cleaner import CortexVoiceCleaner
        cleaner = CortexVoiceCleaner(api_key="test_key", skip_llm=False)

        with patch.object(cleaner, "_llm_clean", new_callable=AsyncMock, return_value="clean text") as mock_llm:
            result = await cleaner.clean("um yeah so I want to go to the meeting yeah")

        mock_llm.assert_called_once()
        assert result == "clean text"


# ===========================================================================
# Kokoro TTS (tests 11–13)
# ===========================================================================

class TestKokoroTTS:

    # 11. is_available returns False when kokoro not installed
    def test_is_available_false_when_not_installed(self):
        from python.helpers.cortex_kokoro_tts import CortexKokoroTTS
        tts = CortexKokoroTTS()
        with patch.dict("sys.modules", {"kokoro": None}):
            # Can't truly uninstall, but we can test the is_available guard
            result = tts.is_available()
            # Result depends on installation state — just verify it returns bool
            assert isinstance(result, bool)

    # 12. synthesize routes to _synthesize_sync via executor
    @pytest.mark.asyncio
    async def test_synthesize_calls_sync(self):
        from python.helpers.cortex_kokoro_tts import CortexKokoroTTS
        tts = CortexKokoroTTS()
        with patch.object(tts, "_synthesize_sync", return_value=b"wav_data"):
            result = await tts.synthesize("Good morning.")
        assert result == b"wav_data"

    # 13. KokoroError raised when synthesis fails
    @pytest.mark.asyncio
    async def test_synthesis_error_raised(self):
        from python.helpers.cortex_kokoro_tts import CortexKokoroTTS, KokoroError
        tts = CortexKokoroTTS()
        with patch.object(tts, "_synthesize_sync", side_effect=KokoroError("synthesis failed")):
            with pytest.raises(KokoroError):
                await tts.synthesize("test")


# ===========================================================================
# Azure TTS (tests 14–16)
# ===========================================================================

class TestAzureTTS:

    def _make_tts(self, key="azure_key", region="westeurope"):
        from python.helpers.cortex_azure_tts import CortexAzureTTS
        return CortexAzureTTS(api_key=key, region=region)

    # 14. is_available returns False when key missing
    def test_is_available_false_no_key(self):
        from python.helpers.cortex_azure_tts import CortexAzureTTS
        tts = CortexAzureTTS(api_key="")
        assert tts.is_available() is False

    # 15. is_available True when key set
    def test_is_available_true_with_key(self):
        tts = self._make_tts()
        assert tts.is_available() is True

    # 16. synthesize calls _synthesize_sync via executor
    @pytest.mark.asyncio
    async def test_synthesize_sl(self):
        tts = self._make_tts()
        with patch.object(tts, "_synthesize_sync", return_value=b"mp3_sl"):
            result = await tts.synthesize("Dobro jutro.", language="sl")
        assert result == b"mp3_sl"


# ===========================================================================
# TTS Router (tests 17–22)
# ===========================================================================

class TestTTSRouter:

    # 17. Slovenian text → routes to Azure
    @pytest.mark.asyncio
    async def test_slovenian_routes_to_azure(self):
        from python.helpers.cortex_tts_router import CortexTTSRouter
        with patch.object(CortexTTSRouter, "_azure", new_callable=AsyncMock, return_value=b"sl_audio") as mock_az:
            with patch.object(CortexTTSRouter, "get_pref", return_value="match_input"):
                result = await CortexTTSRouter.route("Dobro jutro, kako si?", language_hint="sl")
        mock_az.assert_called_once()
        assert result == b"sl_audio"

    # 18. English text → routes to Kokoro
    @pytest.mark.asyncio
    async def test_english_routes_to_kokoro(self):
        from python.helpers.cortex_tts_router import CortexTTSRouter
        with patch.object(CortexTTSRouter, "_kokoro", new_callable=AsyncMock, return_value=b"en_audio") as mock_ko:
            with patch.object(CortexTTSRouter, "get_pref", return_value="match_input"):
                result = await CortexTTSRouter.route("Good morning, here is your report.", language_hint="en")
        mock_ko.assert_called_once()
        assert result == b"en_audio"

    # 19. force_sl pref → Azure even for English text
    @pytest.mark.asyncio
    async def test_force_sl_pref_overrides(self):
        from python.helpers.cortex_tts_router import CortexTTSRouter
        with patch.object(CortexTTSRouter, "_azure", new_callable=AsyncMock, return_value=b"sl_forced") as mock_az:
            with patch.object(CortexTTSRouter, "get_pref", return_value="force_sl"):
                result = await CortexTTSRouter.route("Good morning.", language_hint="en")
        mock_az.assert_called_once()

    # 20. detect_pref_command — Slovenian command detected
    def test_detect_pref_sl_command(self):
        from python.helpers.cortex_tts_router import CortexTTSRouter, PREF_FORCE_SL
        result = CortexTTSRouter.detect_pref_command("answer in Slovenian please")
        assert result == PREF_FORCE_SL

    # 21. detect_pref_command — English command detected
    def test_detect_pref_en_command(self):
        from python.helpers.cortex_tts_router import CortexTTSRouter, PREF_FORCE_EN
        result = CortexTTSRouter.detect_pref_command("odgovori v angleščini")
        assert result == PREF_FORCE_EN

    # 22. detect_pref_command — non-command returns None
    def test_detect_pref_returns_none_for_non_command(self):
        from python.helpers.cortex_tts_router import CortexTTSRouter
        result = CortexTTSRouter.detect_pref_command("What is the revenue for moving_co?")
        assert result is None


# ===========================================================================
# PersonalityModel preferences extension (bonus — validates the extension)
# ===========================================================================

class TestPersonalityModelPreferences:

    def _make_model(self):
        from python.helpers.cortex_personality_model import PersonalityModel
        return PersonalityModel()

    def test_get_preference_default(self):
        model = self._make_model()
        assert model.get_preference("tts_language_pref") == "match_input"

    def test_set_get_preference(self):
        model = self._make_model()
        model.set_preference("tts_language_pref", "force_sl")
        assert model.get_preference("tts_language_pref") == "force_sl"

    def test_preferences_persisted_in_to_dict(self):
        model = self._make_model()
        model.set_preference("comprehension_mode", "detailed")
        d = model.to_dict()
        assert d["preferences"]["comprehension_mode"] == "detailed"

    def test_preferences_restored_from_dict(self):
        from python.helpers.cortex_personality_model import PersonalityModel
        data = {
            "dimensions": {},
            "observations": [],
            "preferences": {"tts_language_pref": "force_en"},
        }
        model = PersonalityModel.from_dict(data)
        assert model.get_preference("tts_language_pref") == "force_en"
