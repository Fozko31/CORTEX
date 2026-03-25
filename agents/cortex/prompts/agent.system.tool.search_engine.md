### search_engine:
General web search fallback. **For CORTEX research tasks, always prefer `cortex_research_tool`.**

`cortex_research_tool` orchestrates Tavily + Exa + Perplexity with tier-aware routing and returns structured research context. It is the correct tool for any question requiring current external data.

Use `search_engine` only when:
- A single quick lookup is needed and full research orchestration is not warranted
- `cortex_research_tool` is explicitly unavailable

**Example usage:**
~~~json
{
    "thoughts": ["Quick single-fact lookup not requiring full research pipeline."],
    "headline": "Quick search",
    "tool_name": "search_engine",
    "tool_args": {
        "query": "..."
    }
}
~~~
