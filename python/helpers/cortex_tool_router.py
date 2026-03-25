import os
from typing import Optional


class TaskFamily:
    RESEARCH = "research"
    REPO_DEV = "repo_dev"
    SAAS_ACTION = "saas_action"
    EXTRACTION = "extraction"
    BROWSER = "browser"


_ROUTING_TABLE = [
    (TaskFamily.RESEARCH,    "cortex_research_tool",      "Live/market/strategic/technical research — current external data"),
    (TaskFamily.REPO_DEV,    "GitHub MCP (github.*)",      "Repos, code, issues, PRs, releases — read-only first"),
    (TaskFamily.SAAS_ACTION, "Composio",                   "Gmail, Slack, Notion, HubSpot, Linear, Jira, Airtable, 300+ apps"),
    (TaskFamily.EXTRACTION,  "Firecrawl",                  "Full structured content from a specific URL"),
    (TaskFamily.BROWSER,     "Browserbase (fallback)",     "JS-heavy, CAPTCHA, login-gated, blocked or interactive pages"),
]

_TOOL_ENV_KEYS = {
    "Tavily":       "TAVILY_API_KEY",
    "Exa":          "EXA_API_KEY",
    "Perplexity":   "API_KEY_OPENROUTER",
    "Firecrawl":    "FIRECRAWL_API_KEY",
    "Composio":     "COMPOSIO_API_KEY",
    "GitHub MCP":   "GITHUB_PERSONAL_ACCESS_TOKEN",
    "Browserbase":  "BROWSERBASE_API_KEY",
}

_TOOL_ROLES = {
    "Tavily":       "research/Tier1 — current events, market data, news",
    "Exa":          "research/Tier1 — expert content, docs, papers, code",
    "Perplexity":   "research/Tier2-only — multi-source depth (hard cap $0.50/run)",
    "Firecrawl":    "extraction — full page markdown from target URL",
    "Composio":     "SaaS actions — check first for any supported app",
    "GitHub MCP":   "repo/dev — read repos, issues, PRs, code search",
    "Browserbase":  "browser-fallback — JS/CAPTCHA/login/blocked pages",
}

_ALWAYS_AVAILABLE = {
    "SurfSense": "memory — long-term knowledge, research storage, venture context",
    "Graphiti":  "memory — temporal knowledge graph, entity relationships",
}


def get_tool_states() -> dict:
    states = {}
    for tool, env_key in _TOOL_ENV_KEYS.items():
        states[tool] = "enabled" if os.getenv(env_key, "") else "not_configured"
    return states


def build_tool_state_prompt(agent=None) -> str:
    states = get_tool_states()

    enabled_lines = []
    missing_lines = []

    for tool, state in states.items():
        role = _TOOL_ROLES.get(tool, "")
        if state == "enabled":
            enabled_lines.append(f"  - {tool} [{role}]")
        else:
            missing_lines.append(f"  - {tool} [{role}] — key not set")

    for tool, role in _ALWAYS_AVAILABLE.items():
        enabled_lines.append(f"  - {tool} [{role}]")

    lines = ["## CORTEX Tool State\n"]

    lines.append("**Enabled:**")
    lines.extend(enabled_lines if enabled_lines else ["  - (none)"])

    if missing_lines:
        lines.append("\n**Not configured** (see tool_install_playbooks.md):")
        lines.extend(missing_lines)

    lines.append("\n**Tool routing (task family → tool):**")
    for family, tool, desc in _ROUTING_TABLE:
        lines.append(f"  - {family} → {tool}: {desc}")

    lines.append("\nNote: RFC/localhost tools unavailable. All execution is cloud-native.")

    return "\n".join(lines)


def routing_guide_text() -> str:
    lines = []
    for family, tool, desc in _ROUTING_TABLE:
        lines.append(f"  {family}: {tool} — {desc}")
    return "\n".join(lines)
