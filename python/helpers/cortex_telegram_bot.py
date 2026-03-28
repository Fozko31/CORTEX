"""
CORTEX Telegram Bot — F-1 Communication Layer
=============================================
Handles all inbound/outbound Telegram communication.

Message routing:
  text     → direct CORTEX input
  voice    → STT pipeline (F-2) → CORTEX
  photo    → vision pipeline (F-3) → CORTEX
  document → parser pipeline (F-3) → CORTEX or SurfSense
  command replies (approve/reject/done/health) → direct function calls

Run modes:
  polling  → local development (python -m python.helpers.cortex_telegram_bot)
  webhook  → Fly.io production (TELEGRAM_WEBHOOK_URL set)

Bot token: read from credential vault at startup.
  vault key: "telegram_bot_token"
  fallback:  TELEGRAM_BOT_TOKEN env var
"""

import asyncio
import io
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Command-reply pattern matching
# ---------------------------------------------------------------------------

_RE_APPROVE = re.compile(r"^\s*approve\s+([A-Za-z0-9_-]+)\s*$", re.IGNORECASE)
_RE_REJECT  = re.compile(r"^\s*reject\s+([A-Za-z0-9_-]+)(?:\s+(.+))?\s*$", re.IGNORECASE)
_RE_DONE    = re.compile(r"^\s*done\s+([A-Za-z0-9_-]+)\s*$", re.IGNORECASE)
_RE_HEALTH  = re.compile(r"^\s*health(?:\s+([A-Za-z0-9_-]+))?\s*$", re.IGNORECASE)
_RE_MORE    = re.compile(r"^\s*(more|full breakdown|details|detailed)\s*$", re.IGNORECASE)


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str
    digest_time: str = "07:00"
    webhook_url: str = ""


@dataclass
class InboundMessage:
    """Normalised representation of any inbound Telegram message."""
    chat_id: str
    message_id: int
    text: Optional[str] = None
    voice_bytes: Optional[bytes] = None
    voice_mime: str = "audio/ogg"
    photo_bytes: Optional[bytes] = None
    document_bytes: Optional[bytes] = None
    document_filename: str = ""
    document_mime: str = ""
    raw_update: Optional[dict] = None


@dataclass
class DigestData:
    hitl_items: list = field(default_factory=list)
    venture_health: list = field(default_factory=list)
    commitments: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core handler
# ---------------------------------------------------------------------------

class TelegramBotHandler:
    """
    Stateless handler for Telegram updates.
    All heavy work is delegated to the pipeline helpers (F-2, F-3) and the
    agent so this class stays thin and easily testable.
    """

    def __init__(self, config: TelegramConfig, agent=None):
        self.config = config
        self.agent = agent
        self._http_client = None

    # ------------------------------------------------------------------
    # HTTP client (lazy, shared)
    # ------------------------------------------------------------------

    async def _get_client(self):
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(timeout=60.0)
        return self._http_client

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    async def handle_update(self, update: dict) -> Optional[str]:
        """
        Route a raw Telegram update dict to the correct handler.
        Returns the response text (or None if handled by sub-pipeline).
        """
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return None

        chat_id = str(msg.get("chat", {}).get("id", ""))
        message_id = msg.get("message_id", 0)

        # Text message
        if "text" in msg:
            return await self.handle_text(msg["text"], chat_id, message_id)

        # Voice note
        if "voice" in msg or "audio" in msg:
            media = msg.get("voice") or msg.get("audio")
            file_id = media.get("file_id", "")
            audio_bytes = await self._download_file(file_id)
            inbound = InboundMessage(
                chat_id=chat_id,
                message_id=message_id,
                voice_bytes=audio_bytes,
                raw_update=update,
            )
            return await self.handle_voice(inbound)

        # Photo
        if "photo" in msg:
            # Telegram sends multiple sizes; take the largest
            photos = msg["photo"]
            file_id = photos[-1]["file_id"]
            image_bytes = await self._download_file(file_id)
            caption = msg.get("caption", "")
            inbound = InboundMessage(
                chat_id=chat_id,
                message_id=message_id,
                photo_bytes=image_bytes,
                text=caption or None,
                raw_update=update,
            )
            return await self.handle_photo(inbound)

        # Document / file
        if "document" in msg:
            doc = msg["document"]
            file_id = doc.get("file_id", "")
            filename = doc.get("file_name", "document")
            mime = doc.get("mime_type", "")
            doc_bytes = await self._download_file(file_id)
            caption = msg.get("caption", "")
            inbound = InboundMessage(
                chat_id=chat_id,
                message_id=message_id,
                document_bytes=doc_bytes,
                document_filename=filename,
                document_mime=mime,
                text=caption or None,
                raw_update=update,
            )
            return await self.handle_document(inbound)

        return None

    # ------------------------------------------------------------------
    # Text handler
    # ------------------------------------------------------------------

    async def handle_text(self, text: str, chat_id: str, message_id: int = 0) -> str:
        """
        Route text to command handler or CORTEX agent.
        Returns the response string.
        """
        stripped = text.strip()

        # Command: approve [id]
        m = _RE_APPROVE.match(stripped)
        if m:
            return await self._cmd_approve(m.group(1), chat_id)

        # Command: reject [id] [optional reason]
        m = _RE_REJECT.match(stripped)
        if m:
            return await self._cmd_reject(m.group(1), m.group(2), chat_id)

        # Command: done [id]
        m = _RE_DONE.match(stripped)
        if m:
            return await self._cmd_done(m.group(1), chat_id)

        # Command: health [venture]
        m = _RE_HEALTH.match(stripped)
        if m:
            return await self._cmd_health(m.group(1), chat_id)

        # Pass to CORTEX agent (if agent wired up)
        return await self._route_to_agent(stripped, chat_id)

    # ------------------------------------------------------------------
    # Voice handler
    # ------------------------------------------------------------------

    async def handle_voice(self, inbound: InboundMessage) -> str:
        """
        STT pipeline: audio bytes → transcript → clean → agent.
        Returns the text response (caller sends as voice note).
        """
        if not inbound.voice_bytes:
            return "No audio received."

        try:
            from python.helpers.cortex_soniox_client import CortexSonioxClient
            from python.helpers.cortex_voice_cleaner import CortexVoiceCleaner

            client = CortexSonioxClient.from_agent_config(self.agent)
            raw_text = await client.transcribe(inbound.voice_bytes)
            cleaner = CortexVoiceCleaner.from_agent_config(self.agent)
            clean_text = await cleaner.clean(raw_text)
            return await self._route_to_agent(clean_text, inbound.chat_id)

        except Exception as e:
            logger.error("Voice pipeline error: %s", e)
            return f"Voice processing failed: {e}"

    # ------------------------------------------------------------------
    # Photo handler
    # ------------------------------------------------------------------

    async def handle_photo(self, inbound: InboundMessage) -> str:
        """
        Vision pipeline: image bytes → structured analysis → agent.
        """
        if not inbound.photo_bytes:
            return "No image received."

        try:
            from python.helpers.cortex_vision_client import CortexVisionClient
            client = CortexVisionClient.from_agent_config(self.agent)
            analysis = await client.analyze(
                inbound.photo_bytes,
                context=inbound.text or "",
            )
            combined_input = _build_image_input(inbound.text, analysis)
            return await self._route_to_agent(combined_input, inbound.chat_id)

        except Exception as e:
            logger.error("Vision pipeline error: %s", e)
            return f"Image processing failed: {e}"

    # ------------------------------------------------------------------
    # Document handler
    # ------------------------------------------------------------------

    async def handle_document(self, inbound: InboundMessage) -> str:
        """
        Document pipeline: file bytes → parsed content → inject or SurfSense.
        """
        if not inbound.document_bytes:
            return "No document received."

        try:
            from python.helpers.cortex_document_parser import CortexDocumentParser
            parser = CortexDocumentParser()
            parsed = await parser.parse(inbound.document_bytes, inbound.document_filename)

            # Small doc: inject as context
            if parsed.token_estimate < 8000:
                combined = (
                    f"[Document: {parsed.filename} ({parsed.mime_type})]\n\n"
                    + (parsed.text if not parsed.chunks else "\n\n".join(parsed.chunks))
                )
                if inbound.text:
                    combined = f"{inbound.text}\n\n{combined}"
                return await self._route_to_agent(combined, inbound.chat_id)

            # Large doc: push to SurfSense
            await self._ingest_to_surfsense(parsed)
            return (
                f"Document ingested: '{parsed.filename}' ({parsed.mime_type}, "
                f"~{parsed.token_estimate:,} tokens). Ask me anything about it."
            )

        except Exception as e:
            logger.error("Document pipeline error: %s", e)
            return f"Document processing failed: {e}"

    # ------------------------------------------------------------------
    # Digest
    # ------------------------------------------------------------------

    async def send_morning_digest(self, chat_id: str) -> str:
        """
        Compile HITL pending + venture health + commitments → format → return text.
        Caller is responsible for sending.
        """
        data = await self._collect_digest_data()
        return _format_digest(data)

    async def _collect_digest_data(self) -> DigestData:
        data = DigestData()

        try:
            from python.helpers.cortex_venture_action_log import VentureActionLog
            log = VentureActionLog()
            data.hitl_items = log.list_pending() or []
        except Exception:
            pass

        try:
            from python.helpers.cortex_commitment_tracker import CommitmentTracker
            tracker = CommitmentTracker.load(self.agent)
            data.commitments = tracker.get_active() or []
        except Exception:
            pass

        return data

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------

    async def send_text(self, chat_id: str, text: str) -> bool:
        """Send a text message via Telegram Bot API."""
        try:
            from python.helpers.cortex_response_formatter import CortexResponseFormatter
            formatted = CortexResponseFormatter().format_for_telegram(text)
            client = await self._get_client()
            resp = await client.post(
                f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": formatted, "parse_mode": "Markdown"},
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("send_text error: %s", e)
            return False

    async def send_voice(self, chat_id: str, audio_bytes: bytes) -> bool:
        """Send an audio/voice note via Telegram Bot API."""
        try:
            client = await self._get_client()
            resp = await client.post(
                f"https://api.telegram.org/bot{self.config.bot_token}/sendVoice",
                data={"chat_id": chat_id},
                files={"voice": ("voice.ogg", io.BytesIO(audio_bytes), "audio/ogg")},
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("send_voice error: %s", e)
            return False

    async def send_photo(self, chat_id: str, image_bytes: bytes, caption: str = "") -> bool:
        """Send a photo via Telegram Bot API."""
        try:
            client = await self._get_client()
            resp = await client.post(
                f"https://api.telegram.org/bot{self.config.bot_token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": ("image.png", io.BytesIO(image_bytes), "image/png")},
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("send_photo error: %s", e)
            return False

    async def health_check(self) -> bool:
        """Verify bot token is valid via getMe."""
        try:
            client = await self._get_client()
            resp = await client.get(
                f"https://api.telegram.org/bot{self.config.bot_token}/getMe",
                timeout=10.0,
            )
            return resp.status_code == 200 and resp.json().get("ok") is True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Command handlers (bypass full agent loop for speed)
    # ------------------------------------------------------------------

    async def _cmd_approve(self, action_id: str, chat_id: str) -> str:
        try:
            from python.helpers.cortex_venture_action_log import VentureActionLog
            log = VentureActionLog()
            log.approve(action_id)
            return f"✓ Action {action_id} approved."
        except Exception as e:
            return f"Could not approve {action_id}: {e}"

    async def _cmd_reject(self, action_id: str, reason: Optional[str], chat_id: str) -> str:
        try:
            from python.helpers.cortex_venture_action_log import VentureActionLog
            log = VentureActionLog()
            log.reject(action_id, reason=reason or "")
            return f"✗ Action {action_id} rejected."
        except Exception as e:
            return f"Could not reject {action_id}: {e}"

    async def _cmd_done(self, commitment_id: str, chat_id: str) -> str:
        try:
            from python.helpers.cortex_commitment_tracker import CommitmentTracker
            tracker = CommitmentTracker.load(self.agent)
            tracker.mark_done(commitment_id, agent=self.agent)
            tracker.save(self.agent)
            return f"✓ Commitment {commitment_id} marked done."
        except Exception as e:
            return f"Could not mark {commitment_id} done: {e}"

    async def _cmd_health(self, venture_slug: Optional[str], chat_id: str) -> str:
        try:
            from python.helpers.cortex_venture_task_queue import VentureTaskQueue
            from python.helpers.cortex_venture_action_log import VentureActionLog
            queue = VentureTaskQueue()
            log = VentureActionLog()

            if venture_slug:
                tasks = queue.list_tasks(venture_slug=venture_slug)
                pending = log.pending_count(venture_slug)
                return (
                    f"**{venture_slug} Health**\n"
                    f"Active tasks: {len([t for t in tasks if t.get('enabled')])}\n"
                    f"Pending approvals: {pending}"
                )
            return "Specify a venture: health moving_co"
        except Exception as e:
            return f"Health check failed: {e}"

    # ------------------------------------------------------------------
    # Agent routing
    # ------------------------------------------------------------------

    async def _route_to_agent(self, text: str, chat_id: str) -> str:
        """
        Pass text to the CORTEX agent and return the response.
        In production this hooks into Agent Zero's message processing.
        In tests agent=None → return echo for assertion.
        """
        if self.agent is None:
            return f"[AGENT]: {text}"
        try:
            # Agent Zero's process_message equivalent
            response = await self.agent.message_loop(text)
            return response or ""
        except Exception as e:
            logger.error("Agent routing error: %s", e)
            return f"Processing error: {e}"

    # ------------------------------------------------------------------
    # SurfSense ingestion
    # ------------------------------------------------------------------

    async def _ingest_to_surfsense(self, parsed) -> None:
        """Push a large parsed document to SurfSense."""
        try:
            from python.helpers.cortex_surfsense_client import CortexSurfSenseClient
            from python.helpers.cortex_ingestion_schema import build_document

            client = CortexSurfSenseClient.from_agent_config(self.agent)
            if client is None:
                logger.warning("SurfSense not configured — skipping document ingest")
                return
            space = "cortex_main"  # default; venture-aware routing in future
            chunks = parsed.chunks if parsed.chunks else [parsed.text]
            for i, chunk in enumerate(chunks):
                doc = build_document(
                    content=chunk,
                    category="research",
                    source="user_upload",
                    topic=f"{parsed.filename} (part {i+1})",
                    summary_level="raw",
                )
                await client.push_document(space, {
                    "title": doc["title"],
                    "content": doc["content"],
                    "metadata": doc.get("metadata", {}),
                })
        except Exception as e:
            logger.warning("SurfSense ingestion failed: %s", e)

    # ------------------------------------------------------------------
    # Telegram file download
    # ------------------------------------------------------------------

    async def _download_file(self, file_id: str) -> bytes:
        """Download a file from Telegram servers given its file_id."""
        client = await self._get_client()
        # Step 1: get file path
        resp = await client.get(
            f"https://api.telegram.org/bot{self.config.bot_token}/getFile",
            params={"file_id": file_id},
        )
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]

        # Step 2: download
        dl_url = f"https://api.telegram.org/file/bot{self.config.bot_token}/{file_path}"
        dl_resp = await client.get(dl_url)
        dl_resp.raise_for_status()
        return dl_resp.content


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_config_from_env(agent=None) -> TelegramConfig:
    """
    Build TelegramConfig from environment / credential vault.
    Vault takes priority over env var for the bot token.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")

    if agent:
        try:
            from python.helpers.cortex_credential_vault import CortexCredentialVault
            vault = CortexCredentialVault("_global")
            vault_token = vault.get("telegram_bot_token")
            if vault_token:
                token = vault_token
        except Exception:
            pass

    return TelegramConfig(
        bot_token=token,
        chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        digest_time=os.getenv("TELEGRAM_DIGEST_TIME", "07:00"),
        webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL", ""),
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _build_image_input(caption: Optional[str], analysis: dict) -> str:
    """Combine user caption + vision analysis into a single agent input."""
    parts = []
    if caption:
        parts.append(caption)
    parts.append("[Image analysis]")
    if analysis.get("summary"):
        parts.append(f"Summary: {analysis['summary']}")
    if analysis.get("text_in_image"):
        parts.append(f"Text visible: {analysis['text_in_image']}")
    if analysis.get("actionable_items"):
        items = analysis["actionable_items"]
        if isinstance(items, list):
            parts.append("Requires action: " + "; ".join(items))
    return "\n".join(parts)


def _format_digest(data: DigestData) -> str:
    """Format morning digest as Telegram-ready text."""
    now = datetime.now().strftime("%H:%M")
    lines = [f"Good morning. Here's your {now} brief:\n"]

    if data.hitl_items:
        lines.append(f"*PENDING APPROVALS ({len(data.hitl_items)})*")
        for item in data.hitl_items[:10]:  # cap at 10 for readability
            aid = item.get("action_id", "?")[:8]
            atype = item.get("action_type", "action")
            venture = item.get("venture_slug", "")
            cost = item.get("cost_estimate")
            cost_str = f" — €{cost:.2f}" if cost else ""
            lines.append(f"[{aid}] {atype}{cost_str} — {venture}")
        lines.append("→ Reply `approve [id]` or `reject [id]`\n")
    else:
        lines.append("✓ No pending approvals\n")

    if data.commitments:
        active = [c for c in data.commitments if getattr(c, "status", "") in ("pending", "overdue")]
        if active:
            lines.append(f"*COMMITMENTS ({len(active)})*")
            for c in active[:5]:
                flag = " [OVERDUE]" if getattr(c, "status", "") == "overdue" else ""
                due = f" (due: {c.due_date})" if getattr(c, "due_date", None) else ""
                cid = getattr(c, "id", "?")
                lines.append(f"[{cid}] {c.text}{due}{flag}")
            lines.append("→ Reply `done [id]` to mark complete\n")

    if not data.hitl_items and not data.commitments:
        lines.append("All clear. Nothing pending.")

    return "\n".join(lines)
