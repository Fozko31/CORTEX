# CORTEX Phase 0 — Project Setup & Foundation

**Completed:** Pre-build (2025/2026)
**Tests:** No automated tests (environment/config phase)
**Technical depth:** [phase_0_architecture.md](usr/knowledge/cortex_main/main/phase_0_architecture.md)

---

## What Phase 0 Built

Phase 0 is the foundation everything else stands on. It is not a feature phase — it is the decision phase that answers: what is CORTEX, what does it run on, how does it connect to the outside world, and what are the rules that govern all subsequent development?

Without Phase 0, no other phase has a safe surface to build on. This phase turns the Agent Zero open-source framework into a CORTEX-specific runtime without touching core Agent Zero files — a constraint that was established here and governs every subsequent phase.

### 1. Agent Zero Fork + CORTEX Profile

CORTEX runs as a profile on top of Agent Zero. Agent Zero provides: the web UI, the tool execution loop, the extension hook system (24 hooks), the memory toolchain (FAISS built-in), MCP server support, and the scheduler.

**The critical architecture decision (D-001):** Zero modifications to Agent Zero core files. All CORTEX customization lives in:
- `agents/cortex/` — the CORTEX profile (prompts + profile-scoped extensions)
- `python/helpers/cortex_*.py` — CORTEX helper modules
- `python/tools/*.py` — agent-callable tools
- `python/extensions/` — global extensions (hook-based injection)

This is not just cleanliness — it preserves upstream mergeability. Agent Zero continues to evolve; CORTEX must be able to pull upstream improvements without rewriting core integrations.

### 2. Directory Structure

```
agents/cortex/
  prompts/          ← CORTEX-specific system prompt files (auto-loaded before global prompts/)
  extensions/       ← CORTEX-scoped extensions (per-hook, per-profile)
python/helpers/     ← cortex_*.py helper modules
python/tools/       ← agent-callable tools
python/extensions/  ← global extensions (all profiles)
usr/
  .env              ← all API keys
  memory/cortex_main/  ← all CORTEX persistent data
  knowledge/cortex_main/main/  ← CORTEX knowledge base (self-reads this)
```

### 3. API Key Setup

All API keys in `usr/.env`. Keys configured at Phase 0:

| Key | Purpose | Status |
|-----|---------|--------|
| `API_KEY_OPENROUTER` | LLM routing (Claude Sonnet 4.6 via OpenRouter) | SET |
| `TAVILY_API_KEY` | Tier 1 web search | SET |
| `EXA_API_KEY` | Tier 1 neural search | SET |
| `FIRECRAWL_API_KEY` | Web extraction | SET |
| `COMPOSIO_API_KEY` | SaaS automation | SET |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub MCP (fine-grained PAT, read-only) | SET |
| `ZEP_API_KEY` | Graphiti / Zep Cloud (L2 temporal memory) | SET |
| `SURFSENSE_*` | SurfSense (L3 consciousness) | SET |

### 4. MCP Servers

Agent Zero supports MCP (Model Context Protocol) servers for extending tool access. Phase 0 configured:

- **GitHub MCP** (`@modelcontextprotocol/server-github`) — ENABLED. 26 tools: repo reading, search, issues, PRs, code search. Read-only PAT.
- **Browserbase MCP** — DISABLED (no API keys yet). Cloud browser for JS-heavy sites.

MCP servers require Node.js v22+ and run via `npx`. Agent Zero handles the MCP protocol; CORTEX uses MCP tools natively in the tool loop.

### 5. Runtime

- **Start:** `python run_ui.py` from `C:\Users\Admin\CORTEX`
- **URL:** `http://localhost:5000`
- **LLM:** Claude Sonnet 4.6 via OpenRouter (`anthropic/claude-sonnet-4.6`)
- **Profile selection:** Settings → Agent → select `cortex` in the UI
- **Node.js:** v22.18.0 required for MCP servers

### 6. Decision Framework

`CORTEX_DECISIONS.md` established as the canonical record of all architecture decisions. Format: `D-NNN — [Decision title]` with rationale, alternatives considered, constraints, and validity conditions.

This is not optional process overhead — decisions without recorded rationale get re-litigated in future sessions, wasting time re-deriving conclusions that were already reached.

---

## Key Design Decisions from Phase 0

| Decision | What was decided | Why |
|----------|-----------------|-----|
| Agent Zero as base | Fork Agent Zero, not build from scratch | 24-hook extension system, FAISS memory, MCP support, UI — months of work included for free |
| Zero core modifications | All customization through extension hooks + profile | Upstream mergeability — D-001 |
| OpenRouter as LLM gateway | All LLM calls via OpenRouter | Multi-model routing, cost tracking, single API key |
| Claude Sonnet 4.6 as primary | Synthesis, user-facing reasoning | Best available reasoning model at build time |
| `usr/.env` for all keys | One file, gitignored | Simple, Agent Zero convention |

---

## What Phase 0 Does NOT Include

Phase 0 is deliberately minimal. It does not include:
- Any CORTEX-specific reasoning or personality (Phase A1)
- Any memory integration beyond FAISS (Phase A2, B)
- Any research tools (Tool phases)
- Any venture logic (Phase C onward)

Phase 0 just makes the environment ready for everything else to be built cleanly.
