from python.helpers.extension import Extension
from python.helpers.memory import Memory
from python.helpers import errors
from agent import LoopData


_SIMILARITY_THRESHOLD = 0.55
_RESULT_LIMIT = 10
_MIN_MESSAGE_LENGTH = 20  # skip trivial messages shorter than this

# Exact-match trivial phrases that never warrant memory recall
_TRIVIAL_PHRASES = frozenset({
    "hi", "hello", "hey", "ok", "okay", "sure", "yes", "no", "thanks",
    "thank you", "got it", "great", "good", "nice", "cool", "perfect",
    "continue", "go on", "proceed", "next", "done", "stop", "bye",
})


class CortexTemporalMemory(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        agent = self.agent
        if not agent or not agent.config:
            return

        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        try:
            user_message = (
                loop_data.user_message.output_text() if loop_data.user_message else ""
            )
            if not user_message or len(user_message) < 3:
                return

            # Skip trivial one-word/short acknowledgements
            stripped = user_message.strip().lower().rstrip(".,!?")
            if len(stripped) < _MIN_MESSAGE_LENGTH and stripped in _TRIVIAL_PHRASES:
                return

            db = await Memory.get(agent)
            context_items = await db.search_similarity_threshold(
                query=user_message,
                limit=_RESULT_LIMIT,
                threshold=_SIMILARITY_THRESHOLD,
                filter=f"area == '{Memory.Area.FRAGMENTS.value}'",
            )

            if not context_items:
                return

            texts = [doc.page_content for doc in context_items]
            context_txt = "\n".join(texts)
            loop_data.extras_persistent["cortex_knowledge"] = (
                f"## CORTEX Knowledge Context\n{context_txt}"
            )

        except Exception as e:
            err = errors.format_error(e)
            agent.context.log.log(
                type="warning",
                heading="CORTEX temporal memory error",
                content=err,
            )
