import asyncio
import json
import os
import time
from datetime import datetime
from typing import Optional
from python.helpers.memory import get_agent_memory_subdir, abs_db_dir


class CortexProactiveEngine:

    STATE_FILE = "cortex_proactive_state.json"

    @staticmethod
    def _state_path(agent) -> str:
        base = abs_db_dir(get_agent_memory_subdir(agent))
        return os.path.join(base, CortexProactiveEngine.STATE_FILE)

    @staticmethod
    def load_state(agent) -> dict:
        path = CortexProactiveEngine._state_path(agent)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {
            "last_pulse": 0.0,
            "last_findings": [],
            "total_pulses": 0,
            "total_cost": 0.0,
        }

    @staticmethod
    def save_state(agent, state: dict):
        path = CortexProactiveEngine._state_path(agent)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def is_enabled(agent) -> bool:
        return bool(getattr(agent.config, "cortex_proactive_enabled", False))

    @staticmethod
    def get_pulse_interval(agent) -> int:
        return int(getattr(agent.config, "cortex_proactive_interval_minutes", 30) or 30) * 60

    @staticmethod
    def get_proactive_level(agent) -> str:
        return str(getattr(agent.config, "cortex_proactive_level", "minimal") or "minimal")

    @staticmethod
    def get_active_ventures(agent) -> list:
        try:
            from python.helpers.cortex_surfsense_router import CortexSurfSenseRouter
            routing_index = CortexSurfSenseRouter.load_routing_index(agent)
            ventures = []
            for name in routing_index.get("spaces", {}):
                if name.startswith("cortex_venture_"):
                    venture_name = name.replace("cortex_venture_", "")
                    ventures.append(venture_name)
            return ventures
        except Exception:
            return []


async def run_proactive_pulse(agent) -> dict:
    if not CortexProactiveEngine.is_enabled(agent):
        return {"status": "disabled", "findings": []}

    from python.helpers.cortex_model_router import CortexModelRouter
    if not CortexModelRouter.is_within_budget(agent):
        return {"status": "budget_exceeded", "findings": []}

    state = CortexProactiveEngine.load_state(agent)
    now = time.time()
    pulse_interval = CortexProactiveEngine.get_pulse_interval(agent)

    if (now - state.get("last_pulse", 0)) < pulse_interval:
        return {"status": "not_due", "findings": []}

    findings = []

    from python.helpers.cortex_surfsense_client import CortexSurfSenseClient
    client = CortexSurfSenseClient.from_agent_config(agent)
    if not client:
        return {"status": "no_client", "findings": []}

    try:
        is_healthy = await client.health_check()
        if not is_healthy:
            return {"status": "surfsense_unreachable", "findings": []}

        proactive_level = CortexProactiveEngine.get_proactive_level(agent)
        active_ventures = CortexProactiveEngine.get_active_ventures(agent)

        scan_spaces = list(active_ventures)
        scan_spaces += ["cortex_knowledge", "cortex_outcomes"]
        scan_spaces = list(dict.fromkeys(scan_spaces))

        for space_name in scan_spaces:
            try:
                venture_key = space_name if space_name.startswith("cortex_") else f"cortex_venture_{space_name}"

                tier0_candidates = await _tier0_scan(client, venture_key, state)

                if not tier0_candidates:
                    continue

                if proactive_level == "minimal":
                    for doc in tier0_candidates[:1]:
                        findings.append({
                            "venture": space_name,
                            "title": doc.title,
                            "summary": doc.content[:200],
                            "tier": 0,
                            "relevance": "new_content",
                        })
                    continue

                tier1_relevant = await _tier1_classify(tier0_candidates, space_name, agent)

                if not tier1_relevant:
                    continue

                if proactive_level in ("moderate", "aggressive"):
                    tier2_synthesis = await _tier2_synthesize(tier1_relevant, space_name, agent)
                    if tier2_synthesis:
                        findings.append({
                            "venture": space_name,
                            "title": f"Proactive insight: {space_name}",
                            "summary": tier2_synthesis,
                            "tier": 2,
                            "relevance": "high",
                        })
                else:
                    for doc in tier1_relevant[:2]:
                        findings.append({
                            "venture": space_name,
                            "title": doc.title,
                            "summary": doc.content[:300],
                            "tier": 1,
                            "relevance": "relevant",
                        })

            except Exception:
                continue

    finally:
        await client.close()

    state["last_pulse"] = now
    state["total_pulses"] = state.get("total_pulses", 0) + 1
    if findings:
        state["last_findings"] = [
            {"title": f["title"], "venture": f["venture"], "timestamp": datetime.now().isoformat()}
            for f in findings[-10:]
        ]
    CortexProactiveEngine.save_state(agent, state)

    if findings:
        _store_findings_for_ui(agent, findings)

    return {"status": "ok", "findings": findings, "spaces_scanned": len(scan_spaces)}


async def _tier0_scan(client, space_name: str, state: dict) -> list:
    last_pulse = state.get("last_pulse", 0)
    last_seen_ids = {f.get("title", "") for f in state.get("last_findings", [])}

    docs = await client.search(
        query="",
        space_names=[space_name],
        limit=10,
    )

    new_docs = [d for d in docs if d.title not in last_seen_ids]
    return new_docs


async def _tier1_classify(candidates: list, space_name: str, agent) -> list:
    if not candidates:
        return []

    from python.helpers.cortex_model_router import CortexModelRouter

    doc_list = "\n".join(f"- {d.title}: {d.content[:150]}" for d in candidates[:5])
    system = (
        f"You are evaluating documents from the '{space_name}' knowledge space.\n"
        "For each document, decide if it is relevant and actionable RIGHT NOW.\n"
        "Return a JSON list of relevant document titles only: [\"title1\", \"title2\"]\n"
        "Only include documents that have clear business value or require action.\n"
        "Return ONLY JSON."
    )

    try:
        response = await CortexModelRouter.call_routed_model(
            task="classification",
            system=system,
            message=doc_list,
            agent=agent,
        )
        from python.helpers.dirty_json import DirtyJson
        relevant_titles = DirtyJson.parse_string(response)
        if isinstance(relevant_titles, list):
            return [d for d in candidates if d.title in relevant_titles]
    except Exception:
        pass

    return candidates[:2]


async def _tier2_synthesize(docs: list, space_name: str, agent) -> str:
    if not docs:
        return ""

    from python.helpers.cortex_model_router import CortexModelRouter

    docs_text = "\n\n".join(f"### {d.title}\n{d.content[:500]}" for d in docs[:3])
    system = (
        f"You are CORTEX reviewing new knowledge in the '{space_name}' space.\n"
        "Synthesize these documents into a concise proactive insight (2-3 sentences).\n"
        "Focus on what is actionable, new, or requires attention.\n"
        "Be direct and specific."
    )

    try:
        return await CortexModelRouter.call_routed_model(
            task="summarization",
            system=system,
            message=docs_text,
            agent=agent,
        )
    except Exception:
        return ""


def _store_findings_for_ui(agent, findings: list):
    try:
        existing = agent.get_data("cortex_awareness_feed") or []
        timestamp = datetime.now().isoformat()
        new_entries = [
            {
                "timestamp": timestamp,
                "venture": f.get("venture", ""),
                "title": f.get("title", ""),
                "summary": f.get("summary", ""),
                "tier": f.get("tier", 0),
                "read": False,
            }
            for f in findings
        ]
        combined = new_entries + existing
        agent.set_data("cortex_awareness_feed", combined[:50])
    except Exception:
        pass


def register_proactive_task():
    try:
        from python.helpers.task_scheduler import TaskScheduler, ScheduledTask, TaskSchedule, TaskState

        scheduler = TaskScheduler.get()
        task_id = "cortex_proactive_pulse"

        existing = scheduler._tasks.get_task(task_id)
        if existing:
            return

        schedule = TaskSchedule(
            minute="*/30",
            hour="*",
            day="*",
            month="*",
            weekday="*",
            timezone="UTC",
        )

        task = ScheduledTask(
            id=task_id,
            name="CORTEX Proactive Pulse",
            schedule=schedule,
            system_prompt=(
                "You are CORTEX running a proactive background pulse. "
                "Check for new relevant content across active venture spaces. "
                "Surface actionable insights without being asked."
            ),
            prompt=(
                "Run the proactive pulse now: scan active venture spaces in SurfSense "
                "for new content, classify relevance, synthesize insights if relevant, "
                "and store findings for the awareness feed."
            ),
            state=TaskState.IDLE,
            agent_name="cortex",
        )

        scheduler._tasks.add_task(task)
    except Exception:
        pass
