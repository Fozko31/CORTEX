import json
import os
from datetime import datetime
from python.helpers.memory import get_agent_memory_subdir, abs_db_dir


TRUST_DOMAINS = ["research", "spending", "irreversible", "communication", "code", "scheduling"]

_DEFAULT = 0.65
_GROWTH = 0.05
_DECAY = 0.10
_FILE = "cortex_trust.json"


class TrustEngine:

    def __init__(self, scores: dict | None = None):
        self.scores: dict[str, float] = {d: _DEFAULT for d in TRUST_DOMAINS}
        if scores:
            for k, v in scores.items():
                if k in TRUST_DOMAINS:
                    self.scores[k] = max(0.0, min(1.0, float(v)))

    def get(self, domain: str) -> float:
        return self.scores.get(domain, _DEFAULT)

    def update(self, domain: str, success: bool, weight: float = 1.0) -> None:
        current = self.scores.get(domain, _DEFAULT)
        delta = (_GROWTH if success else -_DECAY) * weight
        self.scores[domain] = max(0.0, min(1.0, current + delta))

    def format_for_prompt(self) -> str:
        lines = ["Trust levels (0.0 = no autonomy → 1.0 = full autonomy):"]
        for domain in TRUST_DOMAINS:
            score = self.scores.get(domain, _DEFAULT)
            filled = "█" * int(score * 10)
            empty = "░" * (10 - int(score * 10))
            if score < 0.4:
                level = "low"
            elif score < 0.7:
                level = "medium"
            else:
                level = "high"
            lines.append(f"  {domain:<15} {filled}{empty} {score:.2f} ({level})")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"scores": self.scores, "updated": datetime.now().isoformat()}

    @classmethod
    def from_dict(cls, data: dict) -> "TrustEngine":
        return cls(scores=data.get("scores", {}))

    @staticmethod
    def _data_path(agent) -> str:
        memory_dir = abs_db_dir(get_agent_memory_subdir(agent))
        return os.path.join(memory_dir, _FILE)

    @staticmethod
    def load(agent) -> "TrustEngine":
        try:
            path = TrustEngine._data_path(agent)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return TrustEngine.from_dict(json.load(f))
        except Exception:
            pass
        return TrustEngine()

    def save(self, agent) -> None:
        try:
            path = TrustEngine._data_path(agent)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
        except Exception:
            pass
