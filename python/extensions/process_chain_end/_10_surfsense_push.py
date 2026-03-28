import asyncio
from python.cortex.extension import Extension
from python.helpers.defer import DeferredTask, THREAD_BACKGROUND
from python.cortex.loop_data import LoopData
from python.cortex.state import CortexState


class CortexSurfSensePush(Extension):
    async def execute(self, **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        surfsense_url = getattr(agent.config, "cortex_surfsense_url", "") or ""
        if not surfsense_url:
            return

        exchange_count = 0
        if agent.history:
            exchange_count = len([m for m in agent.history if getattr(m, "role", "") == "user"])

        push_interval = getattr(agent.config, "cortex_push_interval_exchanges", 20) or 20
        last_push_at = CortexState.for_agent(agent).get("cortex_last_push_exchange") or 0

        # Push on interval only — not after every single message.
        # SurfSense is the long-term archival layer, not real-time.
        # Real-time knowledge goes to FAISS (L1) and Graphiti (L2) per-turn.
        is_interval_reached = (exchange_count - last_push_at) >= push_interval

        if not is_interval_reached:
            return

        if exchange_count < 2:
            return

        log_item = agent.context.log.log(  # H2: replace with CortexLogger when AZ UI removed
            type="util",
            heading="CORTEX SurfSense push",
            content="Summarizing session and pushing to consciousness layer...",
        )

        task = DeferredTask(thread_name=THREAD_BACKGROUND)
        task.start_task(_push_to_surfsense, agent, exchange_count, log_item)


async def _push_to_surfsense(agent, exchange_count, log_item):
    try:
        from python.helpers.cortex_model_router import CortexModelRouter
        if not CortexModelRouter.is_within_budget(agent):
            log_item.update(content="Daily cost limit reached, skipping SurfSense push.")
            return

        from python.helpers.cortex_session_summarizer import summarize_session, extract_outcomes, extract_knowledge
        summary_data = await summarize_session(agent)

        if not summary_data.get("summary"):
            log_item.update(content="No summary produced, skipping push.")
            return

        from python.helpers.cortex_ingestion_schema import build_document
        from python.helpers.cortex_surfsense_router import CortexSurfSenseRouter

        documents_to_push = []

        conv_doc = build_document(
            content=summary_data["summary"],
            category="conversation",
            source="cortex_extraction",
            topic=", ".join(summary_data.get("topics", [])[:8]) or "session summary",
            tags=summary_data.get("topics", []),
            session_id=summary_data.get("session_id", ""),
            confidence=0.9,
            summary_level="summarized",
        )
        documents_to_push.append(conv_doc)

        for outcome in extract_outcomes(summary_data):
            otype = outcome.get("type", "decision")
            category = "decision" if otype in ("decision", "commitment") else "outcome"
            doc = build_document(
                content=outcome.get("content", ""),
                category=category,
                source="cortex_extraction",
                topic=outcome.get("content", "")[:180],
                confidence=outcome.get("confidence", 0.8),
                tags=[otype],
                session_id=summary_data.get("session_id", ""),
                summary_level="extracted",
            )
            documents_to_push.append(doc)

        for item in extract_knowledge(summary_data):
            category = item.get("category", "research")
            if category not in ("user_preference", "business_fact", "decision", "research", "outcome"):
                category = "research"
            doc = build_document(
                content=item.get("fact", ""),
                category=category,
                source="cortex_extraction",
                topic=item.get("fact", "")[:180],
                confidence=0.75,
                summary_level="extracted",
            )
            documents_to_push.append(doc)

        from python.helpers.cortex_surfsense_client import CortexSurfSenseClient
        client = CortexSurfSenseClient.from_agent_config(agent)
        if not client:
            for doc in documents_to_push:
                spaces = CortexSurfSenseRouter.route_for_push(doc)
                for space in spaces:
                    CortexSurfSenseClient.enqueue(agent, space, doc)
            log_item.update(content=f"SurfSense not configured, queued {len(documents_to_push)} docs.")
            return

        try:
            is_healthy = await client.health_check()
            if not is_healthy:
                for doc in documents_to_push:
                    spaces = CortexSurfSenseRouter.route_for_push(doc)
                    for space in spaces:
                        CortexSurfSenseClient.enqueue(agent, space, doc)
                log_item.update(content=f"SurfSense unreachable, queued {len(documents_to_push)} docs.")
                return

            from python.helpers.cortex_surfsense_router import CORE_SPACES
            await client.ensure_spaces_exist(CORE_SPACES)

            await client.drain_queue(agent)

            pushed = 0
            for doc in documents_to_push:
                spaces = CortexSurfSenseRouter.route_for_push(doc)
                for space in spaces:
                    try:
                        await client.push_document(space, doc)
                        CortexSurfSenseRouter.update_routing_index(agent, space, 1)
                        pushed += 1
                    except Exception:
                        CortexSurfSenseClient.enqueue(agent, space, doc)

            CortexState.for_agent(agent).set("cortex_last_push_exchange", exchange_count)

            try:
                from python.helpers.cortex_self_model import CortexSelfModel
                self_model = CortexSelfModel.load(agent)
                self_model.update_knowledge_map(
                    surfsense_docs=pushed,
                    topics=summary_data.get("topics", []),
                )
                knowledge_count = len(extract_knowledge(summary_data))
                self_model.update_growth_rate(knowledge_count)
                self_model.update_capability("surfsense_search", True)
                self_model.save(agent)
            except Exception:
                pass

            log_item.update(
                content=f"Pushed {pushed} documents to SurfSense. "
                        f"Session: {summary_data.get('summary', '')[:100]}..."
            )

        finally:
            await client.close()

    except Exception as e:
        from python.helpers import errors
        log_item.update(content=f"SurfSense push failed: {errors.format_error(e)}")
