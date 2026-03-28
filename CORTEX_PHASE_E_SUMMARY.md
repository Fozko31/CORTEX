# CORTEX Phase E — NEVER STOP + Scheduler Hardening + Memory Backup

**Completed:** 2026-03-27
**Tests:** 41 new tests — all passing. 322 total (Phase D + E) passing holistically.
**Technical depth:** [phase_e_architecture.md](usr/knowledge/cortex_main/main/phase_e_architecture.md)

---

## What Phase E Built

### 1. Fixed the scheduler (everything that was "running" wasn't)

Three background tasks — the weekly digest, proactive pulse, and discovery loop — were all registered at startup but silently doing nothing:

- **Discovery loop**: was writing to Unix system crontab. On Windows: silent no-op. Never fired.
- **Weekly digest**: called `scheduler.get_task()` which doesn't exist. Caught by try/except. Never registered.
- **Proactive pulse**: same bug. Never registered.

All three are now fixed and actually run via Agent Zero's built-in `TaskScheduler` (which was always the right tool — it just wasn't being used correctly).

Four tasks now registered on every CORTEX startup:

| Task | Schedule | Purpose |
|------|----------|---------|
| CORTEX Proactive Pulse | Every 30 min | Scans venture spaces for new relevant content |
| CORTEX Memory Backup | Sunday 02:00 UTC | Backs up all three memory layers |
| CORTEX Discovery Loop | Daily 03:00 UTC | Autonomous niche scanning (requires `CORTEX_DISCOVERY_AUTO=1`) |
| CORTEX Weekly Digest | Monday 03:00 UTC | Consolidates recent conversations, refreshes indices |

### 2. Memory backup — three-layer, weekly, automated

Every Sunday at 02:00 UTC, CORTEX backs up all three memory layers:

**L1 (FAISS — local files):** Copies `usr/memory/` to a dated backup directory. Keeps 8 weeks, auto-prunes older.

**L2 (Graphiti / Zep Cloud):** Exports the full knowledge graph as a compressed JSON file. Zep Cloud manages their own persistence — this is your disaster recovery copy and portability snapshot (if you ever leave Zep). Weekly full export, ~2-5MB compressed.

**L3 (SurfSense):** Incremental source content export. Only new documents since the last backup. Embeddings are not backed up — they're recomputable. Works across all spaces including CORTEX-pushed content (session summaries, knowledge extracts, discovery findings).

Run manually anytime: `python -m python.helpers.cortex_memory_backup`

### 3. Process watchdog (built, off by default)

`cortex_watchdog.py` monitors `run_ui.py` and restarts it on crash. Built for **commercial desktop users** who run CORTEX locally without a cloud layer. Default state: off.

For your own Fly.io deployment, `restart.policy = "always"` in `fly.toml` does the same thing at the infrastructure level — no code needed.

`scripts/install_windows_service.bat`: Optional NSSM setup for Windows boot auto-start. For commercial desktop packaging.

---

## The Core Flow

```
CORTEX startup
└── monologue_start/_15_register_schedulers.py
    ├── await register_weekly_digest_task()    → TaskScheduler (Mon 03:00)
    ├── await register_proactive_task()         → TaskScheduler (*/30 min)
    ├── await register_discovery_task()         → TaskScheduler (daily 03:00, gated)
    └── await register_backup_task()            → TaskScheduler (Sun 02:00)

job_loop.py (every 60s)
└── TaskScheduler.tick()
    └── get_due_tasks() → _run_task(task)
        └── Creates agent context → sends task.prompt → agent uses tools

Sunday 02:00 UTC (backup fires):
  backup_l1_faiss()    → usr/memory/backups/faiss/{date}/
  backup_l2_graphiti() → usr/memory/backups/graphiti/{date}/graphiti_export.json.gz
  backup_l3_surfsense()→ usr/memory/backups/surfsense/{date}/{space}.json.gz
```

---

## Key Design Decisions

| Decision | What was decided | Why |
|----------|-----------------|-----|
| No APScheduler | Agent Zero's TaskScheduler already works cross-platform | python-crontab is used as a parser only, not for writing to system crontab |
| Weekly full export for Graphiti | Not incremental | Dataset is small (~2-5MB); incremental complexity not worth it |
| Incremental for SurfSense | Not full | SurfSense can grow large; skip seen IDs by document ID |
| No embedding backup | Source content only | Embeddings fully recomputable; backing them up doubles size for zero benefit |
| Monthly full backup not built | Redundant | Weekly incremental from week 1 = complete history, ≤7 days loss |
| Watchdog default OFF | User uses Fly.io | Fly restart policy handles this; watchdog is for commercial desktop only |
| Fly.io confirmed as production target | Fly Machine + Volume for SurfSense, Supabase pgvector for L1 | PaaS with EU regions, built-in restart policy, commercial packaging DX |

---

## Files Created / Modified

| File | Status | Purpose |
|------|--------|---------|
| `python/helpers/cortex_discovery_scheduler.py` | Modified | register_discovery_task() rewritten — uses TaskScheduler, not system crontab |
| `python/helpers/cortex_weekly_digest.py` | Modified | register_weekly_digest_task() fixed — async, correct dedup, correct constructor |
| `python/helpers/cortex_proactive_engine.py` | Modified | register_proactive_task() fixed — same fixes |
| `python/helpers/cortex_memory_backup.py` | New | Three-layer memory backup, weekly scheduled |
| `cortex_watchdog.py` | New | Process watchdog (default OFF, commercial desktop) |
| `scripts/install_windows_service.bat` | New | NSSM setup script (optional, commercial desktop) |
| `python/extensions/monologue_start/_15_register_schedulers.py` | Modified | Now awaits all four registration calls |
| `tests/test_e1_scheduler.py` | New | 24 tests covering all four registration functions |
| `tests/test_e3_memory_backup.py` | New | 17 tests covering all backup logic |

---

## Phase E → Op-A Connection

Op-A (Venture Operations shared infrastructure) is next. What Phase E provides:

- **TaskScheduler integration pattern**: Op-A's per-venture recurring tasks (email handling, invoicing, reminders) register as `ScheduledTask` entries using the same pattern fixed here
- **Memory backup**: Op-A's action log and credential vault entries are in `usr/memory/` — automatically included in L1 backup
- **health_check in venture_ops.py**: Can query `TaskScheduler.get_tasks()` to list registered tasks, last-run times, any failures — Phase E gives this data

Op-A builds: `cortex_credential_vault.py`, `cortex_autonomy_policy.py`, `cortex_venture_task_queue.py`, `cortex_venture_action_log.py`, `venture_ops.py` tool, `venture_playbook_create.py` tool.
