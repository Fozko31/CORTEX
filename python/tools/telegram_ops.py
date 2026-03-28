"""
telegram_ops tool — Telegram Communication Operations
======================================================
Agent-callable interface for all Telegram communication.

Operations:
    send_message     — send text to user's Telegram chat
    send_voice       — send voice note (audio bytes as base64)
    send_photo       — send image (for browser screenshots, charts)
    morning_digest   — compile HITL + health + commitments → send
    health_check     — verify bot connection
"""

import json
import os
from python.helpers.tool import Tool, Response


class TelegramOps(Tool):

    async def execute(self, **kwargs) -> Response:
        operation = kwargs.get("operation", "").lower().strip()

        dispatch = {
            "send_message":    self._send_message,
            "send_voice":      self._send_voice,
            "send_photo":      self._send_photo,
            "morning_digest":  self._morning_digest,
            "health_check":    self._health_check,
        }

        handler = dispatch.get(operation)
        if not handler:
            ops = ", ".join(dispatch.keys())
            return Response(
                message=f"Unknown operation '{operation}'. Available: {ops}",
                break_loop=False,
            )

        try:
            result = await handler(**kwargs)
            return Response(message=json.dumps(result, indent=2), break_loop=False)
        except Exception as e:
            return Response(
                message=json.dumps({"status": "error", "error": str(e)}),
                break_loop=False,
            )

    # ------------------------------------------------------------------
    # send_message
    # ------------------------------------------------------------------

    async def _send_message(self, **kwargs) -> dict:
        text = kwargs.get("text", "")
        chat_id = kwargs.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
        if not text:
            return {"status": "error", "error": "text is required"}
        if not chat_id:
            return {"status": "error", "error": "chat_id not configured"}

        handler = await self._get_handler()
        ok = await handler.send_text(chat_id, text)
        return {"status": "ok" if ok else "error", "chat_id": chat_id}

    # ------------------------------------------------------------------
    # send_voice
    # ------------------------------------------------------------------

    async def _send_voice(self, **kwargs) -> dict:
        """
        Send a voice note. Accepts either:
          audio_b64: base64-encoded audio bytes
          text: text to synthesize via TTS and send
        """
        import base64
        chat_id = kwargs.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
        if not chat_id:
            return {"status": "error", "error": "chat_id not configured"}

        audio_b64 = kwargs.get("audio_b64")
        text = kwargs.get("text")

        if audio_b64:
            audio_bytes = base64.b64decode(audio_b64)
        elif text:
            from python.helpers.cortex_tts_router import CortexTTSRouter
            audio_bytes = await CortexTTSRouter.route(text, "en", self.agent)
            if not audio_bytes:
                # TTS unavailable — send as text instead
                handler = await self._get_handler()
                ok = await handler.send_text(chat_id, text)
                return {"status": "ok" if ok else "error", "chat_id": chat_id, "fallback": "text"}
        else:
            return {"status": "error", "error": "audio_b64 or text required"}

        handler = await self._get_handler()
        ok = await handler.send_voice(chat_id, audio_bytes)
        return {"status": "ok" if ok else "error", "chat_id": chat_id}

    # ------------------------------------------------------------------
    # send_photo
    # ------------------------------------------------------------------

    async def _send_photo(self, **kwargs) -> dict:
        """
        Send an image. Accepts:
          image_b64: base64-encoded PNG/JPEG bytes
          caption: optional caption text
        """
        import base64
        chat_id = kwargs.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
        image_b64 = kwargs.get("image_b64", "")
        caption = kwargs.get("caption", "")

        if not chat_id:
            return {"status": "error", "error": "chat_id not configured"}
        if not image_b64:
            return {"status": "error", "error": "image_b64 required"}

        image_bytes = base64.b64decode(image_b64)
        handler = await self._get_handler()
        ok = await handler.send_photo(chat_id, image_bytes, caption)
        return {"status": "ok" if ok else "error", "chat_id": chat_id}

    # ------------------------------------------------------------------
    # morning_digest
    # ------------------------------------------------------------------

    async def _morning_digest(self, **kwargs) -> dict:
        chat_id = kwargs.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
        if not chat_id:
            return {"status": "error", "error": "chat_id not configured"}

        handler = await self._get_handler()
        digest_text = await handler.send_morning_digest(chat_id)
        ok = await handler.send_text(chat_id, digest_text)
        return {
            "status": "ok" if ok else "error",
            "digest_length": len(digest_text),
        }

    # ------------------------------------------------------------------
    # health_check
    # ------------------------------------------------------------------

    async def _health_check(self, **kwargs) -> dict:
        try:
            handler = await self._get_handler()
            ok = await handler.health_check()
            return {"status": "ok" if ok else "error", "bot_connected": ok}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_handler(self):
        from python.helpers.cortex_telegram_bot import TelegramBotHandler, build_config_from_env
        config = build_config_from_env(self.agent)
        return TelegramBotHandler(config, agent=self.agent)
