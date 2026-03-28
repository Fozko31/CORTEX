# CORTEX Phase Op-A — Venture Operations Shared Infrastructure

**Completed:** 2026-03-27
**Tests:** 92 new tests — all passing. 421 total (D + E + Op-A) passing holistically (4 live-connectivity tests excluded — require running services).
**Technical depth:** [phase_opa_architecture.md](usr/knowledge/cortex_main/main/phase_opa_architecture.md)

---

## What Phase Op-A Built

Op-A is the operational layer that turns CORTEX from a discovery-and-creation machine into one that actually *runs* ventures. Everything here is venture-type-agnostic — it doesn't matter if the venture is SaaS, services, or ecommerce. The same infrastructure serves all of them.

### 1. Credential Vault (Fernet encryption)

Every integration CORTEX uses on behalf of a venture needs credentials — API keys, passwords, tokens. These can't live in plaintext files or environment variables per-venture.

The credential vault encrypts everything with Fernet symmetric encryption. One encrypted blob per venture, stored at `usr/memory/cortex_main/vault/{slug}_credentials.enc`. The encryption key is auto-generated on first use, stored in `usr/.vault_key` (chmod 600), or overridden via `CORTEX_VAULT_KEY` env var.

**Critical design rule:** `list_keys()` returns credential names and expiry status only. The raw values are never shown — not in logs, not in system prompts, not in any output except direct tool retrieval for actual execution. The UI "import credentials" button will call `set_credential` — users never type raw values into the chat.

Credentials can have optional expiry dates. A 7-day warning window surfaces at next interaction.

### 2. Autonomy Policy — Extended to Per-Resource Level

This is the most architecturally significant component. The question it answers: **for every action CORTEX wants to take, is it allowed to just do it, show a draft first, or ask for approval?**

The design confirmed by user goes deeper than most systems: beyond per-venture and per-action-class granularity, it reaches **per-resource-instance** level.

Example that drove the design:
> "Same venture. Two email accounts. The main outreach account: CORTEX can send directly. The personal account: CORTEX always shows me a draft first."

That's now supported. A rule can be keyed by `(venture_slug, action_class, resource_id)` — where `resource_id` is an optional identifier (e.g. `"gmail_primary"`, `"gmail_personal"`).

Lookup hierarchy (most specific wins):
1. `(venture_slug, action_class, resource_id)` — resource-specific
2. `(venture_slug, action_class)` — venture + action class
3. `(venture_slug, *)` — venture-wide default
4. Built-in safe defaults — SEND_MESSAGE and SPEND_MONEY default to REQUIRE_APPROVAL

Action classes: READ, DRAFT, SEND_MESSAGE, SPEND_MONEY, DEPLOY, SCHEDULE, MODIFY_DATA
Autonomy levels: AUTO, DRAFT_FIRST, REQUIRE_APPROVAL

**Spend gate:** Each venture has a `spend_auto_threshold_eur` (default €0.00). Even if SPEND_MONEY is set to AUTO, if the cost exceeds the threshold, it blocks for approval.

**Immutability rule:** Rules are set by user only (`set_by='user'` always). CORTEX never adjusts these autonomously. Once set, the rule persists until explicitly changed.

### 3. Venture Task Queue + Action Log (shared SQLite)

Two tables, one file: `usr/memory/cortex_main/venture_ops.db`.

**Task queue** stores recurring tasks per venture — the operational heartbeat. A moving company venture might have: email triage (Mon-Fri 09:00), invoice review (weekly), monthly accountant delivery. Each task maps to a `ScheduledTask` in Agent Zero's TaskScheduler via the same pattern built in Phase E.

**Action log** is the immutable audit trail of everything CORTEX does on behalf of ventures. Every action — whether auto-executed or waiting for approval — is logged with its inputs, the autonomy decision, cost estimate, and outcome. This is non-negotiable for trust.

The HITL (Human-In-The-Loop) queue lives here: actions requiring approval are logged as `pending_approval`, surfaced at next interaction via `venture_ops list_pending`, and executed only after `approve(action_id)`.

### 4. venture_ops Tool

The agent-callable interface to everything above. 13 operations in one tool:

- `health_check` — venture operational status at a glance
- `set_autonomy` / `get_autonomy` — autonomy rule management
- `list_pending` / `approve` / `reject` — HITL queue
- `set_credential` / `list_credential_keys` / `delete_credential` — vault
- `list_tasks` / `add_task` / `disable_task` — recurring tasks
- `get_playbook` — retrieve published playbook

### 5. venture_playbook_create Tool

First-class tool, same level as `venture_create` and `venture_discover`. Produces the operational playbook that defines how a venture runs.

Nine-step interactive flow. What makes it work:

**Resume logic:** Start a playbook, get interrupted, pick it up later. `start()` detects an existing draft and tells you where you left off. You choose to resume or start fresh.

**Compliance section (step 8) is mandatory:** GDPR lawful basis, user rights procedures, legal entity, ToS/PP status, liability risks. CORTEX asks these questions explicitly. Can't publish without completing it (unless forced).

**Versioning:** Every `publish()` creates `playbook_v{N}.json`. Previous versions are preserved. The SurfSense title includes the version number. `venture_ops get_playbook` retrieves any version.

---

## The Core Flows

```
HITL action flow:
  CORTEX wants to send an email → checks autonomy policy
    → REQUIRE_APPROVAL → log_action(status='pending_approval')
    → next user interaction: "1 action pending approval for [venture]"
    → venture_ops list_pending → approve(action_id) → execute → log outcome

Playbook creation flow:
  venture_playbook_create start(venture_slug="moving_co")
    → checks for draft → none found → creates draft (venture_confirmed pre-marked)
    → returns next_step='business_model' + step questions
  [user answers] → save_step(step='business_model', content={...})
    → returns next_step='customer_profile' + step questions
  ... 7 more steps ...
  → publish() → playbook_v1.json + SurfSense push

Autonomy rule (resource-level):
  venture_ops set_autonomy(
    venture_slug='moving_co',
    action_class='SEND_MESSAGE',
    level='AUTO',
    resource_id='gmail_bulk_outreach',
    reason='Pre-approved outreach sequences, no personal content'
  )
  venture_ops set_autonomy(
    venture_slug='moving_co',
    action_class='SEND_MESSAGE',
    level='DRAFT_FIRST',
    resource_id='gmail_personal',
    reason='Personal account, always review before sending'
  )
```

---

## Key Design Decisions

| Decision | What was decided | Why |
|----------|-----------------|-----|
| Per-resource autonomy granularity | Same venture can have different rules per resource_id | Two email accounts, different trust levels — user's explicit requirement |
| CORTEX never sets autonomy rules | `set_by='user'` always | Trust and control — autonomy policy is a human decision |
| Spend threshold default €0.00 | Any spend requires approval by default | No surprise charges |
| Shared SQLite for task_queue + action_log | Single `venture_ops.db` | Atomic queries across tables (e.g. "all actions from active tasks") |
| `venture_confirmed` pre-marked in playbook | First step implicit | Venture must exist before playbook. Prevents speculative drafts. |
| Compliance step non-skippable | Required before `publish()` | GDPR and legal clarity are not optional |
| Integer playbook versioning | v1, v2, v3... | Simple, human-readable, SurfSense title includes version |
| `list_keys()` never exposes values | Name + expiry status only | Credential values must not appear in any log, prompt, or output |

---

## Files Created

| File | Purpose |
|------|---------|
| `python/helpers/cortex_credential_vault.py` | Fernet-encrypted credential store |
| `python/helpers/cortex_autonomy_policy.py` | Per-resource autonomy policy engine |
| `python/helpers/cortex_venture_task_queue.py` | Recurring task management + scheduler integration |
| `python/helpers/cortex_venture_action_log.py` | Immutable action audit trail + HITL queue |
| `python/tools/venture_ops.py` | Agent-callable operations tool |
| `python/tools/venture_playbook_create.py` | Interactive playbook creation tool |
| `agents/cortex/prompts/agent.system.tool.venture_ops.md` | venture_ops prompt doc |
| `agents/cortex/prompts/agent.system.tool.venture_playbook_create.md` | venture_playbook_create prompt doc |
| `tests/test_opa1_credential_vault.py` | 20 tests |
| `tests/test_opa2_autonomy_policy.py` | 27 tests |
| `tests/test_opa3_task_queue_action_log.py` | 24 tests |
| `tests/test_opa4_playbook_create.py` | 21 tests |

---

## Phase Op-A → Phase F Connection

What Op-A gives Phase F (Telegram + Voice):

- **`venture_ops list_pending`** → surface HITL queue in Telegram daily digest
- **`venture_ops approve/reject`** → user approves actions by replying to Telegram message
- **`venture_ops health_check`** → morning Telegram brief for each active venture
- **Credential vault** → Telegram bot token stored as credential
- **Playbook actions** → voice-driven step completion (user speaks answers, Whisper transcribes, `save_step` stores)

Phase F builds: Telegram bot integration, Groq Whisper STT, Kokoro TTS (local, private by default).
