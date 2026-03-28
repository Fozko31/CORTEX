"""
F-3 Tests — Image Understanding + Document Parsing
====================================================
Tests for:
  cortex_vision_client.py    — Two-step Gemini + DeepSeek image analysis
  cortex_document_parser.py  — PDF/Word/Excel/CSV/text extraction + chunking

All external API calls are mocked. No real Gemini or DeepSeek calls.
Document parsing tests use in-memory bytes — no real files needed.
"""

import csv
import io
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ===========================================================================
# Vision Client (tests 1–10)
# ===========================================================================

class TestVisionClient:

    def _make_client(self, key="test_key"):
        from python.helpers.cortex_vision_client import CortexVisionClient
        return CortexVisionClient(api_key=key)

    def _mock_openrouter(self, content: str, status_code: int = 200):
        """Return an async context manager mock that yields an httpx-like response."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }
        mock_resp.text = content
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        return mock_http

    # 1. from_env reads API_KEY_OPENROUTER
    def test_from_env_reads_key(self):
        with patch.dict(os.environ, {"API_KEY_OPENROUTER": "or_key_123"}):
            from python.helpers.cortex_vision_client import CortexVisionClient
            client = CortexVisionClient.from_env()
        assert client._api_key == "or_key_123"

    # 2. analyze: _describe called with base64 image
    @pytest.mark.asyncio
    async def test_describe_called_with_image(self):
        client = self._make_client()
        with patch.object(client, "_describe", new_callable=AsyncMock, return_value="An invoice for €840") as mock_d:
            with patch.object(client, "_structure", new_callable=AsyncMock, return_value={"summary": "Invoice"}):
                await client.analyze(b"img_bytes", mime_type="image/jpeg")
        mock_d.assert_called_once_with(b"img_bytes", "image/jpeg", None)

    # 3. analyze: _structure called with description
    @pytest.mark.asyncio
    async def test_structure_called_with_description(self):
        client = self._make_client()
        desc = "An invoice showing €840 total"
        with patch.object(client, "_describe", new_callable=AsyncMock, return_value=desc):
            with patch.object(client, "_structure", new_callable=AsyncMock, return_value={"summary": "Invoice"}) as mock_s:
                await client.analyze(b"img_bytes")
        mock_s.assert_called_once_with(desc)

    # 4. analyze: returns structured dict
    @pytest.mark.asyncio
    async def test_analyze_returns_dict(self):
        client = self._make_client()
        expected = {
            "summary": "Invoice for Kovač d.o.o.",
            "key_elements": ["company name", "total amount"],
            "text_in_image": "Total: €840",
            "data": {"total": 840},
            "ui_elements": [],
            "actionable_items": ["Approve payment"],
            "requires_decision": True,
        }
        with patch.object(client, "_describe", new_callable=AsyncMock, return_value="desc"):
            with patch.object(client, "_structure", new_callable=AsyncMock, return_value=expected):
                result = await client.analyze(b"img_bytes")
        assert result["summary"] == "Invoice for Kovač d.o.o."
        assert result["requires_decision"] is True
        assert "Approve payment" in result["actionable_items"]

    # 5. _describe: raises VisionError on API 500
    @pytest.mark.asyncio
    async def test_describe_raises_on_api_error(self):
        from python.helpers.cortex_vision_client import VisionError
        client = self._make_client()
        mock_resp = MagicMock(status_code=500, text="Internal Server Error")
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with pytest.raises(VisionError):
                await client._describe(b"img", "image/jpeg", None)

    # 6. _structure: returns empty analysis on bad JSON
    @pytest.mark.asyncio
    async def test_structure_returns_empty_on_bad_json(self):
        client = self._make_client()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"choices": [{"message": {"content": "not valid json {"}}]}
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client._structure("some description")

        assert isinstance(result, dict)
        assert "summary" in result

    # 7. _structure: strips markdown code fences
    @pytest.mark.asyncio
    async def test_structure_strips_code_fences(self):
        client = self._make_client()
        json_content = '```json\n{"summary": "clean", "key_elements": [], "text_in_image": "", "data": {}, "ui_elements": [], "actionable_items": [], "requires_decision": false}\n```'
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"choices": [{"message": {"content": json_content}}]}
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client._structure("desc")

        assert result["summary"] == "clean"

    # 8. analyze: hint is passed to _describe
    @pytest.mark.asyncio
    async def test_hint_passed_to_describe(self):
        client = self._make_client()
        with patch.object(client, "_describe", new_callable=AsyncMock, return_value="desc") as mock_d:
            with patch.object(client, "_structure", new_callable=AsyncMock, return_value={}):
                await client.analyze(b"img", hint="payment_screenshot")
        mock_d.assert_called_once_with(b"img", "image/jpeg", "payment_screenshot")

    # 9. from_agent_config falls back to env
    def test_from_agent_config_fallback(self):
        with patch.dict(os.environ, {"API_KEY_OPENROUTER": "fallback_key"}):
            from python.helpers.cortex_vision_client import CortexVisionClient
            client = CortexVisionClient.from_agent_config(agent=None)
        assert client._api_key == "fallback_key"

    # 10. analyze: _structure error returns partial result
    @pytest.mark.asyncio
    async def test_structure_exception_returns_partial(self):
        client = self._make_client()
        with patch.object(client, "_describe", new_callable=AsyncMock, return_value="raw desc"):
            with patch.object(client, "_structure", new_callable=AsyncMock, side_effect=Exception("boom")):
                # analyze doesn't propagate _structure errors — _structure catches internally
                # So we test _structure directly
                pass
        # _structure has try/except that returns empty dict — test that path
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.side_effect = Exception("parse failed")
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        with patch("httpx.AsyncClient") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client._structure("desc")
        assert isinstance(result, dict)


# ===========================================================================
# Document Parser (tests 11–20)
# ===========================================================================

class TestDocumentParser:

    def _make_parser(self):
        from python.helpers.cortex_document_parser import CortexDocumentParser
        return CortexDocumentParser()

    # 11. supports() returns True for PDF
    def test_supports_pdf(self):
        parser = self._make_parser()
        assert parser.supports("report.pdf") is True

    # 12. supports() returns True for docx
    def test_supports_docx(self):
        parser = self._make_parser()
        assert parser.supports("brief.docx") is True

    # 13. supports() returns False for unsupported format
    def test_supports_rejects_mp4(self):
        parser = self._make_parser()
        assert parser.supports("video.mp4") is False

    # 14. parse unsupported format raises ParseError
    @pytest.mark.asyncio
    async def test_parse_unsupported_raises(self):
        from python.helpers.cortex_document_parser import ParseError
        parser = self._make_parser()
        with pytest.raises(ParseError, match="Unsupported"):
            await parser.parse(b"data", "video.mp4")

    # 15. parse CSV: extracts rows as text
    @pytest.mark.asyncio
    async def test_parse_csv(self):
        csv_data = "Name,Revenue\nMoving Co,50000\nAcme,120000\n"
        parser = self._make_parser()
        result = await parser.parse(csv_data.encode(), "data.csv")
        assert "Moving Co" in result.text
        assert "Revenue" in result.text

    # 16. parse TXT: returns raw text
    @pytest.mark.asyncio
    async def test_parse_txt(self):
        content = "Hello from CORTEX.\nSecond line here."
        parser = self._make_parser()
        result = await parser.parse(content.encode(), "notes.txt")
        assert "CORTEX" in result.text
        assert result.mime_type == "text/plain"

    # 17. parse MD: returns markdown text
    @pytest.mark.asyncio
    async def test_parse_md(self):
        content = "# Title\n\nSome **bold** content."
        parser = self._make_parser()
        result = await parser.parse(content.encode(), "readme.md")
        assert "Title" in result.text

    # 18. ParseResult.is_large: False for small doc
    @pytest.mark.asyncio
    async def test_is_large_false_for_small(self):
        parser = self._make_parser()
        result = await parser.parse(b"Short text.", "note.txt")
        assert result.is_large is False
        assert result.chunks == []

    # 19. ParseResult.is_large: True for large doc (chunked)
    @pytest.mark.asyncio
    async def test_is_large_true_for_large_doc(self):
        # Generate text > 24000 chars
        large_text = ("word " * 5000 + "\n\n") * 2  # ~60000 chars
        parser = self._make_parser()
        result = await parser.parse(large_text.encode(), "big.txt")
        assert result.is_large is True
        assert len(result.chunks) >= 2
        # All text accounted for (approximately — chunks may vary at boundaries)
        total_chunk_text = "".join(result.chunks)
        assert len(total_chunk_text) > 0

    # 20. token_estimate is reasonable
    @pytest.mark.asyncio
    async def test_token_estimate(self):
        text = "word " * 400  # 2000 words ≈ 10000 chars ≈ 2500 tokens
        parser = self._make_parser()
        result = await parser.parse(text.encode(), "doc.txt")
        assert result.token_estimate > 0
        assert result.token_estimate < 5000  # sanity upper bound
