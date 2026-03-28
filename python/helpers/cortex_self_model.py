import json
import os
from datetime import datetime, date
from typing import Optional
from python.helpers.memory import get_agent_memory_subdir, abs_db_dir


DEFAULT_SELF_MODEL = {
    "capability_registry": {
        "tools": {
            "code_execution": {"confidence": 0.5, "last_used": None, "success_rate": None, "uses": 0},
            "web_search": {"confidence": 0.5, "last_used": None, "success_rate": None, "uses": 0},
            "file_operations": {"confidence": 0.5, "last_used": None, "success_rate": None, "uses": 0},
            "surfsense_search": {"confidence": 0.3, "last_used": None, "success_rate": None, "uses": 0},
            "knowledge_retrieval": {"confidence": 0.5, "last_used": None, "success_rate": None, "uses": 0},
        },
        "knowledge_domains": {},
    },
    "knowledge_map": {
        "total_faiss_entities": 0,
        "total_surfsense_documents": 0,
        "spaces_populated": [],
        "ventures_tracked": [],
        "last_session_topics": [],
    },
    "knowledge_gaps": [],
    "learning_trajectory": {
        "sessions_total": 0,
        "knowledge_growth_rate": 0.0,
        "personality_stability": 0.5,
        "trust_trend": "neutral",
    },
    "performance_history": {
        "approaches_that_worked": [],
        "approaches_that_failed": [],
        "calibration_score": 0.5,
    },
}


class CortexSelfModel:

    def __init__(self, data: dict):
        self.data = data

    @staticmethod
    def _data_path(agent) -> str:
        base = abs_db_dir(get_agent_memory_subdir(agent))
        return os.path.join(base, "cortex_self_model.json")

    @staticmethod
    def load(agent) -> "CortexSelfModel":
        try:
            path = CortexSelfModel._data_path(agent)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = _deep_merge(json.loads(json.dumps(DEFAULT_SELF_MODEL)), data)
                return CortexSelfModel(merged)
        except Exception:
            pass
        return CortexSelfModel(json.loads(json.dumps(DEFAULT_SELF_MODEL)))

    def save(self, agent):
        try:
            path = CortexSelfModel._data_path(agent)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def update_capability(self, tool: str, success: bool):
        tools = self.data.get("capability_registry", {}).get("tools", {})
        if tool not in tools:
            tools[tool] = {"confidence": 0.5, "last_used": None, "success_rate": None, "uses": 0}
        entry = tools[tool]
        entry["last_used"] = date.today().isoformat()
        uses = entry.get("uses", 0) + 1
        entry["uses"] = uses

        old_rate = entry.get("success_rate")
        if old_rate is None:
            entry["success_rate"] = 1.0 if success else 0.0
        else:
            entry["success_rate"] = round(old_rate + (1.0 if success else 0.0 - old_rate) / uses, 3)

        entry["confidence"] = round(min(0.99, max(0.1, entry["success_rate"] * 0.7 + 0.3)), 3)

    def update_knowledge_domain(self, domain: str, depth: str):
        domains = self.data.get("capability_registry", {}).get("knowledge_domains", {})
        domains[domain] = {"depth": depth, "last_updated": date.today().isoformat()}

    def update_knowledge_map(self, faiss_count: int = 0, surfsense_docs: int = 0,
                             spaces: list = None, ventures: list = None, topics: list = None):
        km = self.data.get("knowledge_map", {})
        if faiss_count > 0:
            km["total_faiss_entities"] = faiss_count
        if surfsense_docs > 0:
            km["total_surfsense_documents"] = surfsense_docs
        if spaces is not None:
            km["spaces_populated"] = spaces
        if ventures is not None:
            km["ventures_tracked"] = ventures
        if topics is not None:
            km["last_session_topics"] = topics
        self.data["knowledge_map"] = km

    def add_knowledge_gap(self, topic: str, severity: str = "medium"):
        gaps = self.data.get("knowledge_gaps", [])
        for g in gaps:
            if g.get("topic") == topic:
                return
        gaps.append({
            "topic": topic,
            "detected": date.today().isoformat(),
            "severity": severity,
        })
        self.data["knowledge_gaps"] = gaps[-20:]

    def resolve_knowledge_gap(self, topic: str):
        gaps = self.data.get("knowledge_gaps", [])
        self.data["knowledge_gaps"] = [g for g in gaps if g.get("topic") != topic]

    def add_learning(self, approach: str, worked: bool):
        ph = self.data.get("performance_history", {})
        key = "approaches_that_worked" if worked else "approaches_that_failed"
        entries = ph.get(key, [])
        if approach not in entries:
            entries.append(approach)
        ph[key] = entries[-15:]

    def increment_session(self):
        lt = self.data.get("learning_trajectory", {})
        lt["sessions_total"] = lt.get("sessions_total", 0) + 1

    def update_growth_rate(self, new_facts_this_session: int):
        lt = self.data.get("learning_trajectory", {})
        sessions = max(1, lt.get("sessions_total", 1))
        old_rate = lt.get("knowledge_growth_rate", 0.0)
        lt["knowledge_growth_rate"] = round(old_rate + (new_facts_this_session - old_rate) / sessions, 2)

    def get_confidence_for(self, domain: str) -> float:
        domains = self.data.get("capability_registry", {}).get("knowledge_domains", {})
        entry = domains.get(domain, {})
        depth = entry.get("depth", "")
        depth_map = {"expert": 0.9, "advanced": 0.8, "intermediate": 0.6, "growing": 0.4, "minimal": 0.2}
        return depth_map.get(depth, 0.3)

    def get_self_summary(self) -> str:
        parts = []
        lt = self.data.get("learning_trajectory", {})
        km = self.data.get("knowledge_map", {})
        gaps = self.data.get("knowledge_gaps", [])

        parts.append(f"Sessions: {lt.get('sessions_total', 0)} | "
                     f"FAISS entities: {km.get('total_faiss_entities', 0)} | "
                     f"SurfSense docs: {km.get('total_surfsense_documents', 0)}")

        spaces = km.get("spaces_populated", [])
        if spaces:
            parts.append(f"Active spaces: {', '.join(spaces)}")

        ventures = km.get("ventures_tracked", [])
        if ventures:
            parts.append(f"Ventures: {', '.join(ventures)}")

        if gaps:
            gap_texts = [f"{g['topic']} ({g['severity']})" for g in gaps[:5]]
            parts.append(f"Knowledge gaps: {'; '.join(gap_texts)}")

        domains = self.data.get("capability_registry", {}).get("knowledge_domains", {})
        if domains:
            dom_texts = [f"{k}: {v.get('depth', '?')}" for k, v in list(domains.items())[:5]]
            parts.append(f"Domain expertise: {', '.join(dom_texts)}")

        ph = self.data.get("performance_history", {})
        cal = ph.get("calibration_score", 0.5)
        parts.append(f"Calibration: {cal:.2f} | Trust trend: {lt.get('trust_trend', 'neutral')}")

        return "\n".join(parts)


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
