import json
import os
from datetime import datetime
from typing import Optional
from python.cortex.memory import get_agent_memory_subdir, abs_db_dir
from python.cortex.state import CortexState

CORE_SPACES = [
    "cortex_user_profile",
    "cortex_conversations",
    "cortex_knowledge",
    "cortex_outcomes",
    "cortex_weekly_digest",
    "cortex_cross_venture",
]

CATEGORY_TO_SPACE = {
    "user_preference": "cortex_user_profile",
    "conversation": "cortex_conversations",
    "business_fact": "cortex_knowledge",
    "research": "cortex_knowledge",
    "decision": "cortex_outcomes",
    "outcome": "cortex_outcomes",
}

SEARCH_KEYWORDS = {
    "cortex_user_profile": [
        "preference", "personality", "trust", "like", "dislike", "style",
        "want", "need", "prefer", "favorite", "habit",
    ],
    "cortex_conversations": [
        "said", "discussed", "talked", "conversation", "session", "chat",
        "last time", "previously", "mentioned", "remember when",
    ],
    "cortex_knowledge": [
        "fact", "know", "learned", "research", "information", "data",
        "how does", "what is", "explain",
    ],
    "cortex_outcomes": [
        "decided", "decision", "outcome", "result", "roi", "revenue",
        "committed", "promise", "action item",
    ],
    "cortex_weekly_digest": [
        "week", "summary", "overview", "trend", "pattern", "progress",
        "big picture", "overall",
    ],
    "cortex_cross_venture": [
        "across", "all ventures", "pattern", "lesson", "learned",
        "compare", "synergy",
    ],
}

DEFAULT_ROUTING_INDEX = {
    "spaces": {
        name: {
            "description": "",
            "search_when": SEARCH_KEYWORDS.get(name, []),
            "doc_count": 0,
            "last_updated": None,
        }
        for name in CORE_SPACES
    },
    "last_refreshed": None,
}


class CortexSurfSenseRouter:

    @staticmethod
    def venture_dna_space(venture_name: str) -> str:
        """Return the DNA space name for a venture."""
        from python.helpers.cortex_venture_dna import _safe_space_name
        return f"cortex_venture_{_safe_space_name(venture_name)}_dna"

    @staticmethod
    def venture_ops_space(venture_name: str) -> str:
        """Return the ops space name for a venture."""
        from python.helpers.cortex_venture_dna import _safe_space_name
        return f"cortex_venture_{_safe_space_name(venture_name)}_ops"

    @staticmethod
    def route_for_push(document: dict) -> list:
        meta = document.get("metadata", {})
        category = meta.get("category", "research")
        venture = meta.get("venture", "")
        ops_doc = meta.get("ops_doc", False)  # True = goes to ops space, False = DNA space

        spaces = []
        primary = CATEGORY_TO_SPACE.get(category, "cortex_knowledge")
        spaces.append(primary)

        if venture:
            # Two-space routing: ops_doc flag determines DNA vs ops space
            if ops_doc:
                spaces.append(CortexSurfSenseRouter.venture_ops_space(venture))
            else:
                spaces.append(CortexSurfSenseRouter.venture_dna_space(venture))

        return list(dict.fromkeys(spaces))

    @staticmethod
    async def route_for_push_smart(document: dict, agent) -> list:
        spaces = CortexSurfSenseRouter.route_for_push(document)
        return spaces

    @staticmethod
    def get_venture_spaces_for_active(agent) -> list:
        """Return DNA + ops space names for the currently active venture (if any)."""
        try:
            active_name = CortexState.for_agent(agent).get("active_venture_name") or ""
            if not active_name:
                return []
            return [
                CortexSurfSenseRouter.venture_dna_space(active_name),
                CortexSurfSenseRouter.venture_ops_space(active_name),
            ]
        except Exception:
            return []

    @staticmethod
    def route_for_search(query: str, routing_index: dict = None) -> list:
        query_lower = query.lower()
        scores = {}

        keywords = SEARCH_KEYWORDS
        if routing_index:
            for name, info in routing_index.get("spaces", {}).items():
                kw = info.get("search_when", [])
                if kw:
                    keywords[name] = kw

        for space_name, kws in keywords.items():
            score = 0
            for kw in kws:
                if kw in query_lower:
                    score += 1
            if score > 0:
                doc_count = 0
                if routing_index:
                    doc_count = routing_index.get("spaces", {}).get(space_name, {}).get("doc_count", 0)
                if doc_count > 0:
                    score += 0.5
                scores[space_name] = score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        result = [name for name, _ in ranked[:3]]

        if "cortex_knowledge" not in result:
            result.append("cortex_knowledge")

        return result[:3]

    @staticmethod
    async def route_for_search_smart(query: str, agent, routing_index: dict = None) -> list:
        fast_result = CortexSurfSenseRouter.route_for_search(query, routing_index)
        if fast_result and fast_result[0] != "cortex_knowledge":
            return fast_result

        try:
            from python.helpers.cortex_model_router import CortexModelRouter

            system = (
                "Given a user query, determine which 1-3 knowledge spaces to search.\n"
                "Available spaces:\n"
                "- cortex_user_profile: user preferences, personality, trust\n"
                "- cortex_conversations: past session summaries\n"
                "- cortex_knowledge: facts, research, general knowledge\n"
                "- cortex_outcomes: decisions, results, ROI\n"
                "- cortex_weekly_digest: weekly summaries, trends\n"
                "- cortex_cross_venture: cross-venture patterns\n\n"
                'Return JSON: {"spaces": ["space1", "space2"]}\n'
                "Return ONLY JSON."
            )
            response = await CortexModelRouter.call_routed_model(
                "classification", system, query[:500], agent
            )
            from python.cortex.dirty_json import DirtyJson
            parsed = DirtyJson.parse_string(response)
            if isinstance(parsed, dict) and "spaces" in parsed:
                spaces = parsed["spaces"]
                if isinstance(spaces, list) and spaces:
                    valid = [s for s in spaces if isinstance(s, str)]
                    if valid:
                        return valid[:3]
        except Exception:
            pass

        return fast_result

    @staticmethod
    def get_all_space_names(routing_index: dict = None) -> list:
        names = list(CORE_SPACES)
        if routing_index:
            for name in routing_index.get("spaces", {}):
                if name not in names:
                    names.append(name)
        return names

    @staticmethod
    def _index_path(agent) -> str:
        base = abs_db_dir(get_agent_memory_subdir(agent))
        return os.path.join(base, "cortex_space_index.json")

    @staticmethod
    def load_routing_index(agent) -> dict:
        try:
            path = CortexSurfSenseRouter._index_path(agent)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return json.loads(json.dumps(DEFAULT_ROUTING_INDEX))

    @staticmethod
    def save_routing_index(agent, index: dict):
        try:
            path = CortexSurfSenseRouter._index_path(agent)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def update_routing_index(agent, space_name: str, doc_count_delta: int = 1):
        index = CortexSurfSenseRouter.load_routing_index(agent)
        spaces = index.get("spaces", {})
        if space_name not in spaces:
            spaces[space_name] = {
                "description": f"CORTEX space: {space_name}",
                "search_when": [],
                "doc_count": 0,
                "last_updated": None,
            }
        spaces[space_name]["doc_count"] = spaces[space_name].get("doc_count", 0) + doc_count_delta
        spaces[space_name]["last_updated"] = datetime.now().isoformat()
        index["spaces"] = spaces
        index["last_refreshed"] = datetime.now().isoformat()
        CortexSurfSenseRouter.save_routing_index(agent, index)

    @staticmethod
    async def refresh_routing_index(agent, surfsense_client):
        try:
            spaces = await surfsense_client.list_spaces()
            index = CortexSurfSenseRouter.load_routing_index(agent)
            for s in spaces:
                name = s.get("name", "")
                if name.startswith("cortex_"):
                    if name not in index["spaces"]:
                        index["spaces"][name] = {
                            "description": s.get("description", ""),
                            "search_when": SEARCH_KEYWORDS.get(name, []),
                            "doc_count": 0,
                            "last_updated": None,
                        }
            index["last_refreshed"] = datetime.now().isoformat()
            CortexSurfSenseRouter.save_routing_index(agent, index)
        except Exception:
            pass
