# CORTEX Phase F — Communication Layer Design

**Status:** DESIGN COMPLETE — ready to build
**Designed:** 2026-03-27
**Next:** Implementation session → `CORTEX_PHASE_F_SUMMARY.md` + `phase_f_architecture.md` after build

---

## What Phase F Builds

Phase F is the communication layer. Everything before Phase F is intelligence without a usable interface. Phase F makes CORTEX genuinely operational on a daily basis — accessible via mobile (Telegram), voice-capable in both directions, able to understand images and documents, and structured in how it presents information.

The design principle: **communication is not a feature, it is the product.** A business partner you can't reach or can't understand clearly is not a partner.

---

## Sub-Phase Build Order

| Sub-phase | What | Dependencies |
|-----------|------|-------------|
| F-1 | Telegram Core — bot, message routing, HITL digest | None |
| F-2 | Voice Pipeline — STT, cleanup, TTS, language routing | F-1 |
| F-3 | Image + Document — vision agent, file parser, SurfSense | F-1 |
| F-4 | Response Formatting + Comprehension Check | F-1, F-2, F-3 |

---

## F-1: Telegram Core

### What it does

Telegram is the mobile interface for Phase F. The user can:
- Send text messages → CORTEX processes and responds
- Send voice messages → STT pipeline (F-2) → CORTEX responds
- Send photos → vision pipeline (F-3) → CORTEX responds
- Send files → document parser (F-3) → CORTEX ingests or responds
- Reply to approve/reject HITL actions by ID
- Receive morning digest with pending approvals + venture health

### Files Created

**`python/helpers/cortex_telegram_bot.py`**

```
class TelegramBotHandler:
  handle_message(update)          → routes by message type
  handle_text(update)             → direct CORTEX input
  handle_voice(update)            → download .ogg → F-2 STT pipeline
  handle_photo(update)            → download image → F-3 vision pipeline
  handle_document(update)         → download file → F-3 parser pipeline
  handle_command_reply(update)    → detect "approve X" / "reject X" → venture_ops
  send_text(chat_id, text)        → formatted Telegram text response
  send_voice(chat_id, audio_bytes)→ voice note response
  send_photo(chat_id, img, caption) → image with caption (for screenshots)
  send_morning_digest(chat_id)    → HITL queue + health + commitments
  run_polling()                   → local dev mode
  run_webhook(url, port)          → Fly.io production mode
```

**`python/tools/telegram_ops.py`**

Agent-callable tool. Operations:
- `send_message` — send text to user's Telegram
- `send_voice` — send voice note
- `send_photo` — send image (browser screenshots, charts)
- `morning_digest` — compile HITL + health + commitments → send
- `health_check` — verify bot is connected

**`agents/cortex/prompts/agent.system.tool.telegram_ops.md`**

Prompt doc documenting all telegram_ops operations for CORTEX.

### Bot Token Storage

Stored in credential vault: `venture_ops set_credential("telegram_bot_token", ...)`. Never in plaintext or environment variable directly. Retrieved at bot startup via vault `get()`.

### HITL Morning Digest Format

```
Good morning. Here's your 07:00 brief:

PENDING APPROVALS (2)
[A001] Send invoice to Kovač d.o.o. — €840 — Moving Co
[A002] Post LinkedIn update — content attached — Moving Co
→ Reply "approve A001" or "reject A001 [reason]"

VENTURE HEALTH
Moving Co: Active | 3 tasks scheduled | Last activity: yesterday
→ Reply "health moving_co" for full report

COMMITMENTS DUE
[C4a1] Draft Q2 pricing review — due today
→ Reply "done C4a1" to mark complete
```

### Command Reply Detection

Pattern matching on incoming Telegram text:
- `approve [id]` → `venture_ops approve(action_id)`
- `reject [id]` / `reject [id] reason` → `venture_ops reject(action_id, reason)`
- `done [id]` → CommitmentTracker.mark_done(id)
- `health [venture]` → `venture_ops health_check(venture_slug)`

All command replies bypass the full CORTEX reasoning loop — direct function calls for speed.

### Configuration

```python
# usr/.env additions
TELEGRAM_BOT_TOKEN=...          # overridden by credential vault at runtime
TELEGRAM_CHAT_ID=...            # user's personal chat ID (set on first /start)
TELEGRAM_DIGEST_TIME=07:00      # morning digest schedule (user's local time)
TELEGRAM_WEBHOOK_URL=...        # Fly.io webhook URL (production)
```

### Tests: `tests/test_f1_telegram_core.py` (target: 20 tests)

- Bot handler routes text → correct handler
- Bot handler routes voice → STT handler called
- Bot handler routes photo → vision handler called
- Bot handler routes document → parser handler called
- Command reply detection: approve/reject/done/health
- Morning digest format: includes HITL items, health, commitments
- Morning digest empty state: correct message when nothing pending
- send_text formats Telegram-correctly (no markdown tables)
- Credential vault integration: bot token read from vault
- HITL action execute after approve reply

---

## F-2: Voice Pipeline

### Architecture

```
Telegram voice message (.ogg)
  ↓
cortex_soniox_client.py
  → Soniox async transcription API
  → Raw Slovenian/English text (6.8% WER for Slovenian)
  ↓
cortex_voice_cleaner.py
  → DeepSeek V3.2
  → System prompt: Slovenian + English filler patterns
  → Filler removal, false starts, self-corrections, punctuation
  → Clean text
  ↓
Language detection (langdetect or simple heuristic)
  → "sl" or "en"
  ↓
CORTEX processes clean text as normal message
  ↓
cortex_tts_router.py
  → if tts_pref == "english" or (tts_pref == "match_input" and lang == "en"):
       cortex_kokoro_tts.py → audio bytes (local, private)
  → if tts_pref == "slovenian" or (tts_pref == "match_input" and lang == "sl"):
       cortex_azure_tts.py → audio bytes (Azure Neural, sl-SI)
  ↓
Audio bytes → TelegramBotHandler.send_voice()
```

### Files Created

**`python/helpers/cortex_soniox_client.py`**

```
class CortexSonioxClient:
  from_agent_config(agent)    → reads SONIOX_API_KEY from env
  transcribe(audio_bytes, language_hint=None) → str
    → POST to Soniox async transcription endpoint
    → poll for result (or use streaming if real-time needed)
    → returns raw transcript text
  health_check()              → bool
```

Soniox API: `https://api.soniox.com/v1/transcribe`
Supported audio: `.ogg`, `.mp3`, `.wav`, `.m4a` — Telegram delivers `.ogg`
Language auto-detection: Soniox detects language automatically (no hint needed unless forcing)

**`python/helpers/cortex_voice_cleaner.py`**

```
CLEANUP_SYSTEM_PROMPT = """
You are a voice transcript cleanup engine. You receive raw speech-to-text output
and return clean, readable text. Rules:

Remove ONLY speech artifacts:
- Filler words: English: "um", "uh", "you know", "like", "so", "right"
  Slovenian: "a", "no", "aja", "pač", "torej", "hm", "ee", "mmm"
- False starts: "I want to — actually I need to" → "I need to"
- Self-corrections: "Monday, no wait, Tuesday" → "Tuesday"
- Repetitions: "the the plan" → "the plan"

Preserve EXACTLY:
- All meaning and content
- Speaker's vocabulary and register (formal stays formal, casual stays casual)
- Technical terms, proper nouns, numbers, dates
- Language (do NOT translate — if input is Slovenian, output is Slovenian)

Do NOT:
- Rephrase for clarity or elegance
- Add content not in the original
- Change sentence structure unless removing a false start

Return ONLY the cleaned text. No explanations.
"""

async def clean_transcript(raw_text: str, agent) -> str:
    → CortexModelRouter.call_routed_model("classification", CLEANUP_SYSTEM_PROMPT, raw_text, agent)
    → returns clean text
```

Note: We route cleanup through "classification" task type (DeepSeek V3.2) — it is a classification/transformation task. No new task type needed.

**`python/helpers/cortex_kokoro_tts.py`**

```
class CortexKokoroTTS:
  synthesize(text: str, voice: str = "af_heart") → bytes
    → kokoro.generate(text, voice=voice)
    → returns WAV bytes
  available_voices() → list[str]
  is_available() → bool  (checks if kokoro package installed + model downloaded)
```

Kokoro setup: `pip install kokoro-onnx soundfile`
First run downloads ONNX model (~300MB). Cached locally.
CPU inference: ~1-3s for typical response length (acceptable for async Telegram).

**`python/helpers/cortex_azure_tts.py`**

```
class CortexAzureTTS:
  from_agent_config(agent)    → reads AZURE_SPEECH_KEY, AZURE_SPEECH_REGION from env
  synthesize(text: str, voice: str = "sl-SI-RokNeural") → bytes
    → Azure Speech SDK: SpeechSynthesizer.speak_text_async()
    → returns WAV bytes
  available_voices()          → ["sl-SI-RokNeural", "sl-SI-PetraNeural"]
  health_check()              → bool
```

Azure free tier: 500,000 standard chars/month free. Neural voices: 0.5M chars/month free.
Slovenian responses are typically short → essentially free at launch volume.

**`python/helpers/cortex_tts_router.py`**

```
TTS_PREF_KEY = "tts_output_language"   # stored in PersonalityModel

class CortexTTSRouter:
  route(text: str, detected_lang: str, agent) → bytes
    → pref = PersonalityModel.load(agent).dimensions.get(TTS_PREF_KEY, "match_input")
    → if pref == "english" or (pref == "match_input" and detected_lang == "en"):
         return CortexKokoroTTS().synthesize(text)
    → if pref == "slovenian" or (pref == "match_input" and detected_lang == "sl"):
         return CortexAzureTTS.from_agent_config(agent).synthesize(text)
    → fallback: CortexKokoroTTS (English)

  detect_language(text: str) → str   # "en" or "sl"
    → simple heuristic: check for Slovenian-specific characters (č, š, ž)
      + common Slovenian function words (in, na, je, se, da, za, to)
    → returns "sl" if ≥3 signals, else "en"
    → no external API call needed for EN/SL binary detection
```

### Preference Commands (natural language → saved setting)

These are detected in `monologue_end/_10_knowledge_extraction.py` via the existing user_prefs extraction mechanism. Extended keyword map in PersonalityModel:

```python
# In cortex_personality_model.py _PREF_MAP extension:
"answer in slovenian": (TTS_PREF_KEY, "slovenian"),
"reply in slovenian": (TTS_PREF_KEY, "slovenian"),
"answer in english": (TTS_PREF_KEY, "english"),
"reply in english": (TTS_PREF_KEY, "english"),
"match my language": (TTS_PREF_KEY, "match_input"),
```

CORTEX also responds with: *"Got it — I'll respond in [language] going forward. Change anytime by saying 'answer in English' or 'answer in Slovenian'."*

### env additions
```
SONIOX_API_KEY=...
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=westeurope   # closest to Slovenia
```

### Tests: `tests/test_f2_voice_pipeline.py` (target: 22 tests)

- Soniox client: mock API, transcribe returns string
- Soniox client: health check returns bool
- Voice cleaner: removes English filler words correctly
- Voice cleaner: removes Slovenian filler words correctly
- Voice cleaner: handles false start removal
- Voice cleaner: handles self-correction ("Monday no Tuesday" → "Tuesday")
- Voice cleaner: preserves meaning (no paraphrasing)
- Voice cleaner: preserves Slovenian (no translation)
- Language detector: English text → "en"
- Language detector: Slovenian text with č/š/ž → "sl"
- Language detector: mixed signals → correct primary language
- TTS router: pref=english → Kokoro called
- TTS router: pref=slovenian → Azure called
- TTS router: pref=match_input + lang=sl → Azure called
- TTS router: pref=match_input + lang=en → Kokoro called
- TTS router: fallback on Kokoro if Azure unavailable
- Kokoro TTS: synthesize returns bytes
- Azure TTS: mock SDK, synthesize returns bytes
- Preference command detection: "answer in slovenian" → saved to PersonalityModel
- Preference command detection: "answer in english" → saved
- Preference command: persists across session load
- Full pipeline mock: voice bytes → transcript → clean → TTS bytes

---

## F-3: Image + Document

### Image Understanding Architecture

```
Telegram photo received
  ↓
cortex_vision_client.py
  Step 1: Gemini 2.5 Flash-Lite API
    → image bytes + task prompt
    → raw description/analysis (~$0.0003-0.001 per image)
  Step 2: DeepSeek V3.2 (structuring agent)
    → raw description → structured output for CORTEX
    → format: {summary, key_elements, text_in_image, actionable_items, requires_decision}
  ↓
Structured analysis injected as context for CORTEX
CORTEX responds to user's message + image context combined
```

**`python/helpers/cortex_vision_client.py`**

```
VISION_SYSTEM = """
Analyze this image thoroughly. Extract:
1. What is shown (scene, objects, people, context)
2. All text visible in the image (exact transcription)
3. Any data, numbers, charts, tables (exact values)
4. Any UI elements, buttons, forms (exact labels and state)
5. What action or decision this image seems to require
Be precise. Do not interpret or add information not visible.
"""

STRUCTURE_SYSTEM = """
You receive a raw image analysis. Structure it into:
{
  "summary": "one-sentence description",
  "key_elements": ["list", "of", "main", "items"],
  "text_in_image": "exact text transcribed",
  "data": "any numbers, tables, charts",
  "ui_elements": "any interface elements and their state",
  "actionable_items": ["what needs decision or action"],
  "requires_decision": true/false
}
Return only valid JSON.
"""

class CortexVisionClient:
  from_agent_config(agent)
  async analyze(image_bytes: bytes, context: str = "") -> dict
    → Step 1: Gemini 2.5 Flash-Lite via OpenRouter
    → Step 2: DeepSeek V3.2 structuring
    → returns structured dict
  async analyze_screenshot(image_bytes: bytes, task_context: str) -> dict
    → same but with task_context injected: "CORTEX was performing: {task_context}"
```

**Model call for vision (OpenRouter):**
```python
# Gemini 2.5 Flash-Lite via OpenRouter multimodal
model = "google/gemini-2.5-flash-lite"
messages = [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
    {"type": "text", "text": VISION_SYSTEM + "\n\n" + context}
]}]
```

### Document Parser Architecture

```
Telegram file received (PDF / .docx / .xlsx / .csv / .txt / image)
  ↓
cortex_document_parser.py
  → detect file type by extension + MIME
  → route to appropriate parser
  → returns: {title, content_chunks: list[str], metadata, file_type, page_count}
  ↓
Decision: size-based routing
  → small doc (< 8000 tokens): inject directly as context
  → large doc (≥ 8000 tokens): chunk → push to SurfSense → confirm to user
     ("Document ingested: '{title}'. Available for retrieval in future queries.")
```

**`python/helpers/cortex_document_parser.py`**

```
class CortexDocumentParser:
  parse(file_bytes: bytes, filename: str) -> ParsedDocument
    → routes by extension:
       .pdf        → _parse_pdf()     (PyMuPDF / fitz)
       .docx       → _parse_docx()    (python-docx)
       .xlsx/.xls  → _parse_excel()   (openpyxl)
       .csv        → _parse_csv()     (built-in csv)
       .txt/.md    → _parse_text()    (direct decode)
       .jpg/.png   → _parse_image()   (cortex_vision_client)
       .gdoc/.gsheet → returns guidance: "Use Composio Google integration"

  _parse_pdf(bytes) -> ParsedDocument
    → fitz.open() → extract text per page → chunk by page
    → extract embedded images if any (pass to vision pipeline)

  _parse_docx(bytes) -> ParsedDocument
    → python_docx.Document() → paragraphs + tables → concatenate

  _parse_excel(bytes) -> ParsedDocument
    → openpyxl.load_workbook() → per-sheet extraction
    → tables → markdown table format for readability

  _parse_csv(bytes) -> ParsedDocument
    → csv.reader() → markdown table format
    → if > 100 rows: summarize structure + first 20 rows

@dataclass
class ParsedDocument:
  title: str
  file_type: str
  content_chunks: list[str]
  metadata: dict  # page_count, sheet_names, word_count, etc.
  token_estimate: int
```

**Dependencies to add to requirements.txt:**
```
PyMuPDF          # PDF parsing
python-docx      # Word document parsing
openpyxl         # Excel parsing
kokoro-onnx      # Kokoro TTS
soundfile        # audio I/O for Kokoro
azure-cognitiveservices-speech  # Azure Neural TTS
python-telegram-bot>=21.0      # Telegram bot (async)
langdetect       # language detection (fallback if heuristic insufficient)
httpx            # already present for SurfSense client
```

### Browser Screenshot → Telegram

When CORTEX is using a web tool (Browserbase, future browser integration) and needs user input:

```python
# In telegram_ops tool:
operation: "send_photo"
  → capture screenshot bytes from browser session
  → caption: "I'm at this step: [description]. What should I do?"
  → send to user's Telegram
  → await reply (user replies with instruction)
  → CORTEX continues with instruction
```

This enables the phone-based business management vision: CORTEX does the work, sends a screenshot when stuck, user approves via phone, CORTEX continues.

### Tests: `tests/test_f3_vision_documents.py` (target: 20 tests)

- Vision client step 1: mock Gemini API, returns description
- Vision client step 2: mock DeepSeek, returns structured dict
- Vision client: full pipeline returns correct keys
- Vision client: screenshot mode includes task context
- Document parser: PDF → ParsedDocument (mock fitz)
- Document parser: DOCX → ParsedDocument (mock python-docx)
- Document parser: XLSX → ParsedDocument with markdown tables (mock openpyxl)
- Document parser: CSV → ParsedDocument markdown
- Document parser: TXT → ParsedDocument
- Document parser: unknown extension → informative error
- Document parser: Google Sheets → Composio guidance returned
- Size routing: small doc → returns content_chunks directly
- Size routing: large doc → SurfSense push triggered
- SurfSense push: correct space determined per active venture
- ParsedDocument: token_estimate accurate within 20%
- Image file → routed to vision client
- PDF with embedded images → vision pipeline called for images
- Parser: preserves document structure (headings, tables)
- Excel multi-sheet: each sheet as separate chunk
- CSV > 100 rows: structure summary returned, not full content

---

## F-4: Response Formatting + Comprehension Check

### Medium-Aware Formatter

**`python/helpers/cortex_response_formatter.py`**

Three output media with different rules:

**Telegram format** (`format_for_telegram(text)`):
- No markdown tables → convert to plain text with spacing
- No HTML → strip
- Bold: `**text**` → keep (Telegram renders this)
- Code blocks: keep (Telegram renders monospace)
- Bullet points: `•` emoji instead of `-` for visual clarity
- Max line length: 4096 chars (Telegram limit)
- Headers: `**SECTION NAME**` on its own line
- Numbers and currency: preserve exactly

**Voice format** (`format_for_voice(text)`):
- Strip all formatting symbols: no **, no #, no -, no |, no `
- Convert lists to natural speech: "First... Second... Third..."
- Convert tables to: "The options are: [name]: [value]. [name]: [value]."
- Numbers spoken naturally: "€840" → "840 euros"
- Max length: ~500 words (reasonable voice response)
- No URLs (not speakable)

**Web UI format** (`format_for_web(text)`):
- Standard markdown (current behavior)
- No change from current

### Comprehension Check Extension

**`python/extensions/monologue_start/_08_comprehension_check.py`**

Fires at monologue_start, before any other processing. Determines if a comprehension block should be generated for this request.

```python
TRIGGERS_COMPREHENSION = [
    "draft", "write", "create", "build", "send", "research",
    "analyze", "compare", "schedule", "approve", "plan", "design",
    "find", "contact", "invoice", "email", "call", "buy", "post"
]

SKIPS_COMPREHENSION = [
    "what", "how", "why", "when", "where", "explain",
    "tell me", "what is", "can you", "do you", "remember",
    # Conversational/direct requests → no comprehension block
]
```

Logic:
1. Check user message against TRIGGERS and SKIPS
2. If comprehension warranted: load `comprehension_mode` from PersonalityModel
3. Inject into CORTEX's working context: "Generate a comprehension block before acting. Mode: compact/detailed."
4. CORTEX generates the block as first output, then proceeds

**Compact format (default):**
```
✓ [Task]: {task description}
[Constraint]: {key constraints}
[Assuming]: {key assumptions — the most likely to be wrong}
[Action]: {what CORTEX will do} → {where it ends up, e.g. HITL queue}
```

**Detailed format (on "more" / preference):**
```
✓ Understanding:
  Task: {full task description}
  Venture: {active venture} | Language: {detected} | Register: {formal/casual}
  Constraints: {all constraints listed}

Assumptions I'm making:
  • {assumption 1}
  • {assumption 2}
  [Correct anything before I proceed]

My plan:
  1. {step} (~{time}, {cost estimate if research involved})
  2. {step}
  3. {step} → {end state}

What could go wrong:
  • {risk 1}
  • {risk 2}
```

### Comprehension Mode Preference System

**Extended `_PREF_MAP` in `cortex_personality_model.py`:**

```python
# TTS language preferences
"answer in slovenian":     ("tts_output_language", "slovenian"),
"reply in slovenian":      ("tts_output_language", "slovenian"),
"odgovori v slovenščini":  ("tts_output_language", "slovenian"),  # Slovenian command
"answer in english":       ("tts_output_language", "english"),
"reply in english":        ("tts_output_language", "english"),
"match my language":       ("tts_output_language", "match_input"),

# Comprehension mode preferences
"set default to long":     ("comprehension_mode", "detailed"),
"set default to short":    ("comprehension_mode", "compact"),
"detailed mode":           ("comprehension_mode", "detailed"),
"compact mode":            ("comprehension_mode", "compact"),
"full breakdown by default": ("comprehension_mode", "detailed"),
"short by default":        ("comprehension_mode", "compact"),
```

When preference detected: CORTEX acknowledges explicitly:
*"Saved. I'll use detailed comprehension checks going forward for this context. Change anytime."*

**Per-response override** (always available regardless of default):
- User replies "more" or "full breakdown" → CORTEX generates detailed version of the last comprehension block
- This is handled by detecting these signals in the next message and checking if the previous CORTEX output was a compact comprehension block

### Slovenian Language Rules

Added to `agents/cortex/prompts/agent.system.main.role.md` language section:

```
Slovenian register rules (when outputting in Slovenian):
- Use standard Slovenian (knjižna slovenščina) — not colloquial, not regional dialect
- Do NOT mix in Croatian, Serbian, or Bosnian words
- Do NOT use anglicisms when Slovenian equivalents exist
- Formal register for business communications (Vi form for external, ti for internal)
- Numbers and currency: "840 EUR" not "840$", commas as decimal separators in SL context
- Date format: day.month.year (Slovenian convention)
- Business documents: full legal register unless instructed otherwise
```

### Tests: `tests/test_f4_formatting.py` (target: 18 tests)

- Telegram formatter: markdown table → plain text
- Telegram formatter: HTML stripped
- Telegram formatter: bullets converted to •
- Telegram formatter: bold preserved
- Voice formatter: all symbols stripped
- Voice formatter: list → natural speech sequence
- Voice formatter: €840 → "840 euros"
- Voice formatter: max length respected
- Web formatter: markdown unchanged
- Comprehension check: trigger detection (action verbs → yes)
- Comprehension check: skip detection (questions → no)
- Compact format: 4-line output structure correct
- Compact format: assumptions line included
- Detailed format: all sections present
- Preference detection: "set default to long" → comprehension_mode = detailed
- Preference detection: "answer in slovenian" → tts_output_language = slovenian
- Preference detection: Slovenian command ("odgovori v slovenščini") → recognized
- Preference persistence: saved value survives agent restart

---

## Data Flows (End-to-End)

### Voice Message → Voice Response

```
Telegram: user sends voice note (.ogg)
  ↓ TelegramBotHandler.handle_voice()
  ↓ download audio bytes
  ↓ CortexSonioxClient.transcribe(audio_bytes) → raw text [Soniox API]
  ↓ cortex_voice_cleaner.clean_transcript(raw_text) → clean text [DeepSeek V3.2]
  ↓ TelegramBotHandler.handle_text(clean_text)  [as if typed]
  ↓ CORTEX reasoning loop
  ↓ Response text generated
  ↓ CortexResponseFormatter.format_for_voice(text) → voice-clean text
  ↓ CortexTTSRouter.route(text, detected_lang, agent) → audio bytes
       ├─ English → CortexKokoroTTS.synthesize()   [local]
       └─ Slovenian → CortexAzureTTS.synthesize()  [Azure sl-SI]
  ↓ TelegramBotHandler.send_voice(chat_id, audio_bytes)
```

### Image → Response

```
Telegram: user sends photo
  ↓ TelegramBotHandler.handle_photo()
  ↓ download image bytes
  ↓ CortexVisionClient.analyze(image_bytes) → structured_analysis [Gemini 2.5 Flash-Lite + DeepSeek]
  ↓ combine: user_text_message + structured_analysis → CORTEX input
  ↓ CORTEX reasoning loop
  ↓ Response text → CortexResponseFormatter.format_for_telegram()
  ↓ TelegramBotHandler.send_text()
  [If response includes image: TelegramBotHandler.send_photo()]
```

### Document → Ingested or Answered

```
Telegram: user sends file
  ↓ TelegramBotHandler.handle_document()
  ↓ download bytes, detect type
  ↓ CortexDocumentParser.parse(bytes, filename) → ParsedDocument
  ↓ if token_estimate < 8000:
       inject as context → CORTEX answers directly
     else:
       chunk → CortexSurfSenseClient.push_document() (active venture space)
       confirm: "Document ingested: '{title}'. Ask me anything about it."
```

### Morning Digest

```
Phase E TaskScheduler → morning_digest task fires at 07:00 local
  ↓ telegram_ops.morning_digest(chat_id)
  ↓ venture_ops.list_pending() → HITL items
  ↓ venture_ops.health_check(each_active_venture) → health summary
  ↓ CommitmentTracker.get_active() → due/overdue commitments
  ↓ CortexResponseFormatter.format_for_telegram(digest) → clean text
  ↓ TelegramBotHandler.send_text(chat_id, digest)
```

---

## Requirements.txt Additions

```
PyMuPDF>=1.24.0
python-docx>=1.1.0
openpyxl>=3.1.0
kokoro-onnx>=0.3.0
soundfile>=0.12.0
azure-cognitiveservices-speech>=1.38.0
python-telegram-bot>=21.0.0
langdetect>=1.0.9
```

---

## env Keys to Add

```
# Telegram
TELEGRAM_BOT_TOKEN=              # overridden by credential vault
TELEGRAM_CHAT_ID=                # set on first /start command
TELEGRAM_DIGEST_TIME=07:00       # morning digest time
TELEGRAM_WEBHOOK_URL=            # production Fly.io URL

# STT
SONIOX_API_KEY=

# TTS
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=westeurope

# Vision (uses OpenRouter — already configured)
# No new keys needed
```

---

## Deferred to Future Phases (in plan, not building now)

| Feature | Target Phase | Reason |
|---------|-------------|--------|
| Real-time voice call (Twilio) | Phase H | Requires streaming TTS + GPU for latency budget |
| Web UI voice | Phase H | Agent Zero UI replaced entirely in Phase H |
| Diagrams / Mermaid rendering | Phase H | React frontend handles natively; Telegram workaround = PNG via mermaid-cli |
| Comprehension check UI toggle | Phase H | React per-chat toggle component |
| Inline expand button | Phase H | Accordion component in React |

---

## Test Summary

| Test file | Target tests | Scope |
|-----------|-------------|-------|
| `test_f1_telegram_core.py` | 20 | Bot routing, HITL digest, command replies, credential vault |
| `test_f2_voice_pipeline.py` | 22 | Soniox, cleanup, language detect, TTS routing, Kokoro, Azure, preferences |
| `test_f3_vision_documents.py` | 20 | Vision two-step, document parser all types, size routing, SurfSense push |
| `test_f4_formatting.py` | 18 | Telegram/voice/web formatters, comprehension formats, preference detection |
| **Total new tests** | **80** | |
| **Holistic (D+E+Op-A+F)** | **~500** | All passing together |

---

## Phase F → Phase G Connection

What Phase F gives Phase G (self-optimization loop):

- **Voice interaction logs** → struggle patterns in spoken input (Phase G training signal)
- **Comprehension check feedback** (user corrects CORTEX's assumptions) → high-value training signal for Phase G
- **Document ingestion** → richer knowledge base for Phase G's hypothesis generation
- **Telegram as delivery channel** → Phase G improvement proposals delivered via Telegram digest
