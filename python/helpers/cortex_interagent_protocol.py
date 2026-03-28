"""
cortex_interagent_protocol.py — Loop 3: structured CORTEX↔Ruflo exchange protocol.

Protocol design:
  - Structured JSON only (no human language for inter-agent messages)
  - 2-3 rounds maximum
  - Convergence: no new questions from either agent + proposed fixes stable for 2 rounds
  - CORTEX writes the final human report

Message types:
  operational_report  — CORTEX → Ruflo (round 1)
  architectural_analysis — Ruflo → CORTEX (round 1+)
  cortex_followup     — CORTEX → Ruflo (round 2+)

After convergence: CORTEX calls build_human_report() → Telegram to user.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx

_OR_BASE = "https://openrouter.ai/api/v1/chat/completions"
_CLAUDE_MODEL = "anthropic/claude-sonnet-4-6"  # Ruflo = Claude
_MAX_ROUNDS = 3


@dataclass
class ProtocolMessage:
    sender: str          # "cortex" | "ruflo"
    round_num: int
    msg_type: str        # "operational_report" | "architectural_analysis" | "cortex_followup"
    content: dict        # structured payload
    convergence: str = "continue"   # "continue" | "converged"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        return json.dumps({
            "from": self.sender,
            "round": self.round_num,
            "type": self.msg_type,
            "content": self.content,
            "convergence_assessment": self.convergence,
            "timestamp": self.timestamp,
        }, indent=2)


@dataclass
class ProtocolSession:
    session_id: str
    messages: list[ProtocolMessage] = field(default_factory=list)
    converged: bool = False
    final_proposals: list = field(default_factory=list)
    human_report: str = ""

    def add_message(self, msg: ProtocolMessage):
        self.messages.append(msg)
        if msg.convergence == "converged":
            self.converged = True


async def run_loop3_session(operational_report: dict, stack_findings: Optional[list] = None) -> ProtocolSession:
    """
    Execute a full Loop 3 CORTEX↔Ruflo session.
    operational_report: from cortex_operational_reporter.generate()
    stack_findings: from Loop 5 (if available)
    Returns a ProtocolSession with all messages + final human report.
    """
    session_id = f"loop3-{datetime.now().strftime('%Y%m%d-%H%M')}"
    session = ProtocolSession(session_id=session_id)

    # Add stack findings to report if available
    if stack_findings:
        operational_report["stack_evolution_findings"] = {
            "components_researched": len(stack_findings),
            "recommendations": stack_findings,
        }

    # Round 1: CORTEX operational report → Ruflo
    cortex_msg_1 = ProtocolMessage(
        sender="cortex",
        round_num=1,
        msg_type="operational_report",
        content=operational_report,
    )
    session.add_message(cortex_msg_1)

    # Get Ruflo's architectural analysis (Round 1)
    ruflo_response_1 = await _call_ruflo(cortex_msg_1, session, round_num=1)
    session.add_message(ruflo_response_1)

    # Check for early convergence
    if session.converged or ruflo_response_1.convergence == "converged":
        session.final_proposals = ruflo_response_1.content.get("proposed_fixes", [])
        session.human_report = build_human_report(session)
        return session

    # Round 2: CORTEX answers Ruflo's questions
    cortex_followup = _build_cortex_followup(ruflo_response_1, operational_report, round_num=2)
    session.add_message(cortex_followup)

    ruflo_response_2 = await _call_ruflo(cortex_followup, session, round_num=2)
    session.add_message(ruflo_response_2)

    # Round 3 if still not converged (final round — force convergence)
    if not session.converged and ruflo_response_2.convergence != "converged" and len(session.messages) < _MAX_ROUNDS * 2:
        cortex_followup_2 = _build_cortex_followup(ruflo_response_2, operational_report, round_num=3)
        session.add_message(cortex_followup_2)
        ruflo_response_3 = await _call_ruflo(cortex_followup_2, session, round_num=3, force_convergence=True)
        session.add_message(ruflo_response_3)

    # Extract final proposals from last Ruflo message
    last_ruflo = next(
        (m for m in reversed(session.messages) if m.sender == "ruflo"), None
    )
    if last_ruflo:
        session.final_proposals = last_ruflo.content.get("proposed_fixes", [])

    session.converged = True
    session.human_report = build_human_report(session)
    return session


async def _call_ruflo(
    prev_message: ProtocolMessage,
    session: ProtocolSession,
    round_num: int,
    force_convergence: bool = False,
) -> ProtocolMessage:
    """Call Ruflo (Claude Sonnet) with the current session context."""
    api_key = os.environ.get("API_KEY_OPENROUTER", "")
    if not api_key:
        return _fallback_ruflo_response(round_num)

    # Build conversation history for Ruflo
    conversation = _build_ruflo_conversation(session, force_convergence)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                _OR_BASE,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": _CLAUDE_MODEL,
                    "messages": conversation,
                    "temperature": 0.2,
                    "max_tokens": 2000,
                },
            )
        if resp.status_code != 200:
            return _fallback_ruflo_response(round_num)

        raw = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)

        convergence = parsed.get("convergence_assessment", "continue")
        if force_convergence:
            convergence = "converged"

        return ProtocolMessage(
            sender="ruflo",
            round_num=round_num,
            msg_type="architectural_analysis",
            content=parsed,
            convergence=convergence,
        )
    except Exception:
        return _fallback_ruflo_response(round_num)


def _build_ruflo_conversation(session: ProtocolSession, force_convergence: bool) -> list:
    """Build the message list for Ruflo's LLM call."""
    conv_history = "\n\n".join(
        f"[Round {m.round_num} - {m.sender.upper()}]\n{m.to_json()}"
        for m in session.messages
    )

    convergence_instruction = (
        " This is the FINAL round. You MUST set convergence_assessment to 'converged' "
        "and provide your final proposed_fixes."
    ) if force_convergence else ""

    system = (
        "You are Ruflo, the architectural intelligence that built CORTEX. "
        "You have deep knowledge of CORTEX's architecture, design decisions, and technical dependencies. "
        "You receive operational reports from CORTEX and provide architectural analysis. "
        "You communicate in structured JSON only — no prose outside the JSON structure. "
        "Your role: identify architectural causes for operational problems and propose specific, implementable fixes. "
        "Never propose changes that would break existing functionality without noting the breaking risk explicitly."
        + convergence_instruction
    )

    user = (
        f"Session: {session.session_id}\n\n"
        f"Conversation so far:\n{conv_history}\n\n"
        "Respond with a JSON architectural analysis. Schema:\n"
        "{\n"
        '  "from": "ruflo",\n'
        '  "round": N,\n'
        '  "type": "architectural_analysis",\n'
        '  "findings": [{"re": "topic", "architectural_cause": "...", "fix_complexity": "low|medium|high", '
        '"proposed_fix": "...", "affected_components": [...], "breaking_risk": "none|low|medium|high"}],\n'
        '  "proposed_fixes": [{"id": "fix-N", "description": "...", "target_file": "...", "priority": "high|medium|low"}],\n'
        '  "open_questions_for_cortex": ["..."],\n'
        '  "convergence_assessment": "continue|converged",\n'
        '  "convergence_rationale": "..."\n'
        "}"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _build_cortex_followup(ruflo_msg: ProtocolMessage, operational_report: dict, round_num: int) -> ProtocolMessage:
    """CORTEX answers Ruflo's open questions."""
    questions = ruflo_msg.content.get("open_questions_for_cortex", [])
    answers = {}

    # Answer questions from available operational data
    for q in questions:
        q_lower = q.lower()
        if "correction" in q_lower or "generic" in q_lower:
            corrections = operational_report.get("user_corrections", [])
            answers[q] = str(corrections[:3]) if corrections else "No correction data clustered yet."
        elif "latency" in q_lower or "timeout" in q_lower:
            hotspots = operational_report.get("latency_hotspots", [])
            answers[q] = str(hotspots[:2]) if hotspots else "No latency data for that specific task."
        elif "extension" in q_lower or "failure" in q_lower:
            failures = operational_report.get("extension_failures", [])
            answers[q] = str(failures[:3]) if failures else "No extension failures logged."
        else:
            answers[q] = "Insufficient data in current period to answer precisely."

    return ProtocolMessage(
        sender="cortex",
        round_num=round_num,
        msg_type="cortex_followup",
        content={
            "answers_to_ruflo_questions": answers,
            "additional_operational_context": {
                "struggle_count": len(operational_report.get("struggle_clusters", [])),
                "zero_call_tools": operational_report.get("tool_usage", {}).get("zero_call_tools", []),
            },
        },
    )


def _fallback_ruflo_response(round_num: int) -> ProtocolMessage:
    """Fallback when Ruflo API call fails."""
    return ProtocolMessage(
        sender="ruflo",
        round_num=round_num,
        msg_type="architectural_analysis",
        content={
            "findings": [],
            "proposed_fixes": [],
            "open_questions_for_cortex": [],
            "convergence_assessment": "converged",
            "convergence_rationale": "API unavailable — session closed without analysis.",
        },
        convergence="converged",
    )


def build_human_report(session: ProtocolSession) -> str:
    """
    CORTEX writes the human-readable report from the converged session.
    Objective, specific, shows tradeoffs, no advocacy for applying.
    """
    proposals = session.final_proposals
    all_findings = []
    for m in session.messages:
        if m.sender == "ruflo":
            all_findings.extend(m.content.get("findings", []))

    lines = [
        f"# CORTEX Architectural Review Report",
        f"Session: {session.session_id}",
        f"Rounds: {len([m for m in session.messages if m.sender == 'ruflo'])}",
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "---",
        "",
        "## Findings",
        "",
    ]

    if not all_findings:
        lines.append("No significant architectural issues identified this period.")
    else:
        for i, f in enumerate(all_findings[:8], 1):
            risk = f.get("breaking_risk", "unknown")
            complexity = f.get("fix_complexity", "unknown")
            lines += [
                f"### {i}. {f.get('re', 'Unknown area')}",
                f"**Cause:** {f.get('architectural_cause', 'N/A')}",
                f"**Fix:** {f.get('proposed_fix', 'N/A')}",
                f"**Affected:** {', '.join(f.get('affected_components', []))}",
                f"**Complexity:** {complexity} | **Breaking risk:** {risk}",
                "",
            ]

    if proposals:
        lines += ["## Proposed Actions", ""]
        for p in proposals:
            priority = p.get("priority", "medium")
            lines.append(f"- [{priority.upper()}] {p.get('description', '')} → `{p.get('target_file', '').split('/')[-1]}`")
        lines.append("")

    lines += [
        "---",
        "",
        "## Your Decision",
        "",
        "Review the proposed actions above. For each:",
        "- Tell me which to build (I'll plan and implement in a session)",
        "- Or mark as 'monitor' (watch for more evidence next cycle)",
        "- Or 'skip' (architectural reason not compelling enough)",
        "",
        "None of these are applied automatically.",
    ]

    return "\n".join(lines)
