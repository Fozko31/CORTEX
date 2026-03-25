import re
import uuid
from datetime import datetime, date
from typing import Optional

VALID_SOURCES = ("cortex_extraction", "user_upload", "scheduler_digest", "connector_sync")
VALID_CATEGORIES = (
    "user_preference", "business_fact", "decision",
    "research", "outcome", "conversation",
)
VALID_SUMMARY_LEVELS = ("raw", "extracted", "summarized", "digest")


_CATEGORY_LABELS = {
    "conversation": "Session",
    "decision": "Decision",
    "outcome": "Outcome",
    "research": "Research",
    "user_preference": "Preference",
    "business_fact": "Fact",
}


def generate_title(category: str, dt: date, topic: str) -> str:
    # Natural language title — preserve amounts (€29), names, case.
    # Title is the ONLY keyword-searchable field SurfSense exposes via API.
    # Strip only whitespace/control chars; do NOT slugify or lowercase.
    clean = re.sub(r"[\r\n\t]+", " ", topic).strip()
    # Cap at 220 chars — well within any PostgreSQL VARCHAR or TEXT limit.
    clean = clean[:220]
    label = _CATEGORY_LABELS.get(category, category.capitalize())
    return f"{label} {dt.isoformat()}: {clean}"


def build_document(
    content: str,
    category: str,
    source: str,
    topic: str = "",
    venture: Optional[str] = None,
    confidence: float = 0.8,
    summary_level: str = "extracted",
    tags: Optional[list] = None,
    session_id: Optional[str] = None,
    entity_refs: Optional[list] = None,
    dt: Optional[date] = None,
) -> dict:
    dt = dt or date.today()
    if not topic:
        topic = content[:60].replace("\n", " ")

    doc = {
        "title": generate_title(category, dt, topic),
        "content": content,
        "metadata": {
            "source": source if source in VALID_SOURCES else "cortex_extraction",
            "venture": venture,
            "category": category if category in VALID_CATEGORIES else "research",
            "confidence": max(0.0, min(1.0, confidence)),
            "temporal": datetime.now().isoformat(),
            "summary_level": summary_level if summary_level in VALID_SUMMARY_LEVELS else "extracted",
            "tags": tags or [],
            "session_id": session_id or "",
            "entity_refs": entity_refs or [],
        },
    }
    return doc


def validate_document(doc: dict) -> bool:
    if not isinstance(doc, dict):
        return False
    if "title" not in doc or "content" not in doc or "metadata" not in doc:
        return False
    meta = doc["metadata"]
    if not isinstance(meta, dict):
        return False
    required = ("source", "category", "confidence", "temporal", "summary_level")
    for key in required:
        if key not in meta:
            return False
    if meta["source"] not in VALID_SOURCES:
        return False
    if meta["category"] not in VALID_CATEGORIES:
        return False
    return True


async def classify_content(text: str, agent) -> dict:
    from python.helpers.cortex_model_router import CortexModelRouter

    system = (
        "You are a content classifier. Given text, return JSON with:\n"
        '{"category": one of (user_preference|business_fact|decision|research|outcome|conversation),\n'
        ' "venture": null or venture name if mentioned,\n'
        ' "tags": list of 2-5 relevant tags,\n'
        ' "topic": short 3-5 word topic slug,\n'
        ' "confidence": 0.0-1.0}\n'
        "Return ONLY valid JSON, no explanation."
    )
    try:
        response = await CortexModelRouter.call_routed_model(
            "classification", system, text[:2000], agent
        )
        from python.helpers.dirty_json import DirtyJson
        parsed = DirtyJson.parse_string(response)
        if isinstance(parsed, dict):
            return {
                "category": parsed.get("category", "research"),
                "venture": parsed.get("venture"),
                "tags": parsed.get("tags", []),
                "topic": parsed.get("topic", ""),
                "confidence": parsed.get("confidence", 0.7),
            }
    except Exception:
        pass
    return {"category": "research", "venture": None, "tags": [], "topic": "", "confidence": 0.5}
