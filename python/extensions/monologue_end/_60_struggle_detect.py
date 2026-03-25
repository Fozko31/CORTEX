import re
from python.helpers.extension import Extension
from agent import LoopData


HEDGING_PATTERNS = [
    r"\bi'?m not sure\b",
    r"\bi think\b",
    r"\bit might be\b",
    r"\bi believe\b",
    r"\bpossibly\b",
    r"\bperhaps\b",
    r"\bi'?m uncertain\b",
    r"\bi don'?t know\b",
    r"\bnot entirely clear\b",
    r"\bhard to say\b",
]

COMPILED_HEDGING = [re.compile(p, re.IGNORECASE) for p in HEDGING_PATTERNS]


class CortexStruggleDetect(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs) -> None:
        agent = self.agent
        profile = getattr(agent.config, "profile", "") or ""
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        try:
            response_text = ""
            if agent.history:
                last = agent.history[-1]
                response_text = last.output_text() if hasattr(last, "output_text") else str(last)

            if not response_text.strip():
                return

            struggle_signals = []

            hedging_count = sum(1 for p in COMPILED_HEDGING if p.search(response_text))
            if hedging_count >= 3:
                struggle_signals.append(f"high_hedging ({hedging_count} phrases)")

            user_msg = ""
            if loop_data.user_message:
                user_msg = loop_data.user_message.output_text()

            if user_msg and len(user_msg) > 100 and len(response_text) < 80:
                struggle_signals.append("short_response_to_complex_question")

            if not struggle_signals:
                return

            from python.helpers.cortex_self_model import CortexSelfModel
            self_model = CortexSelfModel.load(agent)

            topic = _extract_topic(user_msg) if user_msg else "unknown"
            severity = "high" if len(struggle_signals) > 1 else "medium"

            self_model.add_knowledge_gap(topic, severity)

            for signal in struggle_signals:
                self_model.add_learning(f"Struggle signal: {signal} on topic: {topic}", False)

            self_model.save(agent)

            agent.set_data("cortex_last_struggle", {
                "topic": topic,
                "signals": struggle_signals,
                "severity": severity,
            })

            await _offer_help(agent, topic, struggle_signals, loop_data)

        except Exception:
            pass


async def _offer_help(agent, topic: str, signals: list, loop_data: LoopData):
    try:
        from python.helpers.cortex_model_router import CortexModelRouter
        if not CortexModelRouter.is_within_budget(agent):
            return

        system = (
            "CORTEX just expressed uncertainty. Topic: " + topic + "\n"
            "Signals: " + ", ".join(signals) + "\n"
            "Suggest 1-2 concrete next steps to resolve this uncertainty.\n"
            "Be brief (1-2 sentences max). Focus on: search SurfSense, ask user for clarification, "
            "or run targeted research. Do NOT suggest vague things."
        )

        suggestion = await CortexModelRouter.call_routed_model(
            task="classification",
            system=system,
            message=topic[:200],
            agent=agent,
        )

        if suggestion and suggestion.strip():
            agent.set_data("cortex_proactive_help", {
                "topic": topic,
                "suggestion": suggestion.strip(),
                "timestamp": __import__("datetime").datetime.now().isoformat(),
            })

            existing_help = loop_data.extras_persistent.get("cortex_consciousness", "")
            help_note = f"\n\n[CORTEX detected uncertainty on: {topic}]\nSuggested next steps: {suggestion.strip()}"
            loop_data.extras_persistent["cortex_consciousness"] = existing_help + help_note

    except Exception:
        pass


def _extract_topic(text: str) -> str:
    cleaned = text.strip()[:100]
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    words = cleaned.split()
    meaningful = [w for w in words if len(w) > 3]
    return " ".join(meaningful[:5]) if meaningful else "general"
