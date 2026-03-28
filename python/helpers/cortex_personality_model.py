import json
import os
from datetime import datetime
from python.cortex.memory import get_agent_memory_subdir, abs_db_dir


_FILE = "cortex_personality.json"
_OBSERVATIONS_MAX = 50

DIMENSIONS = {
    "verbosity": (1, 5, "concise", "verbose"),
    "formality": (1, 5, "casual", "formal"),
    "challenge_level": (1, 5, "agreeable", "challenging"),
    "humor": (1, 5, "serious", "playful"),
    "format": (1, 5, "prose", "structured"),
    "trust": (1, 5, "skeptical", "trusting"),
}

_DEFAULTS = {
    "verbosity": 3.0,
    "formality": 3.0,
    "challenge_level": 4.0,
    "humor": 2.0,
    "format": 3.0,
    "trust": 3.0,
}

# Task-adaptive challenge_level overrides.
# Applies per-request based on query classification — does not mutate persisted state.
# Base challenge_level (4.0) is for strategic/proposal queries.
# Research/info requests get lower challenge — deliver first, challenge after.
_CHALLENGE_BY_TASK = {
    "direct": 2.0,       # Simple factual, math, conversions, memory retrieval → just deliver
    "research": 2.5,     # Research request → deliver findings, note framing issues after
    "creative": 3.0,     # Creative/brainstorm → balanced, some pushback
    "strategic": 4.0,    # Strategy/planning/proposals → full challenge mode
    "review": 4.0,       # Reviewing an idea/plan → full challenge mode
}


def get_adaptive_challenge_level(task_type: str, base: float = 4.0) -> float:
    """Return the appropriate challenge_level for a given task type.
    Falls back to base if task_type is unknown.
    """
    return _CHALLENGE_BY_TASK.get(task_type.lower(), base)

_PREF_MAP = {
    "verbose": ("verbosity", 4.0),
    "concise": ("verbosity", 2.0),
    "brief": ("verbosity", 2.0),
    "detailed": ("verbosity", 4.5),
    "formal": ("formality", 4.0),
    "casual": ("formality", 2.0),
    "structured": ("format", 4.0),
    "prose": ("format", 2.0),
    "table": ("format", 4.5),
    "bullet": ("format", 4.0),
}

# Arbitrary string preferences (stored separately from float dimensions).
# Key: preference name, Value: allowed values + default.
# Extended by Phase F: TTS routing, comprehension check mode.
_STRING_PREF_DEFAULTS: dict[str, str] = {
    "tts_language_pref": "match_input",    # "force_sl" | "force_en" | "match_input"
    "comprehension_mode": "compact",        # "compact" | "detailed" | "off"
}


class PersonalityModel:

    def __init__(
        self,
        dimensions: dict | None = None,
        observations: list | None = None,
        preferences: dict | None = None,
    ):
        self.dimensions: dict[str, float] = dict(_DEFAULTS)
        if dimensions:
            for k, v in dimensions.items():
                if k in self.dimensions:
                    self.dimensions[k] = max(1.0, min(5.0, float(v)))
        self.observations: list[str] = list(observations or [])[-_OBSERVATIONS_MAX:]
        # Arbitrary string preferences (TTS routing, comprehension mode, etc.)
        self.preferences: dict[str, str] = dict(_STRING_PREF_DEFAULTS)
        if preferences:
            self.preferences.update(preferences)

    def update_from_prefs(self, prefs: dict, nudge_weight: float = 0.25) -> None:
        for _key, val in prefs.items():
            for pref_word, (dim, target) in _PREF_MAP.items():
                if pref_word in str(val).lower():
                    self._nudge(dim, target, nudge_weight)

    def _nudge(self, dimension: str, toward: float, weight: float = 0.25) -> None:
        current = self.dimensions.get(dimension, 3.0)
        self.dimensions[dimension] = round(current + (toward - current) * weight, 2)

    def get_preference(self, key: str, default: str = "") -> str:
        """Read a string preference (e.g. 'tts_language_pref')."""
        return self.preferences.get(key, _STRING_PREF_DEFAULTS.get(key, default))

    def set_preference(self, key: str, value: str) -> None:
        """Persist a string preference."""
        self.preferences[key] = value

    def add_observation(self, text: str) -> None:
        self.observations.append(text)
        if len(self.observations) > _OBSERVATIONS_MAX:
            self.observations = self.observations[-_OBSERVATIONS_MAX:]

    def format_for_prompt(self) -> str:
        lines = ["User personality model (scale 1–5):"]
        for dim, (_lo, _hi, low_label, high_label) in DIMENSIONS.items():
            score = self.dimensions.get(dim, 3.0)
            filled = "●" * round(score)
            empty = "○" * (5 - round(score))
            lines.append(
                f"  {dim:<17} [{filled}{empty}] {score:.1f}  ({low_label} ← → {high_label})"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "dimensions": self.dimensions,
            "observations": self.observations,
            "preferences": self.preferences,
            "updated": datetime.now().isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PersonalityModel":
        return cls(
            dimensions=data.get("dimensions"),
            observations=data.get("observations"),
            preferences=data.get("preferences"),
        )

    @staticmethod
    def _data_path(agent) -> str:
        memory_dir = abs_db_dir(get_agent_memory_subdir(agent))
        return os.path.join(memory_dir, _FILE)

    @staticmethod
    def load(agent) -> "PersonalityModel":
        try:
            path = PersonalityModel._data_path(agent)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return PersonalityModel.from_dict(json.load(f))
        except Exception:
            pass
        return PersonalityModel()

    def save(self, agent) -> None:
        try:
            path = PersonalityModel._data_path(agent)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
        except Exception:
            pass
