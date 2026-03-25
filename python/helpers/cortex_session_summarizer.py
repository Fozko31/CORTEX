import uuid
from datetime import datetime
from typing import Optional


async def summarize_session(agent) -> dict:
    from python.helpers.cortex_model_router import CortexModelRouter

    history_text = agent.concat_messages(agent.history) if agent.history else ""
    if not history_text.strip():
        return _empty_summary()

    exchange_count = len([m for m in agent.history if getattr(m, "role", "") == "user"]) if agent.history else 0

    system = (
        "You are a session summarizer for CORTEX, an AI executive assistant.\n"
        "Given a conversation transcript, produce a structured JSON summary.\n"
        "Include:\n"
        '- "summary": 2-4 sentence narrative of what was discussed and decided\n'
        '- "topics": list of 2-5 topic keywords\n'
        '- "outcomes": list of {type: "decision"|"commitment"|"action_item", content: str, confidence: 0.0-1.0}\n'
        '- "knowledge_extracted": list of {fact: str, category: "user_preference"|"business_fact"|"decision"|"research"|"outcome"}\n'
        '- "venture_refs": list of venture names mentioned (or empty)\n'
        '- "mood": one of "productive"|"exploratory"|"frustrated"|"casual"|"urgent"\n'
        "Return ONLY valid JSON."
    )

    trimmed = history_text
    if len(trimmed) > 12000:
        trimmed = trimmed[:4000] + "\n\n[...middle trimmed...]\n\n" + trimmed[-4000:]

    try:
        response = await CortexModelRouter.call_routed_model(
            "summarization", system, trimmed, agent
        )
        from python.helpers.dirty_json import DirtyJson
        parsed = DirtyJson.parse_string(response)
        if isinstance(parsed, dict):
            return {
                "session_id": str(uuid.uuid4())[:12],
                "started_at": _session_start_time(agent),
                "ended_at": datetime.now().isoformat(),
                "exchange_count": exchange_count,
                "summary": parsed.get("summary", ""),
                "topics": parsed.get("topics", []),
                "outcomes": parsed.get("outcomes", []),
                "knowledge_extracted": parsed.get("knowledge_extracted", []),
                "venture_refs": parsed.get("venture_refs", []),
                "mood": parsed.get("mood", "productive"),
            }
    except Exception:
        pass

    return _empty_summary(exchange_count)


def extract_outcomes(summary_data: dict) -> list:
    return summary_data.get("outcomes", [])


def extract_knowledge(summary_data: dict) -> list:
    return summary_data.get("knowledge_extracted", [])


def _empty_summary(exchange_count: int = 0) -> dict:
    return {
        "session_id": str(uuid.uuid4())[:12],
        "started_at": datetime.now().isoformat(),
        "ended_at": datetime.now().isoformat(),
        "exchange_count": exchange_count,
        "summary": "",
        "topics": [],
        "outcomes": [],
        "knowledge_extracted": [],
        "venture_refs": [],
        "mood": "casual",
    }


def _session_start_time(agent) -> str:
    try:
        if agent.history:
            first = agent.history[0]
            ts = getattr(first, "timestamp", None)
            if ts:
                return ts if isinstance(ts, str) else ts.isoformat()
    except Exception:
        pass
    return datetime.now().isoformat()
