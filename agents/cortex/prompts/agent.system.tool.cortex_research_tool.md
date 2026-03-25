### cortex_research_tool:
CORTEX primary research tool. Use for all live, current, market, strategic, and technical research.
**This replaces `search_engine` for all research tasks.**

**Tool args:**
- `topic`: the core research question or topic (one clear statement)
- `queries`: multiple search queries — always more than one; JSON array, newline list, or comma list
- `tier`: `Tier1` (default) or `Tier2` (high-stakes, comprehensive, irreversible decisions)

**What runs behind the scenes:**
- **Tier 1**: multi-query Tavily (current/market) + Exa (expert/technical) → deduped sources → structured context for Claude synthesis
- **Tier 2**: Tier 1 + Perplexity (multi-source depth, hard cap $0.50/run) → full context for Claude synthesis
- Claude Sonnet is always the final synthesis engine. This tool returns raw research context — you synthesize it.

**When to use:**
- Market conditions, competitors, pricing, technology landscape, regulations, current events
- Technical research — documentation, frameworks, methodologies, case studies
- Strategic research — market sizing, competitive landscape, industry analysis
- Any time training data alone is insufficient for a time-sensitive question

**Multiple queries are always better than one.**
Approach each topic from multiple angles: direct question + synonymous phrasing + context-embedded query.
Exa fills gaps Tavily misses. Perplexity (Tier 2 only) fills gaps both miss.

**Example usage:**
~~~json
{
    "thoughts": [
        "Need current competitive landscape for AI agent frameworks.",
        "Will run Tier 1: Tavily for market data, Exa for technical depth.",
        "Multiple queries to cover different angles."
    ],
    "headline": "Researching AI agent framework landscape — Tier 1",
    "tool_name": "cortex_research_tool",
    "tool_args": {
        "topic": "AI agent framework competitive landscape 2025",
        "queries": [
            "AI agent frameworks 2025 market comparison",
            "LangChain vs AutoGen vs CrewAI adoption pricing",
            "best AI coding agent tools developer sentiment 2025"
        ],
        "tier": "Tier1"
    }
}
~~~
