from python.helpers.extension import Extension
from python.helpers.memory import Memory
from python.helpers import errors
from python.helpers.defer import DeferredTask, THREAD_BACKGROUND
from agent import LoopData


class CortexKnowledgeExtraction(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        agent = self.agent
        if not agent or not agent.config:
            return

        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        log_item = agent.context.log.log(
            type="util",
            heading="Extracting CORTEX knowledge...",
        )

        task = DeferredTask(thread_name=THREAD_BACKGROUND)
        task.start_task(self._extract, loop_data, log_item)
        return task

    async def _extract(self, loop_data: LoopData, log_item, **kwargs):
        try:
            from python.helpers.cortex_knowledge_extractor import CortexKnowledgeExtractor
            from python.helpers.cortex_personality_model import PersonalityModel
            from python.helpers.cortex_commitment_tracker import CommitmentTracker

            agent = self.agent
            msgs_text = agent.concat_messages(agent.history)
            result = await CortexKnowledgeExtractor.extract(agent, msgs_text)

            db = await Memory.get(agent)
            stored = 0

            for entity in result.entities:
                text = f"ENTITY: {entity.name} ({entity.entity_type})\n{entity.description}"
                await db.insert_text(
                    text=text,
                    metadata={
                        "area": Memory.Area.FRAGMENTS.value,
                        "cortex_type": "entity",
                    },
                )
                stored += 1

            for fact in result.facts:
                text = f"FACT: {fact.subject} {fact.predicate} {fact.object}"
                await db.insert_text(
                    text=text,
                    metadata={
                        "area": Memory.Area.FRAGMENTS.value,
                        "cortex_type": "fact",
                    },
                )
                stored += 1

            if result.commitments:
                tracker = CommitmentTracker.load(agent)
                for c in result.commitments:
                    tracker.add(
                        text=c.text,
                        due_date=c.due_date,
                        commitment_type=c.commitment_type,
                    )
                tracker.save(agent)
                agent.set_data("cortex_active_commitments", tracker.format_for_prompt())

            if result.user_prefs:
                model = PersonalityModel.load(agent)
                model.update_from_prefs(result.user_prefs)
                model.save(agent)
                agent.set_data("cortex_personality_model", model.format_for_prompt())

            log_item.update(
                heading=(
                    f"CORTEX knowledge: {stored} items stored, "
                    f"{len(result.commitments)} commitment(s) detected"
                ),
            )

        except Exception as e:
            err = errors.format_error(e)
            self.agent.context.log.log(
                type="warning",
                heading="CORTEX knowledge extraction error",
                content=err,
            )
