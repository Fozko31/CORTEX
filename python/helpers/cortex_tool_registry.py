import os
from dataclasses import dataclass, field
from typing import Optional


class ToolState:
    KNOWN = "known"
    INSTALLED = "installed"
    ENABLED = "enabled"


class ToolIntegration:
    DIRECT_API = "direct_api"
    MCP = "mcp"
    COMPOSIO = "composio"


@dataclass
class ToolEntry:
    name: str
    display_name: str
    category: str
    integration: str
    description: str
    state: str = ToolState.KNOWN
    tiers: list = field(default_factory=list)
    ventures: list = field(default_factory=list)
    env_key: str = ""
    mcp_server_name: str = ""
    composio_app_key: str = ""

    def is_enabled(self) -> bool:
        return self.state == ToolState.ENABLED

    def is_available(self) -> bool:
        return self.state in (ToolState.INSTALLED, ToolState.ENABLED)

    def supports_tier(self, tier: str) -> bool:
        return tier in self.tiers or "both" in self.tiers


class CortexToolRegistry:

    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}

    def register(self, tool: ToolEntry):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolEntry]:
        return self._tools.get(name)

    def get_all(self) -> list:
        return list(self._tools.values())

    def get_enabled(self) -> list:
        return [t for t in self._tools.values() if t.is_enabled()]

    def get_available(self) -> list:
        return [t for t in self._tools.values() if t.is_available()]

    def get_by_tier(self, tier: str) -> list:
        return [t for t in self._tools.values() if t.supports_tier(tier)]

    def get_by_category(self, category: str) -> list:
        return [t for t in self._tools.values() if t.category == category]

    def get_by_integration(self, integration: str) -> list:
        return [t for t in self._tools.values() if t.integration == integration]

    def get_for_venture(self, venture_name: str) -> list:
        return [
            t for t in self._tools.values()
            if not t.ventures or venture_name in t.ventures or "all" in t.ventures
        ]

    def set_state(self, name: str, state: str):
        if name in self._tools:
            self._tools[name].state = state

    def enable(self, name: str):
        self.set_state(name, ToolState.ENABLED)

    def disable(self, name: str):
        tool = self._tools.get(name)
        if tool:
            tool.state = ToolState.INSTALLED if tool.state == ToolState.ENABLED else tool.state

    def enable_for_venture(self, venture_name: str):
        for tool in self.get_for_venture(venture_name):
            if tool.state == ToolState.INSTALLED:
                tool.state = ToolState.ENABLED

    def disable_all(self):
        for tool in self._tools.values():
            if tool.state == ToolState.ENABLED:
                tool.state = ToolState.INSTALLED

    def auto_detect_installed(self):
        for tool in self._tools.values():
            if tool.state == ToolState.KNOWN and tool.env_key:
                if os.getenv(tool.env_key, ""):
                    tool.state = ToolState.INSTALLED

    def summary(self) -> str:
        lines = ["## CORTEX Tool Registry\n"]
        by_category: dict = {}
        for tool in self._tools.values():
            by_category.setdefault(tool.category, []).append(tool)
        for category, tools in sorted(by_category.items()):
            lines.append(f"### {category.title()}")
            for t in tools:
                tiers = "/".join(t.tiers) if t.tiers else "all"
                lines.append(
                    f"- **{t.display_name}** ({t.state}) [{tiers}] — {t.description}"
                )
            lines.append("")
        enabled = self.get_enabled()
        lines.append(f"**Enabled: {len(enabled)} / {len(self._tools)} tools**")
        return "\n".join(lines)

    @staticmethod
    def build_default() -> "CortexToolRegistry":
        registry = CortexToolRegistry()

        registry.register(ToolEntry(
            name="tavily",
            display_name="Tavily Search",
            category="research",
            integration=ToolIntegration.DIRECT_API,
            description="Real-time web search for current events, market data, news. Primary Tier 1 research tool.",
            tiers=["Tier1", "Tier2"],
            ventures=["all"],
            env_key="TAVILY_API_KEY",
        ))

        registry.register(ToolEntry(
            name="exa",
            display_name="Exa Search",
            category="research",
            integration=ToolIntegration.DIRECT_API,
            description="Neural semantic search for expert content, technical docs, research papers, code.",
            tiers=["Tier1", "Tier2"],
            ventures=["all"],
            env_key="EXA_API_KEY",
        ))

        registry.register(ToolEntry(
            name="perplexity",
            display_name="Perplexity Research",
            category="research",
            integration=ToolIntegration.DIRECT_API,
            description="Deep multi-source research synthesis. Tier 2 only. Hard cap $0.50/run via OpenRouter.",
            tiers=["Tier2"],
            ventures=["all"],
            env_key="API_KEY_OPENROUTER",
        ))

        registry.register(ToolEntry(
            name="firecrawl",
            display_name="Firecrawl",
            category="research",
            integration=ToolIntegration.DIRECT_API,
            description="Structured web scraping and content extraction into LLM-ready markdown.",
            tiers=["Tier1", "Tier2"],
            ventures=["all"],
            env_key="FIRECRAWL_API_KEY",
        ))

        registry.register(ToolEntry(
            name="github",
            display_name="GitHub MCP",
            category="dev",
            integration=ToolIntegration.MCP,
            description="Read GitHub repos, issues, PRs, code search. Read-only first.",
            tiers=["Tier1", "Tier2"],
            ventures=["product_dev", "open_source", "fundraising"],
            env_key="GITHUB_PERSONAL_ACCESS_TOKEN",
            mcp_server_name="github",
        ))

        registry.register(ToolEntry(
            name="browserbase",
            display_name="Browserbase Browser",
            category="browser",
            integration=ToolIntegration.MCP,
            description="Cloud browser automation. CAPTCHA-resistant, Fly.io-ready. For pages that block scrapers.",
            tiers=["Tier1", "Tier2"],
            ventures=["all"],
            env_key="BROWSERBASE_API_KEY",
            mcp_server_name="browserbase",
        ))

        registry.register(ToolEntry(
            name="composio",
            display_name="Composio",
            category="integrations",
            integration=ToolIntegration.COMPOSIO,
            description="300+ SaaS integrations: Gmail, Slack, Notion, HubSpot, Linear, Jira, and more. First choice for supported apps.",
            tiers=["Tier1", "Tier2"],
            ventures=["all"],
            env_key="COMPOSIO_API_KEY",
        ))

        registry.register(ToolEntry(
            name="surfsense",
            display_name="SurfSense Memory",
            category="memory",
            integration=ToolIntegration.DIRECT_API,
            description="CORTEX long-term memory, research storage, venture knowledge base. Always enabled.",
            tiers=["Tier1", "Tier2"],
            ventures=["all"],
            env_key="",
        ))

        registry.register(ToolEntry(
            name="graphiti",
            display_name="Graphiti / Zep",
            category="memory",
            integration=ToolIntegration.DIRECT_API,
            description="Temporal knowledge graph for entity relationships and project history.",
            tiers=["Tier1", "Tier2"],
            ventures=["all"],
            env_key="",
        ))

        registry.auto_detect_installed()

        for tool in registry._tools.values():
            if tool.name in ("surfsense", "graphiti", "tavily", "exa", "perplexity", "composio"):
                if tool.state == ToolState.INSTALLED:
                    tool.state = ToolState.ENABLED

        return registry
