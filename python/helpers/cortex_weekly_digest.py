import json
import os
from datetime import datetime
from typing import Optional
from python.helpers.memory import get_agent_memory_subdir, abs_db_dir


DIGEST_SYSTEM_PROMPT = """You are CORTEX's weekly digest generator. Your job is to:
1. Review the recent conversation summaries provided
2. Produce a concise weekly digest highlighting: key decisions, important facts learned, venture progress, user preference changes, and open action items
3. Identify cross-venture patterns if multiple ventures were discussed
4. Note any knowledge gaps or areas where CORTEX struggled

Output a structured summary suitable for long-term storage. Be concise but complete."""

DIGEST_USER_PROMPT_TEMPLATE = """Here are the recent session summaries from the past week:

{summaries}

Please produce:
1. A weekly digest summary (2-3 paragraphs)
2. Key decisions made this week
3. New knowledge acquired
4. Open action items or commitments
5. Cross-venture patterns (if any)
6. Suggested focus areas for next week"""


async def run_weekly_digest(agent):
    from python.helpers.cortex_surfsense_client import CortexSurfSenseClient
    from python.helpers.cortex_surfsense_router import CortexSurfSenseRouter
    from python.helpers.cortex_ingestion_schema import build_document
    from python.helpers.cortex_model_router import CortexModelRouter
    from python.helpers.cortex_self_model import CortexSelfModel

    client = CortexSurfSenseClient.from_agent_config(agent)
    if not client:
        return {"status": "error", "message": "SurfSense not configured"}

    try:
        is_healthy = await client.health_check()
        if not is_healthy:
            return {"status": "error", "message": "SurfSense unreachable"}

        recent_docs = await client.search(
            query="session summary conversation",
            space_names=["cortex_conversations"],
            limit=20,
        )

        if not recent_docs:
            return {"status": "skipped", "message": "No recent conversations to digest"}

        summaries_text = "\n\n---\n\n".join(
            f"**{doc.title}**\n{doc.content}" for doc in recent_docs
        )

        if len(summaries_text) > 10000:
            summaries_text = summaries_text[:10000] + "\n\n[...truncated...]"

        prompt = DIGEST_USER_PROMPT_TEMPLATE.format(summaries=summaries_text)
        digest_text = await CortexModelRouter.call_routed_model(
            "digest", DIGEST_SYSTEM_PROMPT, prompt, agent
        )

        if digest_text:
            digest_doc = build_document(
                content=digest_text,
                category="conversation",
                source="scheduler_digest",
                topic=f"weekly-digest-{datetime.now().strftime('%Y-W%W')}",
                confidence=0.9,
                summary_level="digest",
                tags=["weekly-digest", "consolidation"],
            )
            await client.push_document("cortex_weekly_digest", digest_doc)
            CortexSurfSenseRouter.update_routing_index(agent, "cortex_weekly_digest", 1)

        venture_spaces = []
        routing_index = CortexSurfSenseRouter.load_routing_index(agent)
        for name in routing_index.get("spaces", {}):
            if name.startswith("cortex_venture_"):
                venture_spaces.append(name)

        if len(venture_spaces) > 1:
            await _cross_venture_analysis(agent, client, venture_spaces)

        await _refresh_space_summaries(agent, client, routing_index)

        try:
            self_model = CortexSelfModel.load(agent)
            km = self_model.data.get("knowledge_map", {})
            populated = []
            for name, info in routing_index.get("spaces", {}).items():
                if info.get("doc_count", 0) > 0:
                    populated.append(name)
            self_model.update_knowledge_map(spaces=populated)
            self_model.save(agent)
        except Exception:
            pass

        return {"status": "success", "message": f"Weekly digest generated, {len(recent_docs)} sessions processed"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        await client.close()


async def _cross_venture_analysis(agent, client, venture_spaces):
    from python.helpers.cortex_model_router import CortexModelRouter
    from python.helpers.cortex_ingestion_schema import build_document
    from python.helpers.cortex_surfsense_router import CortexSurfSenseRouter

    venture_summaries = []
    for space in venture_spaces:
        try:
            docs = await client.search("progress results decisions", [space], limit=5)
            if docs:
                venture_name = space.replace("cortex_venture_", "")
                text = "\n".join(f"- {d.title}: {d.content[:200]}" for d in docs)
                venture_summaries.append(f"## {venture_name}\n{text}")
        except Exception:
            pass

    if len(venture_summaries) < 2:
        return

    system = (
        "Analyze patterns across these ventures. Identify:\n"
        "1. Common strategies or approaches\n"
        "2. Lessons from one venture applicable to others\n"
        "3. Resource allocation patterns\n"
        "4. Risk correlations\n"
        "Be concise and actionable."
    )
    combined = "\n\n".join(venture_summaries)
    try:
        analysis = await CortexModelRouter.call_routed_model(
            "digest", system, combined[:8000], agent
        )
        if analysis:
            doc = build_document(
                content=analysis,
                category="research",
                source="scheduler_digest",
                topic="cross-venture-analysis",
                confidence=0.8,
                summary_level="digest",
                tags=["cross-venture", "pattern-analysis"],
            )
            await client.push_document("cortex_cross_venture", doc)
            CortexSurfSenseRouter.update_routing_index(agent, "cortex_cross_venture", 1)
    except Exception:
        pass


async def _refresh_space_summaries(agent, client, routing_index):
    from python.helpers.cortex_surfsense_router import CortexSurfSenseRouter

    try:
        spaces = await client.list_spaces()
        for s in spaces:
            name = s.get("name", "")
            if name.startswith("cortex_"):
                if name in routing_index.get("spaces", {}):
                    pass
                else:
                    routing_index["spaces"][name] = {
                        "description": s.get("description", ""),
                        "search_when": [],
                        "doc_count": 0,
                        "last_updated": None,
                    }

        routing_index["last_refreshed"] = datetime.now().isoformat()
        CortexSurfSenseRouter.save_routing_index(agent, routing_index)
    except Exception:
        pass


def register_weekly_digest_task():
    try:
        from python.helpers.task_scheduler import TaskScheduler, ScheduledTask, TaskSchedule, TaskState

        scheduler = TaskScheduler.get()
        task_id = "cortex_weekly_digest"

        existing = scheduler._tasks.get_task(task_id)
        if existing:
            return

        schedule = TaskSchedule(
            minute="0",
            hour="3",
            day="*",
            month="*",
            weekday="1",
            timezone="UTC",
        )

        task = ScheduledTask(
            id=task_id,
            name="CORTEX Weekly Digest",
            schedule=schedule,
            system_prompt=DIGEST_SYSTEM_PROMPT,
            prompt="Run the weekly digest consolidation now. Summarize recent conversations, refresh indices, and analyze cross-venture patterns.",
            state=TaskState.IDLE,
            agent_name="cortex",
        )

        scheduler._tasks.add_task(task)
    except Exception:
        pass
