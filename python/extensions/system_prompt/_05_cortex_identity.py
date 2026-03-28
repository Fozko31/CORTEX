from python.cortex.extension import Extension
from python.cortex.state import CortexState
from python.cortex.config import CortexConfig


class CortexIdentity(Extension):

    async def execute(self, system_prompt: list[str], loop_data, **kwargs):
        agent = self.agent
        if not agent:
            return

        profile = ""
        if agent.config:
            profile = CortexConfig.from_agent_config(agent.config).profile
        if not profile.startswith("cortex") and not profile.startswith("venture_"):
            return

        self._ensure_data_loaded(agent)

        sections = []

        venture_summary = CortexState.for_agent(agent).get("cortex_venture_summary")
        if venture_summary:
            sections.append("## Active Ventures")
            sections.append(venture_summary)
            sections.append("")

        trust_data = CortexState.for_agent(agent).get("cortex_trust_levels")
        if trust_data:
            sections.append("## Authority & Trust")
            sections.append(trust_data)
            sections.append("")

        commitments = CortexState.for_agent(agent).get("cortex_active_commitments")
        if commitments and commitments != "No active commitments.":
            sections.append("## Active Commitments")
            sections.append(commitments)
            sections.append("")

        personality = CortexState.for_agent(agent).get("cortex_personality_model")
        if personality:
            sections.append("## User Personality Model")
            sections.append(personality)
            sections.append("")

        self_summary = CortexState.for_agent(agent).get("cortex_self_summary")
        if self_summary:
            sections.append("## CORTEX Self-Awareness")
            sections.append(self_summary)
            sections.append("")

        if sections:
            header = "# CORTEX Active Context\n\n" + "\n".join(sections)
            system_prompt.insert(0, header)

    def _ensure_data_loaded(self, agent) -> None:
        if not CortexState.for_agent(agent).get("cortex_trust_levels"):
            try:
                from python.helpers.cortex_trust_engine import TrustEngine
                engine = TrustEngine.load(agent)
                CortexState.for_agent(agent).set("cortex_trust_levels", engine.format_for_prompt())
            except Exception:
                pass

        if not CortexState.for_agent(agent).get("cortex_personality_model"):
            try:
                from python.helpers.cortex_personality_model import PersonalityModel
                model = PersonalityModel.load(agent)
                CortexState.for_agent(agent).set("cortex_personality_model", model.format_for_prompt())
            except Exception:
                pass

        if not CortexState.for_agent(agent).get("cortex_active_commitments"):
            try:
                from python.helpers.cortex_commitment_tracker import CommitmentTracker
                tracker = CommitmentTracker.load(agent)
                active = tracker.get_active()
                if active:
                    CortexState.for_agent(agent).set("cortex_active_commitments", tracker.format_for_prompt())
            except Exception:
                pass

        if not CortexState.for_agent(agent).get("cortex_self_summary"):
            try:
                from python.helpers.cortex_self_model import CortexSelfModel
                self_model = CortexSelfModel.load(agent)
                summary = self_model.get_self_summary()
                if summary:
                    CortexState.for_agent(agent).set("cortex_self_summary", summary)
            except Exception:
                pass
