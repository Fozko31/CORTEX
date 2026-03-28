# CORTEX Phase Tools — Research Stack, Tool Registry & Venture Packs

**Phases:** Tool-1 through Tool-7 + Umbrella-A through Umbrella-G
**Completed:** Before Phase C
**Tests:** Covered by `tests/test_b6_model_router.py` + holistic suite
**Technical depth:** [phase_tools_architecture.md](usr/knowledge/cortex_main/main/phase_tools_architecture.md)

---

## What the Tool Phases Built

The tool phases built the research infrastructure, external integrations, model routing, and the tool management layer that makes CORTEX's intelligence actionable. The discovery and venture creation work in later phases rests entirely on what was built here.

### Tool-1: Research Clients

Three search APIs, all async, all built as standalone clients with `from_agent_config()` factory methods:

**Tavily** (`cortex_tavily_client.py`) — real-time web search. Structured results with title, URL, content. Used for: current market data, pricing, recent events, local data, news, "what tools people use now." Cost: ~$0.01–0.04/query.

**Exa** (`cortex_exa_client.py`) — neural/semantic search. Finds conceptually similar content rather than keyword matches. Used for: expert frameworks, research papers, methodology, case studies, authoritative analysis. Supports recency filters. Cost: ~$0.01–0.02/query.

**Perplexity** (`cortex_perplexity_client.py`) — Tier 2 only. Multi-source synthesis with citations. Used as the depth layer: Tier 1 findings feed directly into Perplexity queries for comprehensive coverage. Hard cap: $0.50/run. Gate: if cost estimate >$0.10, surface to user before running. `PerplexityCapExceededError` raised if cap would be exceeded.

### Tool-2: Research Orchestrator

`cortex_research_orchestrator.py` — combines the three clients into the Tier 1/2 research system.

**Tier 1:** Tavily + Exa, multiple queries per tool, results deduplicated by URL. Claude Sonnet synthesizes. Cost: ~€0.02–0.05/run.

**Tier 2:** Tier 1 + Perplexity (Tier 1 findings passed as context for Perplexity queries). Query chaining: each tool's output informs the next tool's queries. Cost: ~€0.10–0.50/run, hard-capped.

**Deduplication:** Sources tracked by URL across all tools. Same URL from Tavily and Exa appears once.

### Tool-3: External Service Clients

**Firecrawl** (`cortex_firecrawl_client.py`) — web extraction for specific URLs. Three modes:
- `scrape`: single page, full content extraction
- `extract`: structured extraction with schema (pulls specific fields)
- `crawl`: multi-page site crawl with depth/limit controls

Used when a specific URL needs full structured content (not search — extraction).

**Composio** (`cortex_composio_client.py`) — SaaS action client. 300+ app integrations. Client built, apps not yet connected. Will power: email send, calendar, Slack, Notion, HubSpot, Linear, and more. Core infrastructure for Phase Op-A's autonomy-gated actions.

**GitHub MCP** — not a client file; configured as an MCP server. 26 tools available natively in the tool loop.

### Tool-4: Model Router

`cortex_model_router.py` — task-to-model routing for non-user-facing calls.

| Task type | Model | Cost per M tokens |
|-----------|-------|------------------|
| extraction | Gemini Flash Lite (fallback: Gemini Flash) | $0.25 input / $1.50 output |
| classification | DeepSeek V3.2 (fallback: Qwen) | $0.26 input / $0.38 output |
| summarization | DeepSeek V3.2 | $0.26 input / $0.38 output |
| digest | DeepSeek V3.2 | $0.26 input / $0.38 output |

**Claude Sonnet is never routed here.** Sonnet is reserved for user-facing synthesis — the final step of every research run and every direct response. All background/utility calls use cheaper models.

`call_routed_model(task_type, system, message, agent)` — single entry point. Returns string response. Tracks call count and cost estimate in a session log.

### Tool-5: `cortex_research_tool.py`

The agent-callable entry point for all research. One tool, two tiers.

Operations: `tier1_research`, `tier2_research`, `extract_page`, `health_check`

For each operation, the tool:
1. Reads context from the active venture (if any)
2. Constructs queries embedding that context
3. Runs the orchestrator
4. Returns structured results with sources, cost estimate, warnings

Tier 2 has a user confirmation gate when estimated cost >$0.10.

Prompt doc: `agents/cortex/prompts/agent.system.tool.cortex_research_tool.md`

### Tool-6: Tool Registry & Router

`cortex_tool_registry.py` — tracks tool state across the lifecycle.

States: `known` (documented, not installed), `installed` (available), `enabled` (active in current session), `disabled` (temporarily off), `error` (failed on last use).

`cortex_tool_router.py` — routes task families to tools.

Task families and primary tools:
- Research → `cortex_research_tool`
- Repo/dev → GitHub MCP
- SaaS actions → Composio
- Page extraction → Firecrawl
- Browser (JS/CAPTCHA) → Browserbase (disabled)
- Venture discovery → `venture_discover`
- Venture creation → `venture_create`
- Venture management → `venture_manage`

Live tool state is injected into the CORTEX profile's system prompt via `agents/cortex/extensions/system_prompt/_15_cortex_tool_state.py`.

### Tool-7: Venture Packs & Proactive Engine

**Venture Packs** (`cortex_venture_activation.py`) — 6 pre-defined venture type packs, each with core/tier1/tier2 tools and Composio apps.

Six packs: `saas`, `services`, `ecommerce`, `content`, `affiliate`, `marketplace`

When a venture is activated, its pack determines which tools are surfaced in the system prompt and which Composio apps are highlighted.

**Proactive Engine** (`cortex_proactive_engine.py`) — scans for actionable context and surfaces suggestions. Fires at appropriate moments to push relevant insights without being asked.

**Weekly Digest** (`cortex_weekly_digest.py`) — scheduled consolidation. Runs weekly (Phase E scheduler), pulls cross-session patterns, produces structured digest document pushed to SurfSense `cortex_weekly_digest` space.

---

## Umbrella Phases (A through G)

The Umbrella phases were cross-cutting integration passes — wiring existing components together and validating they work as a system:

| Umbrella | Focus |
|---------|-------|
| A | CORTEX identity → extension system wiring |
| B | Memory layers (FAISS + Graphiti + SurfSense) end-to-end |
| C | Research stack → tool router → agent tool loop integration |
| D | Tool registry → system prompt injection |
| E | Venture packs → activation → tool state |
| F | Proactive engine → monologue hooks |
| G | Full system test: identity + memory + research + tools all running together |

Umbrella phases left no new files — they produced test results and validated the integration surface. Their output is reflected in the combined test suite that passes holistically.

---

## Key Design Decisions

| Decision | What was decided | Why |
|----------|-----------------|-----|
| Tavily for current data, Exa for frameworks | Different query types, different strengths | Research quality: use the right tool for each sub-question |
| Perplexity gated at $0.10 | Budget control | Tier 2 adds significant cost; user should confirm high-spend runs |
| Claude Sonnet never routed for background tasks | Cost — DeepSeek/Gemini sufficient | ~10x cost saving for extraction, classification, summarization |
| Single `cortex_research_tool` entry point | Simple interface for agent | Agent doesn't need to know which underlying client to use |
| Venture packs instead of manual tool lists | Venture type → default tool selection | Moving company doesn't need ecommerce tools; SaaS doesn't need invoicing |
