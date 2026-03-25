from dataclasses import dataclass, field
from typing import Optional
from python.helpers.dirty_json import DirtyJson


@dataclass
class Entity:
    name: str
    entity_type: str
    description: str = ""


@dataclass
class Fact:
    subject: str
    predicate: str
    object: str


@dataclass
class CommitmentItem:
    text: str
    due_date: Optional[str]
    commitment_type: str


@dataclass
class ExtractionResult:
    entities: list[Entity] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    commitments: list[CommitmentItem] = field(default_factory=list)
    user_prefs: dict = field(default_factory=dict)


_SYSTEM = """You are a precise knowledge extraction engine for CORTEX, an AI business partner.

Analyze the conversation and extract structured knowledge. Return ONLY valid JSON with this exact structure:
{
  "entities": [{"name": "...", "entity_type": "person|company|product|place|concept", "description": "..."}],
  "facts": [{"subject": "...", "predicate": "...", "object": "..."}],
  "commitments": [{"text": "...", "due_date": "YYYY-MM-DD or null", "commitment_type": "promise|task|reminder"}],
  "user_prefs": {"verbosity": "concise|verbose", "formality": "casual|formal", "format": "prose|structured"}
}

Rules:
- entities: named people, companies, ventures, products, places mentioned with business relevance
- facts: concrete statements about the user, their business, preferences, constraints
- commitments: things CORTEX explicitly promised or agreed to do ("I will...", "Let me...", "I'll...")
- user_prefs: only if clearly expressed by user behavior or direct statement
- Return empty arrays/objects if nothing relevant found
- Return ONLY JSON, no explanation, no markdown fences"""


class CortexKnowledgeExtractor:

    @staticmethod
    async def extract(agent, conversation_text: str) -> ExtractionResult:
        result = ExtractionResult()
        try:
            raw = await agent.call_utility_model(
                system=_SYSTEM,
                message=f"Conversation:\n\n{conversation_text}",
                background=True,
            )
            if not raw:
                return result

            parsed = DirtyJson.parse_string(raw.strip())
            if not isinstance(parsed, dict):
                return result

            for e in parsed.get("entities") or []:
                if isinstance(e, dict) and e.get("name"):
                    result.entities.append(Entity(
                        name=str(e["name"]),
                        entity_type=str(e.get("entity_type", "concept")),
                        description=str(e.get("description", "")),
                    ))

            for f in parsed.get("facts") or []:
                if isinstance(f, dict) and f.get("subject"):
                    result.facts.append(Fact(
                        subject=str(f["subject"]),
                        predicate=str(f.get("predicate", "")),
                        object=str(f.get("object", "")),
                    ))

            for c in parsed.get("commitments") or []:
                if isinstance(c, dict) and c.get("text"):
                    result.commitments.append(CommitmentItem(
                        text=str(c["text"]),
                        due_date=c.get("due_date") or None,
                        commitment_type=str(c.get("commitment_type", "promise")),
                    ))

            prefs = parsed.get("user_prefs") or {}
            if isinstance(prefs, dict):
                result.user_prefs = prefs

        except Exception:
            pass

        return result
