from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from python.helpers.cortex_tool_registry import (
    CortexToolRegistry,
    ToolEntry,
    ToolState,
)

_DEFAULT_STATE_FILE = Path("usr/memory/cortex_main/cortex_venture_state.json")


@dataclass
class VenturePack:
    name: str
    display_name: str
    description: str
    core_tools: list = field(default_factory=list)
    tier1_tools: list = field(default_factory=list)
    tier2_tools: list = field(default_factory=list)
    composio_apps: list = field(default_factory=list)

    def all_tools(self) -> list:
        seen = set()
        result = []
        for t in self.core_tools + self.tier1_tools + self.tier2_tools:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result


class CortexVentureActivation:

    def __init__(self, registry: CortexToolRegistry, state_file: Path = _DEFAULT_STATE_FILE):
        self.registry = registry
        self._packs: dict[str, VenturePack] = {}
        self._active_venture: Optional[str] = None
        self._active_pack: Optional[VenturePack] = None
        self._state_file = state_file

    # ── Persistence ──────────────────────────────────────────────────────────

    def save_state(self) -> None:
        """Persist active venture name to disk so it survives restarts."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps({"active_venture": self._active_venture}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # never crash on state save

    def load_state(self) -> None:
        """Restore active venture from disk if the state file exists."""
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            name = data.get("active_venture")
            if name and name in self._packs:
                self.activate(name, _persist=False)  # avoid double-write on load
        except Exception:
            pass

    # ── Pack management ───────────────────────────────────────────────────────

    def register_pack(self, pack: VenturePack):
        self._packs[pack.name] = pack

    def get_pack(self, name: str) -> Optional[VenturePack]:
        return self._packs.get(name)

    def list_packs(self) -> list:
        return list(self._packs.values())

    def activate(self, venture_name: str, _persist: bool = True):
        pack = self._packs.get(venture_name)
        if pack is None:
            return
        if self._active_venture and self._active_venture != venture_name:
            self.deactivate(_persist=False)
        self._active_venture = venture_name
        self._active_pack = pack
        for tool_name in pack.all_tools():
            tool = self.registry.get(tool_name)
            if tool and tool.state == ToolState.INSTALLED:
                self.registry.enable(tool_name)
        if _persist:
            self.save_state()

    def deactivate(self, _persist: bool = True):
        if self._active_pack:
            for tool_name in self._active_pack.all_tools():
                tool = self.registry.get(tool_name)
                if tool and tool.state == ToolState.ENABLED:
                    tool.state = ToolState.INSTALLED
        self._active_venture = None
        self._active_pack = None
        if _persist:
            self.save_state()

    def active_venture(self) -> Optional[str]:
        return self._active_venture

    def active_pack(self) -> Optional[VenturePack]:
        return self._active_pack

    def active_tools(self) -> list:
        return self.registry.get_enabled()

    def composio_apps_for_active_venture(self) -> list:
        if self._active_pack:
            return self._active_pack.composio_apps
        return []

    def tool_context_for_agent(self) -> str:
        if not self._active_venture or not self._active_pack:
            tools = self.registry.get_enabled()
            venture_label = "No active venture"
        else:
            tools = self.active_tools()
            venture_label = f"{self._active_pack.display_name} ({self._active_venture})"

        if not tools:
            return f"Active venture: {venture_label}\nNo tools currently enabled."

        lines = [f"Active venture: {venture_label}", "Enabled tools:"]
        for tool in sorted(tools, key=lambda t: t.category):
            tiers = "/".join(tool.tiers) if tool.tiers else "all tiers"
            lines.append(f"  - {tool.display_name} [{tool.category}, {tiers}]: {tool.description}")

        if self._active_pack and self._active_pack.composio_apps:
            lines.append(f"Composio apps for this venture: {', '.join(self._active_pack.composio_apps)}")

        return "\n".join(lines)

    @staticmethod
    def build_default(registry: CortexToolRegistry) -> "CortexVentureActivation":
        activation = CortexVentureActivation(registry)

        activation.register_pack(VenturePack(
            name="core",
            display_name="Core / Always-On",
            description="Base tools always available to CORTEX regardless of venture.",
            core_tools=["tavily", "exa", "perplexity", "surfsense", "graphiti", "composio"],
            tier1_tools=["tavily", "exa", "firecrawl"],
            tier2_tools=["perplexity", "firecrawl", "browserbase"],
            composio_apps=[],
        ))

        activation.register_pack(VenturePack(
            name="market_research",
            display_name="Market Research",
            description="Deep market research, competitor analysis, trend analysis, industry landscape.",
            core_tools=["tavily", "exa", "surfsense", "graphiti"],
            tier1_tools=["tavily", "exa", "firecrawl"],
            tier2_tools=["perplexity", "browserbase"],
            composio_apps=[],
        ))

        activation.register_pack(VenturePack(
            name="product_dev",
            display_name="Product Development",
            description="Software development, repo analysis, issue tracking, technical research.",
            core_tools=["tavily", "exa", "github", "surfsense", "graphiti"],
            tier1_tools=["tavily", "exa", "github", "firecrawl"],
            tier2_tools=["perplexity", "browserbase"],
            composio_apps=["github", "linear", "jira", "notion"],
        ))

        activation.register_pack(VenturePack(
            name="content",
            display_name="Content & Distribution",
            description="Content research, creation strategy, distribution across channels.",
            core_tools=["tavily", "exa", "surfsense", "composio"],
            tier1_tools=["tavily", "exa", "firecrawl"],
            tier2_tools=["perplexity", "browserbase"],
            composio_apps=["twitter", "linkedin", "notion", "wordpress", "slack"],
        ))

        activation.register_pack(VenturePack(
            name="operations",
            display_name="Business Operations",
            description="Business operations, team coordination, project management, communications.",
            core_tools=["tavily", "surfsense", "graphiti", "composio"],
            tier1_tools=["tavily", "exa"],
            tier2_tools=["perplexity"],
            composio_apps=["gmail", "slack", "notion", "hubspot", "airtable", "google_calendar"],
        ))

        activation.register_pack(VenturePack(
            name="fundraising",
            display_name="Fundraising & Investors",
            description="Investor research, deck prep, due diligence support, cap table management.",
            core_tools=["tavily", "exa", "surfsense", "graphiti", "github"],
            tier1_tools=["tavily", "exa", "firecrawl"],
            tier2_tools=["perplexity", "browserbase"],
            composio_apps=["gmail", "notion", "slack", "linkedin"],
        ))

        activation.load_state()
        return activation
