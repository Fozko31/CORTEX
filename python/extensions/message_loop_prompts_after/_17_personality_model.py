from python.helpers.extension import Extension
from python.helpers import errors
from agent import LoopData


# Keywords used to classify task type for adaptive challenge_level.
# First match wins — order matters (more specific first).
_TASK_CLASSIFIERS = [
    ("direct", [
        "what is", "what's", "how much", "how many", "when did", "who is",
        "define ", "convert ", "calculate ", "format ", "summarize ",
        "what did we", "what was", "capital of", "translate ",
    ]),
    ("research", [
        "research ", "find out", "look up", "search for", "investigate",
        "what are the latest", "current state of", "market for", "trend",
        "competitors", "landscape", "news about", "what do people",
    ]),
    ("creative", [
        "brainstorm", "ideas for", "suggest ", "generate ideas", "come up with",
        "write a ", "draft a ", "create a ", "design a ",
    ]),
    ("review", [
        "review this", "what do you think", "is this good", "check this",
        "feedback on", "evaluate ", "assess ", "critique ",
    ]),
    ("strategic", [
        "should i", "should we", "plan ", "strategy", "roadmap", "launch",
        "invest ", "hire ", "partner ", "pricing", "decision", "choose",
        "recommend", "next steps", "how to grow", "how to scale",
    ]),
]


def _classify_task(message: str) -> str:
    """Classify a user message into a task type for adaptive challenge_level."""
    lower = message.lower()
    for task_type, keywords in _TASK_CLASSIFIERS:
        for kw in keywords:
            if kw in lower:
                return task_type
    return "strategic"  # default: full challenge mode


class CortexPersonalityInjection(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        agent = self.agent
        if not agent or not agent.config:
            return

        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        try:
            from python.helpers.cortex_personality_model import (
                PersonalityModel,
                get_adaptive_challenge_level,
            )
            from python.helpers.cortex_commitment_tracker import CommitmentTracker

            model = PersonalityModel.load(agent)
            personality_txt = model.format_for_prompt()
            agent.set_data("cortex_personality_model", personality_txt)
            loop_data.extras_persistent["cortex_personality"] = (
                f"## User Personality Model\n{personality_txt}"
            )

            # Inject adaptive challenge_level based on task type
            user_message = (
                loop_data.user_message.output_text() if loop_data.user_message else ""
            )
            if user_message:
                task_type = _classify_task(user_message)
                base = model.dimensions.get("challenge_level", 4.0)
                effective = get_adaptive_challenge_level(task_type, base)
                loop_data.extras_persistent["cortex_challenge_override"] = (
                    f"## Effective Challenge Level\n"
                    f"Task type: {task_type} → challenge_level: {effective:.1f}/5.0\n"
                    f"{'Deliver first, challenge after if needed.' if task_type in ('direct', 'research') else 'Full challenge mode — flag flaws before assisting.'}"
                )

            tracker = CommitmentTracker.load(agent)
            active = tracker.get_active()
            if active:
                commitments_txt = tracker.format_for_prompt()
                agent.set_data("cortex_active_commitments", commitments_txt)
                loop_data.extras_persistent["cortex_commitments"] = (
                    f"## Active Commitments\n{commitments_txt}"
                )

        except Exception as e:
            err = errors.format_error(e)
            agent.context.log.log(
                type="warning",
                heading="CORTEX personality injection error",
                content=err,
            )
