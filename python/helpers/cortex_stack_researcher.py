"""
cortex_stack_researcher.py — Loop 5: research each CORTEX stack component for updates.

For each component in the stack inventory:
1. Build targeted search queries (changelog, alternatives, pricing, reliability)
2. Run Tier 1 research (Tavily + Exa)
3. Synthesize findings via DeepSeek (cheap — not Claude)
4. Return structured findings list for stack_evaluator

Called by cortex_ruflo_session_packager on bi-monthly schedule (3am CET, 1st of odd months).
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx


_OR_BASE = "https://openrouter.ai/api/v1/chat/completions"
_SYNTHESIS_MODEL = "deepseek/deepseek-chat-v3-0324"  # cheap synthesis


@dataclass
class ComponentFinding:
    component: str
    category: str
    current_version: str
    researched_at: str = ""
    update_available: bool = False
    update_description: str = ""
    pricing_change: bool = False
    pricing_change_description: str = ""
    reliability_signals: list = field(default_factory=list)
    notable_alternatives: list = field(default_factory=list)
    raw_snippets: list = field(default_factory=list)
    recommendation: str = "stable"  # "stable" | "monitor" | "investigate" | "replace"
    recommendation_reason: str = ""

    def __post_init__(self):
        if not self.researched_at:
            self.researched_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "category": self.category,
            "current_version": self.current_version,
            "researched_at": self.researched_at,
            "update_available": self.update_available,
            "update_description": self.update_description,
            "pricing_change": self.pricing_change,
            "pricing_change_description": self.pricing_change_description,
            "reliability_signals": self.reliability_signals,
            "notable_alternatives": self.notable_alternatives,
            "recommendation": self.recommendation,
            "recommendation_reason": self.recommendation_reason,
        }


def _build_search_queries(component: dict) -> list[str]:
    """Build targeted search queries for a component."""
    name = component["component"]
    version = component["version"]
    alternatives = component.get("alternatives_to_monitor", [])[:2]

    queries = [
        f"{name} changelog release notes 2025 2026 new version",
        f"{name} pricing changes API updates reliability issues",
    ]

    if alternatives:
        alt_str = " vs ".join(alternatives[:2])
        queries.append(f"{name} vs {alt_str} comparison performance cost 2025")

    return queries


async def _search_tavily(query: str, api_key: str, max_results: int = 3) -> list[dict]:
    """Run a Tavily search, return list of {title, url, content} dicts."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": False,
                },
            )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")[:400]}
            for r in data.get("results", [])
        ]
    except Exception:
        return []


async def _search_exa(query: str, api_key: str, max_results: int = 2) -> list[dict]:
    """Run an Exa neural search, return list of {title, url, content} dicts."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "numResults": max_results,
                    "contents": {"text": {"maxCharacters": 400}},
                },
            )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("text", "")[:400]}
            for r in data.get("results", [])
        ]
    except Exception:
        return []


async def _synthesize_findings(component: dict, snippets: list[dict]) -> ComponentFinding:
    """Use DeepSeek to synthesize raw snippets into a structured ComponentFinding."""
    api_key = os.environ.get("API_KEY_OPENROUTER", "")
    if not api_key or not snippets:
        return ComponentFinding(
            component=component["component"],
            category=component["category"],
            current_version=component["version"],
            recommendation="stable",
            recommendation_reason="No research data available.",
        )

    snippet_text = "\n\n".join(
        f"[{i+1}] {s.get('title', '')}\n{s.get('content', '')}"
        for i, s in enumerate(snippets[:8])
    )

    prompt = (
        f"You are evaluating whether CORTEX should update or replace a technology component.\n\n"
        f"Component: {component['component']}\n"
        f"Category: {component['category']}\n"
        f"Current version/model: {component['version']}\n"
        f"Role in CORTEX: {component['role']}\n"
        f"Alternatives to monitor: {component.get('alternatives_to_monitor', [])}\n\n"
        f"Research snippets (recent web results):\n{snippet_text}\n\n"
        "Analyze the snippets and respond with ONLY a JSON object:\n"
        "{\n"
        '  "update_available": true/false,\n'
        '  "update_description": "brief description of any new version/model",\n'
        '  "pricing_change": true/false,\n'
        '  "pricing_change_description": "brief description of pricing change if any",\n'
        '  "reliability_signals": ["list of any reliability/outage mentions"],\n'
        '  "notable_alternatives": ["alternative name: one-line comparison"],\n'
        '  "recommendation": "stable|monitor|investigate|replace",\n'
        '  "recommendation_reason": "1-2 sentences explaining recommendation"\n'
        "}\n\n"
        "Criteria:\n"
        "- stable: no significant changes, component performing well\n"
        "- monitor: minor changes or interesting alternatives emerging\n"
        "- investigate: significant update or pricing change warrants deeper look\n"
        "- replace: clear superior alternative exists with cost or quality advantage\n"
        "Be conservative — only recommend 'investigate' or 'replace' with strong evidence."
    )

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                _OR_BASE,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": _SYNTHESIS_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
            )
        if resp.status_code != 200:
            raise ValueError(f"API error {resp.status_code}")

        raw = resp.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)

        return ComponentFinding(
            component=component["component"],
            category=component["category"],
            current_version=component["version"],
            update_available=parsed.get("update_available", False),
            update_description=parsed.get("update_description", ""),
            pricing_change=parsed.get("pricing_change", False),
            pricing_change_description=parsed.get("pricing_change_description", ""),
            reliability_signals=parsed.get("reliability_signals", []),
            notable_alternatives=parsed.get("notable_alternatives", []),
            raw_snippets=[s.get("url", "") for s in snippets[:5]],
            recommendation=parsed.get("recommendation", "stable"),
            recommendation_reason=parsed.get("recommendation_reason", ""),
        )
    except Exception as e:
        return ComponentFinding(
            component=component["component"],
            category=component["category"],
            current_version=component["version"],
            recommendation="stable",
            recommendation_reason=f"Synthesis failed: {e}",
        )


async def research_component(component: dict) -> ComponentFinding:
    """
    Research a single stack component.
    Runs 2-3 search queries (Tavily + Exa), synthesizes via DeepSeek.
    """
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    exa_key = os.environ.get("EXA_API_KEY", "")

    queries = _build_search_queries(component)

    # Gather snippets from both sources in parallel
    all_snippets: list[dict] = []
    tasks = []
    for q in queries[:2]:  # max 2 queries per component to control cost
        if tavily_key:
            tasks.append(_search_tavily(q, tavily_key, max_results=3))
        if exa_key:
            tasks.append(_search_exa(q, exa_key, max_results=2))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_snippets.extend(r)

    # Synthesize findings
    finding = await _synthesize_findings(component, all_snippets)
    return finding


async def run_full_research(
    categories: Optional[list[str]] = None,
    max_components: int = 17,
) -> list[dict]:
    """
    Run Loop 5 research across all (or specified) stack components.
    categories: filter by category (e.g. ["llm", "memory"]). None = all.
    max_components: safety cap.
    Returns list of ComponentFinding dicts.

    Rate-limited: components researched sequentially with 2s sleep to avoid
    hitting rate limits on Tavily/Exa.
    """
    from python.helpers.cortex_stack_inventory import STACK

    components = [c.to_dict() for c in STACK]
    if categories:
        components = [c for c in components if c["category"] in categories]
    components = components[:max_components]

    findings = []
    for comp in components:
        try:
            finding = await research_component(comp)
            findings.append(finding.to_dict())

            # Update last_researched in event store
            try:
                from python.helpers import cortex_event_store as es
                es.log_benchmark_run(
                    suite_id=f"stack_research_{comp['component']}",
                    scores={"recommendation": ["stable", "monitor", "investigate", "replace"].index(finding.recommendation) / 3.0},
                    baseline_scores={},
                    drift_flags=[],
                )
            except Exception:
                pass

            await asyncio.sleep(2)  # rate limiting
        except Exception:
            findings.append({
                "component": comp["component"],
                "category": comp["category"],
                "current_version": comp["version"],
                "recommendation": "stable",
                "recommendation_reason": "Research skipped due to error.",
                "researched_at": datetime.now().isoformat(),
            })

    return findings


async def run_quick_research(component_names: list[str]) -> list[dict]:
    """Research specific components by name (for manual Loop 5 trigger)."""
    from python.helpers.cortex_stack_inventory import STACK

    components = [c.to_dict() for c in STACK if c["component"] in component_names]
    findings = []
    for comp in components:
        finding = await research_component(comp)
        findings.append(finding.to_dict())
        await asyncio.sleep(1)
    return findings


def format_findings_summary(findings: list[dict]) -> str:
    """Format findings for Telegram report."""
    if not findings:
        return "No stack research findings available."

    investigate = [f for f in findings if f.get("recommendation") in ("investigate", "replace")]
    monitor = [f for f in findings if f.get("recommendation") == "monitor"]
    stable = [f for f in findings if f.get("recommendation") == "stable"]

    lines = [
        f"*Loop 5 Stack Research — {datetime.now().strftime('%Y-%m-%d')}*",
        f"Components researched: {len(findings)}",
        "",
    ]

    if investigate:
        lines.append("*Action Required:*")
        for f in investigate:
            rec = f.get("recommendation", "").upper()
            lines.append(f"- [{rec}] {f['component']}: {f.get('recommendation_reason', '')}")
        lines.append("")

    if monitor:
        lines.append("*Monitor:*")
        for f in monitor:
            lines.append(f"- {f['component']}: {f.get('recommendation_reason', '')}")
        lines.append("")

    lines.append(f"Stable: {len(stable)} components")
    return "\n".join(lines)
