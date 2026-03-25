# CLAUDE.md — CORTEX Session Context

**Last Updated:** 2026-03-25

## Project: CORTEX — AI Business Partner
- **Status:** Tool Stack complete + live. Phase C (Venture Machine) is next.
- **Foundation:** Agent Zero fork (github.com/Fozko31/CORTEX)
- **Local path:** `C:\Users\Admin\CORTEX`
- **Reference:** `C:\Users\Admin\CORTEX-Ruflo` (DO NOT MODIFY)
- **LLM:** Claude Sonnet 4.6 via OpenRouter (`anthropic/claude-sonnet-4.6`)
- **Target:** Autonomous business partner + venture factory

## Start a New Session
```
Read CORTEX_PROGRESS.md first — it has the full current state summary table at the top.
Then read this file. Then ask what to work on.
```

## Key Documents (read in order)
1. `CORTEX_PROGRESS.md` — Phase tracking + current status (ALWAYS READ FIRST)
2. `CORTEX_PLAN.md` — Master implementation plan (phases + architecture)
3. `CORTEX_DECISIONS.md` — All architecture decisions with rationale
4. `CLAUDE.md` — This file (session bootstrap)

## Runtime
- **Run:** `python run_ui.py` from `C:\Users\Admin\CORTEX`
- **URL:** `http://localhost:5000` (WEB_UI_PORT not set, defaults to 5000)
- **Profile:** select `cortex` in Settings → Agent in the UI
- **Node.js:** v22.18.0 (required for MCP servers via npx)

## Architecture — Key Facts

### Extension System
- ALL customization through Agent Zero's 24-hook extension system — zero core modifications
- CORTEX identity lives in `agents/cortex/prompts/` (auto-resolved before global `prompts/`)
- CORTEX-scoped extensions live in `agents/cortex/extensions/<hook>/`
- Per-profile extensions override global ones by filename prefix
- Extension naming: `_NN_description.py` — execution order is numeric, gaps of 5-10

### Tool Loading
- `agent.py:get_tool()` does exact filename lookup → `python/tools/<tool_name>.py`
- All tool prompt docs auto-included from `agents/cortex/prompts/agent.system.tool.*.md`
- `cortex_research_tool.py` is the primary research entry point (replaces RFC path)

### Memory Layers
| Layer | Technology | What it stores |
|-------|-----------|----------------|
| L1 | FAISS | Fast local entities/facts, per-session recall |
| L2 | Graphiti (Zep Cloud) | Temporal graph: entity→relationship→time |
| L3 | SurfSense | Cross-device consciousness, session summaries |

### Tool Routing (active)
| Task family | Primary tool | Status |
|-------------|-------------|--------|
| Research — live, market, strategic | `cortex_research_tool` | LIVE |
| Repo / dev / code | GitHub MCP (`github.*`) | LIVE — 26 tools |
| SaaS integrations | Composio | CLIENT BUILT — apps not connected yet |
| Page extraction | Firecrawl | LIVE |
| Browser (JS/CAPTCHA/login) | Browserbase | DISABLED — no API keys |

### Research Tiers
- **Tier 1:** Tavily + Exa, multi-query, deduped, structured → Claude synthesizes
- **Tier 2:** Tier 1 + Perplexity (Tier 1 findings as context), hard cap $0.50/run via OpenRouter
- Claude Sonnet 4.6 is always the final synthesis engine

## API Keys in `usr/.env`
| Key | Status |
|-----|--------|
| API_KEY_OPENROUTER | SET |
| TAVILY_API_KEY | SET |
| EXA_API_KEY | SET |
| FIRECRAWL_API_KEY | SET |
| COMPOSIO_API_KEY | SET |
| GITHUB_PERSONAL_ACCESS_TOKEN | SET (fine-grained PAT, read-only) |
| BROWSERBASE_API_KEY | NOT SET |
| BROWSERBASE_PROJECT_ID | NOT SET |

## MCP Servers
| Server | State |
|--------|-------|
| GitHub (`@modelcontextprotocol/server-github`) | ENABLED — PAT in env dict |
| Browserbase (`@browserbasehq/mcp`) | DISABLED — awaiting API keys |

## Files Created This Project (CORTEX-specific, not Agent Zero core)

### Helpers (`python/helpers/`)
- `cortex_knowledge_extractor.py` — entity/fact extraction via utility LLM
- `cortex_trust_engine.py` — per-domain trust scoring
- `cortex_personality_model.py` — 6-dimension personality model (challenge_level=4.0)
- `cortex_commitment_tracker.py` — promise/task tracking
- `cortex_model_router.py` — task→model routing (Gemini Flash Lite, DeepSeek V3.2, Claude)
- `cortex_ingestion_schema.py` — schema validation + content classification
- `cortex_surfsense_client.py` — SurfSense JWT auth + push/search
- `cortex_surfsense_router.py` — 4-tier retrieval, space routing
- `cortex_session_summarizer.py` — session→structured summary
- `cortex_graphiti_client.py` — Zep/Graphiti temporal graph wrapper
- `cortex_self_model.py` — capability registry + knowledge map
- `cortex_weekly_digest.py` — periodic consolidation + scheduler
- `cortex_tavily_client.py` — async Tavily search client
- `cortex_exa_client.py` — async Exa neural search client
- `cortex_perplexity_client.py` — Tier 2 Perplexity client (cost-capped)
- `cortex_firecrawl_client.py` — Firecrawl scrape/extract/crawl
- `cortex_research_orchestrator.py` — Tier 1/2 research orchestrator
- `cortex_composio_client.py` — Composio SaaS action client
- `cortex_tool_registry.py` — tool state management (known/installed/enabled)
- `cortex_tool_router.py` — task family routing + live tool state prompt
- `cortex_venture_activation.py` — venture pack activation (6 packs)
- `cortex_proactive_engine.py` — proactive context engine

### Tools (`python/tools/`)
- `cortex_research_tool.py` — agent-callable Tier1/2 research tool

### Extensions — Global (`python/extensions/`)
- `system_prompt/_05_cortex_identity.py` — dynamic context injection
- `system_prompt/_07_trust_level.py` — trust level injection
- `monologue_start/_05_self_model_load.py` — self-model + Tier 0 index load
- `monologue_end/_10_knowledge_extraction.py` — background entity/fact extraction
- `monologue_end/_15_graphiti_update.py` — forward entities to Graphiti
- `monologue_end/_60_struggle_detect.py` — detect hedging → flag knowledge gaps
- `message_loop_prompts_after/_15_temporal_memory.py` — FAISS recall injection
- `message_loop_prompts_after/_17_personality_model.py` — personality + commitments
- `message_loop_prompts_after/_20_surfsense_pull.py` — 4-tier consciousness pull
- `process_chain_end/_10_surfsense_push.py` — session end → SurfSense push

### Extensions — CORTEX Profile (`agents/cortex/extensions/`)
- `system_prompt/_15_cortex_tool_state.py` — live tool state in system prompt

### Prompts — CORTEX Profile (`agents/cortex/prompts/`)
- `agent.system.main.role.md` — COO identity + tool routing table (Step 6)
- `agent.system.main.communication.md` — thinking process
- `agent.system.tool.response.md` — response format
- `agent.system.tool.cortex_research_tool.md` — research tool documentation
- `agent.system.tool.search_engine.md` — demotes search_engine, prefers cortex_research_tool

### Knowledge (`usr/knowledge/cortex_main/main/`)
- `tools/tool_registry_core.md`
- `tools/tool_registry_optional.md`
- `tools/tool_selection_rules.md`
- `tools/tool_install_playbooks.md`
- `tools/tool_registry_venture_packs.md`
- `ventures/venture_pack_definitions.md`

## Known Non-Blocking Warnings
1. `Failed to pause job loop by development instance: localhost:55080` — job_loop.py dev ping, fires every 60s, harmless
2. `LLM consolidation analysis failed` — memory_consolidation.py background dedup, skips cycle, harmless
3. `litellm LoggingWorker pending task` — cosmetic async cleanup warning at shutdown
4. `RequestsDependencyWarning` — urllib3/chardet version mismatch, cosmetic only

## What's Next (Phase C: Venture Machine)
See `CORTEX_PLAN.md` Phase C section for full file list. Core work:
- `cortex_venture_dna.py` — VentureDNA Pydantic models
- `cortex_venture_lifecycle.py` — lifecycle engine
- `cortex_outcome_ledger.py` — decision + ROI tracking
- `venture_create.py` tool — conversational venture creation
- `venture_manage.py` tool — venture status + operations
