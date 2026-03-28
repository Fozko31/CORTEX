# Phase F — Communication Layer: Complete
**Status: BUILT + LIVE TESTED** | *2026-03-27*

---

## What Was Built

Phase F gives CORTEX a full communication channel to the user — Telegram in, Telegram out, voice in, voice out, images, documents, formatted responses, and comprehension checks before starting work.

---

## F-1: Telegram Core

**What:** The bot handler that receives and routes every type of Telegram message.

**Files:**
- `python/helpers/cortex_telegram_bot.py` — `TelegramBotHandler`, routing, commands, digest
- `python/tools/telegram_ops.py` — Agent tool (send_message, send_voice, send_photo, morning_digest, health_check)
- `agents/cortex/prompts/agent.system.tool.telegram_ops.md` — Tool documentation

**What it handles:**
| Inbound | How |
|---------|-----|
| Text message | Route: command dispatch OR agent |
| Voice note | Download → STT → clean → agent → TTS back |
| Photo | Download → vision analysis → agent |
| Document | Download → parse → context inject or SurfSense push |

**Command replies (bypass agent):**
- `approve [id]` — approve a HITL action
- `reject [id] [reason]` — reject with optional reason
- `done [id]` — mark commitment done
- `health [venture]` — venture health check

**Morning digest:** HITL pending queue + active commitments + venture health → formatted brief.

---

## F-2: Voice Pipeline

**What:** Full push-to-talk voice cycle. User sends voice note → CORTEX responds with voice note.

**STT: Soniox** (`cortex_soniox_client.py`)
- Best Slovenian WER at 6.8% — outperforms Whisper (23.5%) and AssemblyAI (55.6%)
- Pay-as-you-go, ~$0.10/hr async
- Submit → poll pattern, 120s timeout
- Native .ogg support (Telegram format)

**Cleanup: DeepSeek V3.2** (`cortex_voice_cleaner.py`)
- Pass 1: Fast regex — Slovenian fillers (pač, torej, aja, hm), English fillers (um, uh, you know), repeated words, false starts, stutters
- Pass 2: DeepSeek V3.2 via OpenRouter — catches what regex misses, without changing meaning
- Degrades gracefully — never crashes the pipeline

**TTS: Language-routed** (`cortex_tts_router.py`)
- English → Kokoro local inference (zero cost, CPU-viable for async Telegram)
- Slovenian → Azure Neural TTS sl-SI: RokNeural (male), PetraNeural (female)
- Azure free tier: 0.5M chars/month — covers all realistic usage

**Language preferences** (natural language commands, stored in PersonalityModel):
- "Answer in Slovenian" / "Odgovori v slovenščini" → `force_sl`
- "Answer in English" / "Odgovori v angleščini" → `force_en`
- "Match my language" → `match_input` (default)

**PersonalityModel extended** with `preferences` dict (arbitrary string prefs):
- `tts_language_pref`: "force_sl" | "force_en" | "match_input"
- `comprehension_mode`: "compact" | "detailed" | "off"

---

## F-3: Image + Document Understanding

**What:** CORTEX can receive and understand photos and documents from Telegram.

**Vision: Two-step pipeline** (`cortex_vision_client.py`)
- Step 1: Gemini 2.5 Flash-Lite — raw image description (stable GA, not Preview)
- Step 2: DeepSeek V3.2 — structures into standard schema
- Cost: ~$0.001-0.003/image (vs $0.01-0.03 for Claude Sonnet)
- Output: `{summary, key_elements, text_in_image, data, ui_elements, actionable_items, requires_decision}`

**Documents** (`cortex_document_parser.py`)
- PDF via PyMuPDF, Word via python-docx, Excel via openpyxl, CSV + text built-in
- Size routing: < 24k chars → inject as context, ≥ 24k chars → chunk → SurfSense push
- Paragraph-boundary chunking — no mid-sentence cuts

---

## F-4: Response Formatting + Comprehension Check

**What:** Responses adapt to the medium they're delivered in, and CORTEX checks its understanding before starting work.

**Medium-aware formatter** (`cortex_response_formatter.py`)

| Medium | What happens |
|--------|-------------|
| Telegram | Tables → bullet lists, `•` bullets, code fences stripped, 4000-char limit enforced |
| Voice | All markdown stripped, `%`→"percent", `$50`→"50 dollars", `→`→"leads to", etc. |
| Web | Pass-through unchanged |

**Comprehension check** (`python/extensions/monologue_start/_08_comprehension_check.py`)
- Fires before CORTEX starts any action-oriented task
- Detects action verbs (40+ EN + SL verbs) and skips pure questions
- Default: compact 4-line format

```
Task:       [what was asked]
Constraint: [key constraints]
Assuming:   [what CORTEX is assuming ← catches wrong assumptions before work begins]
Action:     [first step]
```

- "more" / "full breakdown" → detailed 7-line format
- Can be disabled: "turn off comprehension check"
- Mode stored persistently in PersonalityModel

**Language rules added to role prompt:**
- Automatic language matching (SL ↔ EN)
- Honor "answer in Slovenian" / "odgovori v angleščini" commands persistently
- Perfect standard Slovenian — no dialect mixing, no calques

---

## New Environment Variables

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot authentication |
| `TELEGRAM_CHAT_ID` | User's personal chat ID |
| `SONIOX_API_KEY` | STT — get at soniox.com |
| `AZURE_SPEECH_KEY` | TTS Slovenian — Azure Cognitive Services |
| `AZURE_SPEECH_REGION` | Default: westeurope |

---

## New Dependencies (requirements.txt)

```
python-docx>=1.1.0
openpyxl>=3.1.0
langdetect>=1.0.9
azure-cognitiveservices-speech>=1.40.0
```

(kokoro, soundfile, PyMuPDF, httpx already present from prior phases)

---

## Test Coverage

| Suite | Tests | Status |
|-------|-------|--------|
| F-1 Telegram Core | 20 | Mocked — PASS |
| F-2 Voice Pipeline | 22 | Mocked — PASS |
| F-3 Vision + Documents | 20 | Mocked — PASS |
| F-4 Formatting + Comprehension | 18 | Mocked — PASS |
| **Live free tests** | **13** | **Live — PASS (user confirmed in Telegram)** |
| **Total Phase F** | **93** | **All passing** |

### Bugs found during live testing (all fixed)
1. `send_text` called `CortexResponseFormatter.format_for_telegram(text)` as a class method — missing `()` to instantiate. Fixed to `CortexResponseFormatter().format_for_telegram(text)`.
2. Dollar regex `\$(\d)` captured only one digit — `$50` → `5 dollars0`. Fixed to `\$(\d+)`.
3. TTS router skipped `get_pref()` when `agent=None` — force_sl preference ignored. Fixed to always call `get_pref`.
4. `pytest-asyncio` not installed — all async tests silently skipped. Installed + `pytest.ini` with `asyncio_mode = auto` created.

### Live test confirmed working (2026-03-27)
- Bot health check: CONNECTED
- Text message sent to Telegram: CONFIRMED by user
- Morning digest sent to Telegram: CONFIRMED by user
- Kokoro TTS voice note sent to Telegram: CONFIRMED by user (477KB WAV)
- Gemini 2.0 Flash-Lite on OpenRouter: HTTP 200 confirmed
- Gemini correct model ID: `google/gemini-2.0-flash-lite-001` (NOT the date-suffixed preview variant)

---

## What's Deferred

- **Real-time voice** (Twilio + streaming): deferred to Phase H — needs GPU on Fly.io for sub-1s Kokoro latency
- **Web UI voice** (React microphone): deferred to Phase H frontend
- **Diagram rendering** (Mermaid/Chart.js): deferred to Phase H
- **Azure TTS streaming** for real-time: deferred with real-time voice

---

## Next Phase

**Phase G: Self-Improvement Loop** — struggle_detect → hypothesis → experiment → judge cycle (DSPy). See `project_self_improvement_plan.md`.

Or the currently planned sequence: **Phase H** (React + FastAPI frontend + voice in browser + per-venture windows).

Check `CORTEX_PROGRESS.md` for current status.
