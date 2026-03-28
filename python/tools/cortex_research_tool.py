import json
from python.cortex.tool import Tool, Response
from python.helpers.print_style import PrintStyle
from python.helpers.cortex_research_orchestrator import CortexResearchOrchestrator

_JSON_PARSE_ERROR = "__JSON_PARSE_ERROR__"


class CortexResearch(Tool):

    async def execute(self, topic="", queries="", tier="Tier1", **kwargs):
        if not topic:
            topic = self.args.get("query", "") or self.args.get("topic", "")
        if not tier:
            tier = self.args.get("tier", "Tier1")
        if not queries:
            queries = self.args.get("queries", "")

        query_list = _parse_queries(queries, topic)

        if query_list is _JSON_PARSE_ERROR:
            return Response(
                message=(
                    "Research tool call failed: the `queries` argument looks like a JSON array "
                    "but could not be parsed. Please provide a valid JSON array of strings, "
                    "e.g. [\"query one\", \"query two\"]."
                ),
                break_loop=False,
            )

        if not query_list:
            return Response(
                message="No queries provided for research.", break_loop=False
            )

        # Validate all queries are non-empty strings
        bad = [q for q in query_list if not isinstance(q, str) or not q.strip()]
        if bad:
            return Response(
                message=(
                    f"Research tool call failed: {len(bad)} query entries are empty or not strings. "
                    "Each query must be a non-empty string."
                ),
                break_loop=False,
            )

        query_list = [q.strip() for q in query_list]

        PrintStyle(font_color="#5DADE2", bold=True).print(
            f"CORTEX Research [{tier}]: {topic} — {len(query_list)} queries"
        )

        orchestrator = CortexResearchOrchestrator.from_agent(self.agent)

        try:
            output = await orchestrator.research(
                topic=topic,
                queries=query_list,
                tier=tier,
            )
        except Exception as e:
            return Response(
                message=f"Research failed: {str(e)}", break_loop=False
            )

        if output.warnings:
            for w in output.warnings:
                PrintStyle(font_color="#F39C12").print(f"[Research Warning] {w}")

        return Response(message=output.context_summary, break_loop=False)


def _parse_queries(queries_arg, fallback_topic: str):
    """
    Parse the queries argument into a list of strings.
    Returns _JSON_PARSE_ERROR sentinel (not a list) if JSON was expected but malformed.
    """
    if not queries_arg:
        return [fallback_topic] if fallback_topic else []
    if isinstance(queries_arg, list):
        return [q for q in queries_arg if q]
    if isinstance(queries_arg, str):
        stripped = queries_arg.strip()
        # Strict JSON path — if it looks like a JSON array, require valid JSON
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [q for q in parsed if q]
                # Parsed fine but not a list — treat as error
                return _JSON_PARSE_ERROR
            except json.JSONDecodeError:
                return _JSON_PARSE_ERROR
        # Flexible plaintext path — newline or bullet list
        lines = [q.strip().lstrip("-•*").strip() for q in stripped.splitlines()]
        lines = [q for q in lines if q]
        if lines:
            return lines
        return [stripped]
    return [fallback_topic] if fallback_topic else []
