# telegram_ops

Send messages, voice notes, and images to the user via Telegram. Surface HITL approvals, venture health, and commitments in the morning digest.

## When to use

- Any time you need to reach the user on their phone
- Sending browser screenshots for mobile approval
- Morning digest (triggered by scheduler)
- Responding with voice when the user spoke to you via voice

## Operations

### send_message

Send a text message to the user's Telegram.

```json
{
  "tool_name": "telegram_ops",
  "operation": "send_message",
  "text": "The invoice for Kovač d.o.o. is ready for your review.",
  "chat_id": ""
}
```

`chat_id` is optional — defaults to `TELEGRAM_CHAT_ID` env var (the user's personal chat).

---

### send_voice

Send a voice note. Provide either pre-generated audio (`audio_b64`) or text to synthesize via TTS.

```json
{
  "tool_name": "telegram_ops",
  "operation": "send_voice",
  "text": "Good morning. You have two pending approvals.",
  "chat_id": ""
}
```

TTS routing is automatic: English → Kokoro (local), Slovenian → Azure Neural (sl-SI). Language is detected from the text.

---

### send_photo

Send an image to the user. Use for browser screenshots, charts, or any visual that requires the user's review.

```json
{
  "tool_name": "telegram_ops",
  "operation": "send_photo",
  "image_b64": "<base64-encoded PNG or JPEG>",
  "caption": "I'm at the payment confirmation step. Which card should I use?",
  "chat_id": ""
}
```

---

### morning_digest

Compile the HITL pending queue, active commitments, and venture health into a morning brief and send it. Triggered by the scheduler at the user's configured time (default 07:00).

```json
{
  "tool_name": "telegram_ops",
  "operation": "morning_digest",
  "chat_id": ""
}
```

---

### health_check

Verify the bot token is valid and Telegram is reachable.

```json
{
  "tool_name": "telegram_ops",
  "operation": "health_check"
}
```

Returns `{"status": "ok", "bot_connected": true}`.

---

## User command replies (inbound — handled automatically)

When the user replies via Telegram with these commands, they bypass the full reasoning loop and execute directly:

| Command | Action |
|---------|--------|
| `approve [id]` | Approve a HITL action by ID |
| `reject [id] [reason]` | Reject a HITL action |
| `done [id]` | Mark a commitment as done |
| `health [venture]` | Get venture health summary |
| `more` / `full breakdown` | Get detailed comprehension check |

---

## Rules

- Never send sensitive data (credentials, raw values) via Telegram
- Always use `send_photo` when the user needs to see a visual to make a decision
- For voice responses: the TTS engine handles language routing — just pass the text
- `chat_id` defaults to the user's personal chat — only override for multi-user setups (future)
