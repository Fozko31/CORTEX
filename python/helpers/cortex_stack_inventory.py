"""
cortex_stack_inventory.py — Authoritative definition of CORTEX's technology stack.

This is the source of truth for Loop 5 research. Each component is defined with
its role, current version/API, dependencies, and what to monitor for.

Updated manually after each stack change (or automatically via Loop 5 apply).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StackComponent:
    component: str          # canonical name
    category: str           # "llm" | "memory" | "research" | "communication" | "infra" | "voice" | "vision"
    role: str               # what it does in CORTEX
    version: str            # current version or model ID
    api_endpoint: str       # API or service URL
    cost_model: str         # "per_token" | "per_request" | "monthly_flat" | "free_local"
    cost_estimate: str      # rough cost estimate
    dependencies: list = field(default_factory=list)  # other components that depend on this
    alternatives_to_monitor: list = field(default_factory=list)  # competitors to watch
    last_researched: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "category": self.category,
            "role": self.role,
            "version": self.version,
            "api_endpoint": self.api_endpoint,
            "cost_model": self.cost_model,
            "cost_estimate": self.cost_estimate,
            "dependencies": self.dependencies,
            "alternatives_to_monitor": self.alternatives_to_monitor,
            "last_researched": self.last_researched,
            "notes": self.notes,
        }


STACK: list[StackComponent] = [

    # ─── LLM ─────────────────────────────────────────────────────────────────

    StackComponent(
        component="claude_sonnet_46",
        category="llm",
        role="Primary LLM for all CORTEX reasoning, synthesis, and user-facing responses",
        version="claude-sonnet-4-6",
        api_endpoint="https://openrouter.ai/api/v1 (model: anthropic/claude-sonnet-4-6)",
        cost_model="per_token",
        cost_estimate="~$3/$15 per M input/output tokens via OpenRouter",
        dependencies=["openrouter"],
        alternatives_to_monitor=["claude-opus-4-6", "gemini-2-0-pro", "gpt-4-turbo"],
        notes="Always the final synthesis engine. Downgrade only if G.1 DSPy identifies a cheaper equivalent.",
    ),

    StackComponent(
        component="deepseek_v3",
        category="llm",
        role="Cheap workhorse: voice cleanup, vision Step 2, experiment judge, benchmark runner",
        version="deepseek-chat-v3-0324",
        api_endpoint="https://openrouter.ai/api/v1 (model: deepseek/deepseek-chat-v3-0324)",
        cost_model="per_token",
        cost_estimate="~$0.27/$1.10 per M input/output tokens",
        dependencies=["openrouter"],
        alternatives_to_monitor=["deepseek-r1", "qwen-2-5-72b", "llama-3-3-70b"],
        notes="DeepSeek V3.2 is the cost-efficiency backbone. Monitor for new versions.",
    ),

    StackComponent(
        component="gemini_flash_lite",
        category="llm",
        role="Vision Step 1: raw image description (fast, cheap multimodal)",
        version="google/gemini-2.0-flash-lite-001",
        api_endpoint="https://openrouter.ai/api/v1",
        cost_model="per_token",
        cost_estimate="~$0.075/$0.30 per M tokens",
        dependencies=["openrouter"],
        alternatives_to_monitor=["gemini-2-0-flash", "claude-haiku-4-5", "llava-1-6"],
        notes="Do NOT use date-suffixed preview variants. Use stable GA model IDs only.",
    ),

    StackComponent(
        component="openrouter",
        category="infra",
        role="LLM routing gateway — provides access to all models via single API key",
        version="v1",
        api_endpoint="https://openrouter.ai/api/v1/chat/completions",
        cost_model="pass_through",
        cost_estimate="Model cost + ~0% markup",
        dependencies=[],
        alternatives_to_monitor=["direct anthropic API", "together.ai", "fireworks.ai"],
        notes="Central dependency. If OpenRouter goes down, all LLM calls fail. Monitor uptime.",
    ),

    # ─── MEMORY ──────────────────────────────────────────────────────────────

    StackComponent(
        component="faiss_local",
        category="memory",
        role="L1 memory: fast local vector search for entities and facts per session",
        version="faiss 1.x (Agent Zero built-in)",
        api_endpoint="local filesystem (usr/memory/cortex_main/)",
        cost_model="free_local",
        cost_estimate="$0 — CPU-based",
        dependencies=[],
        alternatives_to_monitor=["hnswlib", "chroma", "lancedb", "pgvector"],
        notes="On Fly.io: lives on Fly Volume. Snapshotted pre-experiment.",
    ),

    StackComponent(
        component="zep_graphiti",
        category="memory",
        role="L2 memory: temporal knowledge graph — entity relationships over time",
        version="Zep Cloud (Graphiti backend)",
        api_endpoint="https://api.getzep.com",
        cost_model="monthly_flat",
        cost_estimate="Free tier + paid plans",
        dependencies=[],
        alternatives_to_monitor=["neo4j aura", "falkordb", "memgraph", "local graphiti self-host"],
        notes="Cloud-external: survives code rollbacks. Monitor for pricing changes.",
    ),

    StackComponent(
        component="surfsense",
        category="memory",
        role="L3 memory: cross-device consciousness, session summaries, knowledge documents",
        version="SurfSense Cloud API",
        api_endpoint="https://api.surfsense.net",
        cost_model="per_request",
        cost_estimate="Free tier + usage-based",
        dependencies=[],
        alternatives_to_monitor=["ragie.ai", "mem0", "cognee", "private SurfSense self-host"],
        notes="Cloud-external. Houses cortex_optimization space for Loop 3/5 data.",
    ),

    # ─── RESEARCH ────────────────────────────────────────────────────────────

    StackComponent(
        component="tavily",
        category="research",
        role="Tier 1 research: real-time web search with structured results",
        version="Tavily Search API v1",
        api_endpoint="https://api.tavily.com",
        cost_model="per_request",
        cost_estimate="~$0.01/search",
        dependencies=[],
        alternatives_to_monitor=["serper", "brave search API", "you.com API", "bing search API"],
        notes="Paired with Exa for complementary coverage.",
    ),

    StackComponent(
        component="exa",
        category="research",
        role="Tier 1 research: neural semantic search over web content",
        version="Exa Search API",
        api_endpoint="https://api.exa.ai",
        cost_model="per_request",
        cost_estimate="~$0.01/search",
        dependencies=[],
        alternatives_to_monitor=["metaphor", "you.com", "bing news API"],
        notes="Complements Tavily — neural vs. keyword.",
    ),

    StackComponent(
        component="perplexity",
        category="research",
        role="Tier 2 research: synthesis + citation with Tier 1 findings as context",
        version="perplexity/sonar-pro via OpenRouter",
        api_endpoint="https://openrouter.ai/api/v1",
        cost_model="per_token",
        cost_estimate="~$3/$15 per M tokens (expensive — used sparingly)",
        dependencies=["openrouter"],
        alternatives_to_monitor=["perplexity-sonar-huge", "you.com research", "consensus"],
        notes="Hard cap $0.50/run. Cost-capped by CortexModelRouter.",
    ),

    StackComponent(
        component="firecrawl",
        category="research",
        role="Web page extraction: scrape, extract structured data, crawl",
        version="Firecrawl API v1",
        api_endpoint="https://api.firecrawl.dev",
        cost_model="per_request",
        cost_estimate="~$0.005-0.01/page",
        dependencies=[],
        alternatives_to_monitor=["jina reader", "browserless", "zenrows", "brightdata"],
        notes="Used for deep page extraction when search results are insufficient.",
    ),

    # ─── COMMUNICATION ───────────────────────────────────────────────────────

    StackComponent(
        component="telegram",
        category="communication",
        role="Primary user interface: text, voice, images, documents in/out",
        version="python-telegram-bot 20.x (Bot API 7.x)",
        api_endpoint="https://api.telegram.org",
        cost_model="free_local",
        cost_estimate="$0 — free API",
        dependencies=[],
        alternatives_to_monitor=["signal API", "whatsapp business API", "discord bot"],
        notes="Free and reliable. Only replace if user requests different channel.",
    ),

    # ─── VOICE ───────────────────────────────────────────────────────────────

    StackComponent(
        component="kokoro_tts",
        category="voice",
        role="English TTS: local inference, zero cost, CPU-viable",
        version="hexgrad/Kokoro-82M (af_heart voice)",
        api_endpoint="local (HuggingFace model)",
        cost_model="free_local",
        cost_estimate="$0 — local CPU inference",
        dependencies=[],
        alternatives_to_monitor=["coqui TTS", "piper TTS", "openai TTS", "elevenlabs"],
        notes="Already installed. 24kHz WAV output. Runs in executor for async compat.",
    ),

    StackComponent(
        component="azure_tts",
        category="voice",
        role="Slovenian TTS: RokNeural/PetraNeural voices, 0.5M chars/month free",
        version="Azure Cognitive Services Speech SDK 1.40+",
        api_endpoint="https://{region}.tts.speech.microsoft.com",
        cost_model="monthly_flat",
        cost_estimate="Free up to 0.5M chars/month (covers all realistic usage)",
        dependencies=[],
        alternatives_to_monitor=["google TTS (sl-SI)", "elevenlabs custom", "voicemaker"],
        notes="sl-SI region: westeurope. Free tier covers usage unless very high volume.",
    ),

    StackComponent(
        component="soniox_stt",
        category="voice",
        role="STT: 6.8% WER Slovenian — best available",
        version="Soniox API (async submit-poll)",
        api_endpoint="https://api.soniox.com",
        cost_model="per_request",
        cost_estimate="~$0.10/hour of audio",
        dependencies=[],
        alternatives_to_monitor=["google chirp_2 (10.8% WER, 14x costlier)", "whisper-v3", "assemblyai"],
        notes="No free tier. Pay-per-use. Fund account at soniox.com when ready.",
    ),

    # ─── INFRA ───────────────────────────────────────────────────────────────

    StackComponent(
        component="agent_zero",
        category="infra",
        role="Framework base: extension system, tool system, memory integration",
        version="Fork of agent0ai/agent-zero (github.com/Fozko31/CORTEX)",
        api_endpoint="local",
        cost_model="free_local",
        cost_estimate="$0",
        dependencies=[],
        alternatives_to_monitor=["autogen", "crewai", "langchain agents", "smolagents"],
        notes="Zero core modifications. All CORTEX customization via extension hooks.",
    ),

    StackComponent(
        component="sqlite",
        category="infra",
        role="Event store + outcome ledger: local append-only structured storage",
        version="sqlite3 (Python built-in)",
        api_endpoint="local file (Fly Volume)",
        cost_model="free_local",
        cost_estimate="$0",
        dependencies=[],
        alternatives_to_monitor=["duckdb", "litestream (replication)"],
        notes="Stable. Unlikely to need replacement. Litestream for replication if multi-instance.",
    ),
]


def get_all() -> list[dict]:
    return [c.to_dict() for c in STACK]


def get_by_category(category: str) -> list[dict]:
    return [c.to_dict() for c in STACK if c.category == category]


def get_by_component(name: str) -> Optional[dict]:
    comp = next((c for c in STACK if c.component == name), None)
    return comp.to_dict() if comp else None


def summary() -> dict:
    by_cat: dict = {}
    for c in STACK:
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
    return {"total_components": len(STACK), "by_category": by_cat}
