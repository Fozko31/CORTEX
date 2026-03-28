# CORTEX Tool Architecture — Agent-Mode Implementation Plan

## Status: APPROVED — Ready to build

## Approved decisions (do not re-discuss)
- RFC/local runtime: replaced entirely for research and tool routing
- Composio: first-choice for SaaS app integrations
- Tavily: direct API (not MCP)
- Exa: direct API (not MCP) — user explicit preference
- Perplexity: Tier 2 only, via OpenRouter, hard cap $0.25 soft / $0.50 hard per research run
- GitHub: official hosted MCP at https://api.githubcopilot.com/mcp/ — read-only first
- Firecrawl: primary web scraping/extraction — MCP or direct API
- Browserbase: cloud browser automation (CAPTCHA-resistant, cloud-native, Fly.io-ready)
- Claude Sonnet 4.6: always the final synthesis engine
- Tool registry: stored in SurfSense in standardized metadata format
- Venture packs: global install, scoped activation

---

## Phase 1 — Core direct API research clients

### Milestone 1.1 — Tavily direct API
**Files to create:**
- `python/helpers/cortex_tavily_client.py`

**Implementation:**
```python
# TavilyClient wrapping tavily-python SDK
# - async search(query, context=None, max_results=5) -> list[dict]
# - multi_search(queries: list[str], context=None) -> list[list[dict]]
# - context parameter prepends venture/user context to every query
# - returns: [{title, url, content, score, published_date}]
# - error handling with timeout (default 10s)
# - uses TAVILY_API_KEY from environment
```

**Environment variable required:**
- `TAVILY_API_KEY` in `usr/.env`

**Acceptance criteria:**
- `await TavilyClient.search("moving company pricing Maribor 2026")` returns 5+ results without error
- Context injection confirmed in query
- Timeout handled gracefully

---

### Milestone 1.2 — Exa direct API
**Files to create:**
- `python/helpers/cortex_exa_client.py`

**Implementation:**
```python
# ExaClient wrapping exa-py SDK
# - async search(query, context=None, type="neural", num_results=5) -> list[dict]
# - async find_similar(url, context=None) -> list[dict]
# - type options: "neural" (semantic), "keyword" (exact)
# - returns: [{title, url, text, highlights, published_date, author}]
# - uses EXA_API_KEY from environment
```

**Environment variable required:**
- `EXA_API_KEY` in `usr/.env`

**Acceptance criteria:**
- `await ExaClient.search("value-based pricing methodology service businesses")` returns quality results
- Neural search confirmed working

---

### Milestone 1.3 — Perplexity via OpenRouter (Tier 2 only)
**Files to create:**
- `python/helpers/cortex_perplexity_client.py`

**Implementation:**
```python
# PerplexityClient using OpenRouter with perplexity/sonar-pro model
# - async search(query, context=None, search_context_size="low") -> dict
# - tracks estimated cost per call
# - enforces hard cap: PERPLEXITY_HARD_CAP_USD (default 0.50) per research session
# - fails closed (raises CostCapExceeded) if cap would be exceeded
# - uses OPENROUTER_API_KEY (already in environment)
# - model: "perplexity/sonar-pro" via OpenRouter
# - returns: {content, citations, estimated_cost}
```

**Settings to add in `agents/cortex/settings.json`:**
```json
"cortex_perplexity_enabled": false,
"cortex_perplexity_model": "perplexity/sonar-pro",
"cortex_perplexity_hard_cap_usd": 0.50,
"cortex_perplexity_soft_cap_usd": 0.25
```

**Acceptance criteria:**
- Disabled by default (only fires in Tier 2)
- Cost tracking confirmed
- Hard cap triggers CostCapExceeded before exceeding $0.50

---

### Milestone 1.4 — Firecrawl web scraper
**Files to create:**
- `python/helpers/cortex_firecrawl_client.py`

**Implementation:**
```python
# FirecrawlClient using firecrawl-py SDK
# - async scrape(url, context=None) -> dict (full page content, clean markdown)
# - async extract(urls: list[str], schema: dict) -> dict (structured extraction)
# - async crawl(url, max_depth=2, limit=10) -> list[dict]
# - returns LLM-ready content
# - uses FIRECRAWL_API_KEY from environment
```

**Environment variable required:**
- `FIRECRAWL_API_KEY` in `usr/.env`

**Acceptance criteria:**
- `await FirecrawlClient.scrape("https://example.com")` returns clean markdown
- Structured extraction from a page works

---

## Phase 2 — Research orchestrator (the core of the tier system)

### Milestone 2.1 — Research orchestrator
**Files to create:**
- `python/helpers/cortex_research_orchestrator.py`

**Implementation:**
```python
# CortexResearchOrchestrator
# - async run_tier1(query, context, venture_context) -> ResearchResult
#   Steps: load memory → multi-query Tavily and/or Exa → Claude synthesis
#   Returns: {findings, gaps, confidence, sources, cost}
#
# - async run_tier2(query, context, venture_context, tier1_result=None) -> ResearchResult
#   Steps: revisit gaps → targeted Exa for Tavily gaps → optional Perplexity → Claude synthesis
#   If tier1_result provided: builds on it (escalation path)
#   If not: runs Tier 1 first, then extends
#   Returns: {findings, gaps, confidence, sources, cost, ranked_options}
#
# - _plan_queries(query, context) -> {tavily_queries: list, exa_queries: list}
#   Determines which tools handle which sub-questions
#   No hard rules — routes by query composition
#
# - _synthesize(context, tavily_results, exa_results, perplexity_result=None) -> str
#   Calls Claude Sonnet with all research inputs
#   Returns strategic insight, not search dump
#   Includes confidence decomposition
#
# Cost tracking: accumulates per-research, enforces Perplexity cap
```

**Acceptance criteria:**
- Tier 1 run on "moving company pricing Maribor 2026" returns meaningful result
- Tier 2 escalation (using Tier 1 findings) produces richer result than standalone Tier 1
- Perplexity NOT called during Tier 1
- Claude synthesis present in both tiers

---

## Phase 3 — GitHub MCP integration

### Milestone 3.1 — GitHub hosted MCP
**What to configure:**

In Agent Zero's MCP config (location depends on Agent Zero's config structure — check `agents/cortex/settings.json` or the Agent Zero MCP config path), add:

```json
{
  "github": {
    "type": "http",
    "url": "https://api.githubcopilot.com/mcp/",
    "headers": {
      "X-MCP-Readonly": "true"
    }
  }
}
```

Start with read-only mode.
Enable dynamic toolsets.

**Environment variable required:**
- `GITHUB_PERSONAL_ACCESS_TOKEN` in `usr/.env` (or OAuth handled separately)

**Acceptance criteria:**
- CORTEX can read a GitHub repository via MCP tool
- Read-only confirmed (no write capability exposed)

---

## Phase 4 — Composio integration

### Milestone 4.1 — Composio session model
**Files to create:**
- `python/helpers/cortex_composio_client.py`

**Implementation:**
```python
# CortexComposioClient
# - create_session(user_id, toolkits=None) -> ComposioSession
#   Creates a scoped session with selected toolkits
#   If toolkits=None: uses default scoped set (not all 300+)
# - discover_tools(session, query) -> list[dict]
#   Uses Composio meta-tool to find relevant tools
# - execute(session, tool_name, params) -> dict
# - get_mcp_url(session) -> str (for MCP-compatible routing)
# - uses COMPOSIO_API_KEY from environment (already in usr/.env)
```

**Default toolkit scopes:**
- `["gmail", "googlecalendar"]` for venture context
- Expand per venture pack later

**Acceptance criteria:**
- Session created with Gmail toolkit
- Tool discovery returns relevant Gmail tools
- Large response offloading to workbench confirmed

---

## Phase 5 — Browserbase MCP (browser automation)

### Milestone 5.1 — Browserbase cloud browser
**What to configure:**

Add Browserbase MCP to Agent Zero MCP config:
```json
{
  "browserbase": {
    "type": "http", 
    "url": "https://api.browserbase.com/mcp"
  }
}
```

OR use the npm package approach:
```json
{
  "browserbase": {
    "command": "npx",
    "args": ["-y", "@browserbasehq/mcp-browserbase"],
    "env": {
      "BROWSERBASE_API_KEY": "your_key",
      "BROWSERBASE_PROJECT_ID": "your_project_id"
    }
  }
}
```

**Environment variables required:**
- `BROWSERBASE_API_KEY` in `usr/.env`
- `BROWSERBASE_PROJECT_ID` in `usr/.env`

**Acceptance criteria:**
- CORTEX can navigate to a page and extract content
- Works from cloud (no localhost dependency)

---

## Phase 6 — Tool Capability Registry in SurfSense

### Milestone 6.1 — Define registry schema
**Files to create:**
- `python/helpers/cortex_tool_registry.py`

**Schema for each tool entry:**
```python
@dataclass
class ToolRegistryEntry:
    name: str
    category: str  # research, app_integration, browser, dev, productivity
    provider_type: str  # composio, mcp, direct_api, native
    short_description: str
    best_for: list[str]
    not_for: list[str]
    venture_tags: list[str]  # moving_company, saas, content, all
    install_source: str  # URL or package name
    auth_type: str  # api_key, oauth, none
    installed_status: str  # installed, available, known
    enabled_by_default: bool
    approval_required: bool
    write_capable: bool
    cost_profile: str  # free, low, medium, high
    priority: int  # 1=core, 2=optional, 3=venture_specific
    notes: str
```

### Milestone 6.2 — Seed core registry
**Files to create:**
- `knowledge/cortex/tools/tool_registry_core.md`
- `knowledge/cortex/tools/tool_registry_optional.md`
- `knowledge/cortex/tools/tool_registry_venture_packs.md`
- `knowledge/cortex/tools/tool_selection_rules.md`
- `knowledge/cortex/tools/tool_install_playbooks.md`

**The core registry must include entries for:**
Tavily, Exa, Perplexity, GitHub MCP, Composio, Firecrawl, Browserbase, SurfSense, Zep, Claude Sonnet

**Each entry must use the exact schema fields above.**

**Acceptance criteria:**
- CORTEX can query: "what research tools do I have?"
- CORTEX can query: "what tools are available for moving company venture?"
- CORTEX can propose enabling a tool and ask user for approval

---

## Phase 7 — Venture pack activation model

### Milestone 7.1 — Venture pack definitions
**Files to create:**
- `knowledge/cortex/ventures/venture_pack_definitions.md`

**Define packs:**
```
moving_company_pack:
  tools: [tavily, firecrawl, gmail_composio, calendar_composio, browserbase]
  description: Local service business pack

saas_dev_pack:
  tools: [github_mcp, tavily, exa, firecrawl, linear_composio, slack_composio]
  description: Software/dev venture pack

content_media_pack:
  tools: [tavily, exa, browserbase, firecrawl]
  description: Content and media venture pack

core_always_active:
  tools: [tavily, exa, surfsense, zep, claude_sonnet, composio]
  description: Always-on core regardless of venture
```

### Milestone 7.2 — Activation logic
**Files to modify:**
- Relevant extension or helper that loads tools for a session

**Logic:**
```python
def get_active_tools(venture_type: str) -> list[str]:
    core = get_core_tools()  # always active
    pack = get_venture_pack(venture_type)  # venture-specific
    return deduplicated_merge(core, pack)
```

---

## Phase 8 — Wire into reasoning protocol

### Milestone 8.1 — Replace RFC search_engine with orchestrator
**Files to modify:**
- `python/extensions/message_loop_prompts_after/_20_surfsense_pull.py` — already uses smart routing
- Create new tool that exposes `cortex_research_orchestrator` to CORTEX as a callable tool

**New tool file:**
- `python/tools/cortex_research_tool.py`

```python
# Exposes CortexResearchOrchestrator to the agent
# - research_tier1(query) -> result
# - research_tier2(query, tier1_result=None) -> result
# This replaces the RFC-dependent search_engine for strategic research
```

---

## Environment variables summary

All must be in `usr/.env`:

```
TAVILY_API_KEY=tvly-...
EXA_API_KEY=...
FIRECRAWL_API_KEY=fc-...
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
BROWSERBASE_API_KEY=...
BROWSERBASE_PROJECT_ID=...
COMPOSIO_API_KEY=...  # already set
OPENROUTER_API_KEY=...  # already set (used for Perplexity)
```

---

## Install dependencies

Add to `requirements.txt`:
```
tavily-python>=0.5.0
exa-py>=1.0.0
firecrawl-py>=1.0.0
composio-core>=0.7.0
```

---

## Test procedure per phase

### Phase 1 test
Start CORTEX and ask: "What are current moving company hourly rates in Maribor, Slovenia?"
- Expect: Tavily fires (no RFC/localhost:55080 error)
- Expect: Exa fires for expert frameworks
- Expect: Results returned without connection errors

### Phase 2 test
Ask: "What should SSMB's pricing strategy be for 2026?"
- Expect: Tier 1 runs (Tavily + Exa)
- Expect: Escalation option shown to user
- If escalated: Tier 2 extends with new targeted queries
- Perplexity: only if explicitly triggered in Tier 2

### Phase 3 test
Ask: "What is in the CORTEX GitHub repository?"
- Expect: GitHub MCP reads the repo
- Expect: No write actions performed (read-only mode)

### Phase 4 test
Ask: "Check my Gmail for messages about SSMB"
- Expect: Composio session created with Gmail toolkit
- Expect: Gmail tools discovered and executed

---

## What is explicitly deferred
- Perplexity enabling in production (enable after cap testing)
- Browserbase CAPTCHA capability (evaluation in Phase 5)
- Composio write capabilities (later with autonomy tiers)
- GitHub write capabilities (later with permission model)
- Full venture pack automation (Phase 7)
- Autonomy tiers (long-term roadmap)
- UI for tool management (deferred until meta-layers proven)

---

## Notes for agent executing this plan
1. Do not modify the existing RFC path — just stop using it for research routing
2. Preserve all existing Phase B functionality (SurfSense push/pull, self-model, proactive engine)
3. Do not remove `search_engine` tool — add the new orchestrator tool alongside it
4. Follow existing code style from `cortex_surfsense_client.py` and similar helpers
5. All new files go in `python/helpers/` for clients and `python/tools/` for agent-callable tools
6. Knowledge files go under `knowledge/cortex/tools/`
7. Always use async patterns consistent with existing CORTEX helpers
8. Add CORTEX context injection to every external search call
