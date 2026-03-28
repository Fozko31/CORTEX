"""
F-1 Tests — Telegram Core
=========================
Tests for cortex_telegram_bot.py and telegram_ops.py.
All external calls are mocked. No real Telegram API calls.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_config(token="test_token", chat_id="123456"):
    from python.helpers.cortex_telegram_bot import TelegramConfig
    return TelegramConfig(bot_token=token, chat_id=chat_id)


def make_handler(token="test_token", chat_id="123456", agent=None):
    from python.helpers.cortex_telegram_bot import TelegramBotHandler, TelegramConfig
    config = TelegramConfig(bot_token=token, chat_id=chat_id)
    return TelegramBotHandler(config, agent=agent)


def make_text_update(text: str, chat_id: str = "123456", message_id: int = 1) -> dict:
    return {
        "message": {
            "message_id": message_id,
            "chat": {"id": chat_id},
            "text": text,
        }
    }


def make_voice_update(file_id: str = "voice_file_id", chat_id: str = "123456") -> dict:
    return {
        "message": {
            "message_id": 2,
            "chat": {"id": chat_id},
            "voice": {"file_id": file_id, "duration": 3, "mime_type": "audio/ogg"},
        }
    }


def make_photo_update(file_id: str = "photo_file_id", caption: str = "", chat_id: str = "123456") -> dict:
    return {
        "message": {
            "message_id": 3,
            "chat": {"id": chat_id},
            "photo": [
                {"file_id": "small_id", "width": 100, "height": 100},
                {"file_id": file_id, "width": 800, "height": 600},
            ],
            "caption": caption,
        }
    }


def make_document_update(file_id: str = "doc_file_id", filename: str = "test.pdf", chat_id: str = "123456") -> dict:
    return {
        "message": {
            "message_id": 4,
            "chat": {"id": chat_id},
            "document": {
                "file_id": file_id,
                "file_name": filename,
                "mime_type": "application/pdf",
            },
        }
    }


# ---------------------------------------------------------------------------
# 1. Routing: text update → handle_text called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_update_routes_text():
    handler = make_handler()
    update = make_text_update("Hello CORTEX")

    with patch.object(handler, "handle_text", new_callable=AsyncMock, return_value="ok") as mock_text:
        result = await handler.handle_update(update)
    mock_text.assert_called_once_with("Hello CORTEX", "123456", 1)
    assert result == "ok"


# ---------------------------------------------------------------------------
# 2. Routing: voice update → handle_voice called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_update_routes_voice():
    handler = make_handler()
    update = make_voice_update()

    with patch.object(handler, "_download_file", new_callable=AsyncMock, return_value=b"audio"):
        with patch.object(handler, "handle_voice", new_callable=AsyncMock, return_value="transcribed") as mock_voice:
            result = await handler.handle_update(update)

    mock_voice.assert_called_once()
    assert result == "transcribed"


# ---------------------------------------------------------------------------
# 3. Routing: photo update → handle_photo called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_update_routes_photo():
    handler = make_handler()
    update = make_photo_update(caption="What is this?")

    with patch.object(handler, "_download_file", new_callable=AsyncMock, return_value=b"imgdata"):
        with patch.object(handler, "handle_photo", new_callable=AsyncMock, return_value="photo handled") as mock_photo:
            result = await handler.handle_update(update)

    mock_photo.assert_called_once()
    assert result == "photo handled"


# ---------------------------------------------------------------------------
# 4. Routing: document update → handle_document called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_update_routes_document():
    handler = make_handler()
    update = make_document_update()

    with patch.object(handler, "_download_file", new_callable=AsyncMock, return_value=b"pdfbytes"):
        with patch.object(handler, "handle_document", new_callable=AsyncMock, return_value="doc handled") as mock_doc:
            result = await handler.handle_update(update)

    mock_doc.assert_called_once()
    assert result == "doc handled"


# ---------------------------------------------------------------------------
# 5. Command reply: approve [id]
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_text_approve_command():
    handler = make_handler()

    with patch.object(handler, "_cmd_approve", new_callable=AsyncMock, return_value="✓ Action abc12345 approved.") as mock_approve:
        result = await handler.handle_text("approve abc12345", "123456")

    mock_approve.assert_called_once_with("abc12345", "123456")
    assert "approved" in result


# ---------------------------------------------------------------------------
# 6. Command reply: reject [id] [reason]
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_text_reject_command_with_reason():
    handler = make_handler()

    with patch.object(handler, "_cmd_reject", new_callable=AsyncMock, return_value="✗ Action xyz rejected.") as mock_reject:
        result = await handler.handle_text("reject xyz wrong account", "123456")

    mock_reject.assert_called_once_with("xyz", "wrong account", "123456")


# ---------------------------------------------------------------------------
# 7. Command reply: reject [id] (no reason)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_text_reject_command_no_reason():
    handler = make_handler()

    with patch.object(handler, "_cmd_reject", new_callable=AsyncMock, return_value="✗ rejected") as mock_reject:
        await handler.handle_text("reject abc123", "123456")

    mock_reject.assert_called_once_with("abc123", None, "123456")


# ---------------------------------------------------------------------------
# 8. Command reply: done [id]
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_text_done_command():
    handler = make_handler()

    with patch.object(handler, "_cmd_done", new_callable=AsyncMock, return_value="✓ done") as mock_done:
        result = await handler.handle_text("done C4a1", "123456")

    mock_done.assert_called_once_with("C4a1", "123456")


# ---------------------------------------------------------------------------
# 9. Command reply: health [venture]
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_text_health_command():
    handler = make_handler()

    with patch.object(handler, "_cmd_health", new_callable=AsyncMock, return_value="health ok") as mock_health:
        result = await handler.handle_text("health moving_co", "123456")

    mock_health.assert_called_once_with("moving_co", "123456")


# ---------------------------------------------------------------------------
# 10. Non-command text → routed to agent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_text_routes_to_agent():
    handler = make_handler()

    with patch.object(handler, "_route_to_agent", new_callable=AsyncMock, return_value="agent response") as mock_agent:
        result = await handler.handle_text("What is the CVS score for moving_co?", "123456")

    mock_agent.assert_called_once_with("What is the CVS score for moving_co?", "123456")
    assert result == "agent response"


# ---------------------------------------------------------------------------
# 11. Morning digest format: HITL items present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_morning_digest_includes_hitl():
    from python.helpers.cortex_telegram_bot import _format_digest, DigestData

    data = DigestData(
        hitl_items=[
            {"action_id": "A001xxxx", "action_type": "send_email", "venture_slug": "moving_co", "cost_estimate": None},
            {"action_id": "A002yyyy", "action_type": "spend_money", "venture_slug": "moving_co", "cost_estimate": 840.0},
        ]
    )
    text = _format_digest(data)

    assert "PENDING APPROVALS" in text
    assert "A001" in text
    assert "A002" in text
    assert "approve" in text.lower()


# ---------------------------------------------------------------------------
# 12. Morning digest format: no pending items
# ---------------------------------------------------------------------------

def test_morning_digest_empty():
    from python.helpers.cortex_telegram_bot import _format_digest, DigestData

    data = DigestData()
    text = _format_digest(data)

    assert "No pending approvals" in text or "All clear" in text


# ---------------------------------------------------------------------------
# 13. Morning digest: commitments shown
# ---------------------------------------------------------------------------

def test_morning_digest_commitments():
    from python.helpers.cortex_telegram_bot import _format_digest, DigestData

    class FakeCommitment:
        id = "C4a1"
        text = "Draft pricing review"
        status = "overdue"
        due_date = "2026-03-25"

    data = DigestData(commitments=[FakeCommitment()])
    text = _format_digest(data)

    assert "C4a1" in text
    assert "OVERDUE" in text


# ---------------------------------------------------------------------------
# 14. send_text uses formatter and posts to Telegram API
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_text_calls_api():
    handler = make_handler()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(handler, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        with patch("python.helpers.cortex_response_formatter.CortexResponseFormatter.format_for_telegram",
                   return_value="formatted text", create=True):
            ok = await handler.send_text("123456", "Hello **world**")

    assert mock_client.post.called


# ---------------------------------------------------------------------------
# 15. send_text returns False on API error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_text_returns_false_on_error():
    handler = make_handler()

    mock_resp = MagicMock()
    mock_resp.status_code = 401

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(handler, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        with patch("python.helpers.cortex_response_formatter.CortexResponseFormatter.format_for_telegram",
                   return_value="text", create=True):
            ok = await handler.send_text("123456", "test")

    assert ok is False


# ---------------------------------------------------------------------------
# 16. health_check: valid token → True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_check_valid_token():
    handler = make_handler()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"username": "cortex_bot"}}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch.object(handler, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        result = await handler.health_check()

    assert result is True


# ---------------------------------------------------------------------------
# 17. health_check: invalid token → False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_check_invalid_token():
    handler = make_handler()

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"ok": False}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch.object(handler, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        result = await handler.health_check()

    assert result is False


# ---------------------------------------------------------------------------
# 18. build_config_from_env: reads env var
# ---------------------------------------------------------------------------

def test_build_config_from_env():
    import os
    from python.helpers.cortex_telegram_bot import build_config_from_env

    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "env_token", "TELEGRAM_CHAT_ID": "99999"}):
        config = build_config_from_env(agent=None)

    assert config.bot_token == "env_token"
    assert config.chat_id == "99999"


# ---------------------------------------------------------------------------
# 19. _build_image_input: combines caption + analysis
# ---------------------------------------------------------------------------

def test_build_image_input_with_caption():
    from python.helpers.cortex_telegram_bot import _build_image_input

    analysis = {
        "summary": "Invoice document",
        "text_in_image": "Total: €840",
        "actionable_items": ["Approve payment"],
    }
    result = _build_image_input("Please check this", analysis)

    assert "Please check this" in result
    assert "Invoice document" in result
    assert "€840" in result
    assert "Approve payment" in result


# ---------------------------------------------------------------------------
# 20. _build_image_input: works with no caption
# ---------------------------------------------------------------------------

def test_build_image_input_no_caption():
    from python.helpers.cortex_telegram_bot import _build_image_input

    analysis = {"summary": "Screenshot of browser", "text_in_image": "", "actionable_items": []}
    result = _build_image_input(None, analysis)

    assert "Screenshot of browser" in result
    assert "[Image analysis]" in result
