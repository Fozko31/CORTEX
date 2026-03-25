from dataclasses import dataclass, field
from typing import Optional

from python.helpers.cortex_tavily_client import CortexTavilyClient, TavilyResult
from python.helpers.cortex_exa_client import CortexExaClient, ExaResult
from python.helpers.cortex_perplexity_client import (
    CortexPerplexityClient,
    PerplexityResult,
    PerplexityCapExceededError,
)


@dataclass
class ResearchOutput:
    tier: str = ""
    topic: str = ""
    tavily_results: list = field(default_factory=list)
    exa_results: list = field(default_factory=list)
    perplexity_result: Optional[PerplexityResult] = None
    context_summary: str = ""
    sources: list = field(default_factory=list)
    run_cost_usd: float = 0.0
    warnings: list = field(default_factory=list)


class CortexResearchOrchestrator:

    def __init__(
        self,
        tavily: CortexTavilyClient,
        exa: CortexExaClient,
        perplexity: Optional[CortexPerplexityClient] = None,
    ):
        self.tavily = tavily
        self.exa = exa
        self.perplexity = perplexity

    @staticmethod
    def from_agent(agent) -> "CortexResearchOrchestrator":
        tavily = CortexTavilyClient.from_agent_config(agent)
        exa = CortexExaClient.from_agent_config(agent)
        perplexity = CortexPerplexityClient.from_agent_config(agent)
        return CortexResearchOrchestrator(tavily=tavily, exa=exa, perplexity=perplexity)

    async def research(
        self,
        topic: str,
        queries: list,
        tier: str = "Tier1",
        max_results_per_query: int = 5,
    ) -> ResearchOutput:
        output = ResearchOutput(tier=tier, topic=topic)
        sources_seen: set = set()

        tavily_results = await self._run_tavily(
            queries, max_results_per_query, sources_seen
        )
        output.tavily_results = tavily_results

        exa_results = await self._run_exa(
            queries, max_results_per_query, sources_seen
        )
        output.exa_results = exa_results

        output.sources = list(sources_seen)

        if tier == "Tier2" and self.perplexity and self.perplexity.is_configured():
            context = _format_context_for_perplexity(tavily_results, exa_results)
            try:
                result = await self.perplexity.query(
                    question=topic,
                    context=context,
                    tier="Tier2",
                )
                output.perplexity_result = result
                output.run_cost_usd += result.estimated_cost_usd
                warning = self.perplexity.soft_cap_warning()
                if warning:
                    output.warnings.append(warning)
            except PerplexityCapExceededError as e:
                output.warnings.append(str(e))

        output.context_summary = _build_context_summary(output)
        return output

    async def _run_tavily(
        self, queries: list, max_results: int, sources_seen: set
    ) -> list:
        if not self.tavily.is_configured():
            return []
        all_results = []
        for query in queries:
            try:
                hits = await self.tavily.search(query, max_results=max_results)
                for hit in hits:
                    if hit.url not in sources_seen:
                        sources_seen.add(hit.url)
                        all_results.append(hit)
            except Exception:
                pass
        return all_results

    async def _run_exa(
        self, queries: list, max_results: int, sources_seen: set
    ) -> list:
        if not self.exa.is_configured():
            return []
        all_results = []
        for query in queries:
            try:
                hits = await self.exa.search(query, num_results=max_results)
                for hit in hits:
                    if hit.url not in sources_seen:
                        sources_seen.add(hit.url)
                        all_results.append(hit)
            except Exception:
                pass
        return all_results


def _format_context_for_perplexity(
    tavily_results: list, exa_results: list
) -> str:
    parts = []
    if tavily_results:
        parts.append("Tavily findings:")
        for r in tavily_results[:6]:
            snippet = r.content[:400].replace("\n", " ") if r.content else ""
            parts.append(f"- [{r.title}]({r.url}): {snippet}")
    if exa_results:
        parts.append("\nExa findings:")
        for r in exa_results[:6]:
            snippet = r.content[:400].replace("\n", " ") if r.content else ""
            parts.append(f"- [{r.title}]({r.url}): {snippet}")
    return "\n".join(parts)


def _build_context_summary(output: ResearchOutput) -> str:
    sections = []
    sections.append(f"## Research: {output.topic}  [Tier: {output.tier}]")

    if output.tavily_results:
        sections.append("\n### Tavily — Current / Market")
        answer = next(
            (r.answer for r in output.tavily_results if r.answer), ""
        )
        if answer:
            sections.append(f"**Summary:** {answer}")
        for r in output.tavily_results:
            snippet = r.content[:600].rstrip() if r.content else ""
            sections.append(f"\n**{r.title}**\n{r.url}\n{snippet}")
    else:
        sections.append("\n### Tavily — not configured or no results")

    if output.exa_results:
        sections.append("\n### Exa — Expert / Technical")
        for r in output.exa_results:
            date = f" ({r.published_date[:10]})" if r.published_date else ""
            snippet = r.content[:600].rstrip() if r.content else ""
            sections.append(f"\n**{r.title}**{date}\n{r.url}\n{snippet}")
    else:
        sections.append("\n### Exa — not configured or no results")

    if output.perplexity_result:
        sections.append("\n### Perplexity — Deep Research (Tier 2)")
        sections.append(output.perplexity_result.content)
        if output.perplexity_result.citations:
            sections.append(
                "Sources: " + ", ".join(output.perplexity_result.citations[:5])
            )

    if output.warnings:
        sections.append("\n### Warnings")
        for w in output.warnings:
            sections.append(f"- {w}")

    if output.sources:
        sections.append(f"\n_Total unique sources: {len(output.sources)}_")

    return "\n".join(sections)
