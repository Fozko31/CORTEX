"""
_08_comprehension_check.py — Pre-action Comprehension Check
============================================================
Injects a comprehension check prompt before CORTEX begins work on
action-oriented requests. Catches wrong assumptions before any work starts.

Trigger: message contains one or more action verbs AND user is not
         asking a pure question (i.e., not just seeking information).

Modes (stored in PersonalityModel as "comprehension_mode"):
  compact  (default) — 4-line compact format injected into system prompt
  detailed           — full step-by-step breakdown format
  off                — comprehension check disabled

Compact format (the most valuable — catches wrong assumptions):
  Task:       [one-line restatement of what was asked]
  Constraint: [key constraints or limits mentioned]
  Assuming:   [what I'm assuming — THIS is the critical line]
  Action:     [what I will do first]

Detailed format (on "more" / "full breakdown"):
  Shows full Tier 2 Step-by-step protocol block.

User commands (handled in TelegramBotHandler, not here):
  "set comprehension to compact"   → saves "compact" to PersonalityModel
  "set comprehension to detailed"  → saves "detailed"
  "turn off comprehension check"   → saves "off"
  "more" / "full breakdown"        → one-time detailed mode for current request
"""

from python.cortex.extension import Extension
from python.helpers.print_style import PrintStyle

# Action verbs that trigger the comprehension check
_ACTION_VERBS = {
    "draft", "write", "create", "build", "make", "send", "email",
    "research", "find", "analyze", "analyse", "compare", "evaluate",
    "plan", "design", "implement", "set up", "configure",
    "update", "edit", "fix", "debug", "refactor",
    "schedule", "book", "arrange", "contact", "reach out",
    "buy", "purchase", "pay", "invoice",
    "launch", "deploy", "publish", "release",
    "review", "check", "audit", "test",
    # Slovenian action verbs
    "napiši", "ustvari", "pošlji", "najdi", "analiziraj",
    "primerjaj", "načrtuj", "nastavi", "posodobi", "popravi",
    "preveri", "kupi", "plačaj", "objavi", "sproži",
}

# Pure question words — if present alone, skip check
_QUESTION_ONLY_RE = None  # built lazily


class Extension(Extension):

    async def execute(self, agent=None, **kwargs):
        # Get the current user message
        message = _get_latest_user_message(agent)
        if not message:
            return

        # Check user's comprehension mode preference
        mode = _get_mode(agent)
        if mode == "off":
            return

        # Check if this is a "more" / detailed request
        if _is_more_request(message):
            _inject_detailed_format(agent, message)
            return

        # Only trigger for action-verb messages
        if not _has_action_verb(message):
            return

        # Skip pure questions ("What is X?", "How does Y work?")
        if _is_pure_question(message):
            return

        # Inject the check
        if mode == "detailed":
            _inject_detailed_format(agent, message)
        else:
            _inject_compact_format(agent, message)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_latest_user_message(agent) -> str:
    """Extract the most recent user message text."""
    try:
        history = agent.history if hasattr(agent, "history") else []
        for msg in reversed(history):
            role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
            if role == "user":
                content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else "")
                if isinstance(content, list):
                    # Multimodal content — find text part
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            return part.get("text", "")
                return str(content)
    except Exception:
        pass
    return ""


def _get_mode(agent) -> str:
    """Read comprehension mode from PersonalityModel."""
    try:
        from python.helpers.cortex_personality_model import PersonalityModel
        model = PersonalityModel.load(agent)
        return model.get_preference("comprehension_mode", default="compact")
    except Exception:
        return "compact"


def _has_action_verb(message: str) -> bool:
    words = set(message.lower().split())
    return bool(words & _ACTION_VERBS)


def _is_pure_question(message: str) -> bool:
    """Return True if the message is purely interrogative (no action implied)."""
    stripped = message.strip().rstrip("?").lower()
    # Short questions with no action verb — already filtered by _has_action_verb
    question_starters = (
        "what", "who", "when", "where", "which", "how", "why",
        "is", "are", "was", "were", "do", "does", "did",
        "can", "could", "would", "should", "shall",
        "kaj", "kdo", "kdaj", "kje", "kako", "zakaj", "ali",
    )
    first_word = stripped.split()[0] if stripped.split() else ""
    return first_word in question_starters and "?" in message


def _is_more_request(message: str) -> bool:
    """Detect 'more' / 'full breakdown' commands."""
    lowered = message.strip().lower()
    triggers = {"more", "full breakdown", "detailed", "show full", "give me more", "elaborate"}
    return any(t in lowered for t in triggers)


def _inject_compact_format(agent, message: str):
    """Inject compact 4-line comprehension check into agent's system message."""
    snippet = (
        "\n\n---\n"
        "**Before starting — Comprehension Check (compact)**\n"
        "Output this at the start of your response:\n\n"
        "```\n"
        "Task:       [one-line restatement of the request]\n"
        "Constraint: [key constraints, limits, or requirements mentioned]\n"
        "Assuming:   [what you're assuming — list any non-obvious assumptions]\n"
        "Action:     [what you will do first]\n"
        "```\n"
        "If any assumption is wrong, the user will correct it before you proceed.\n"
        "---\n"
    )
    _append_to_system(agent, snippet)


def _inject_detailed_format(agent, message: str):
    """Inject detailed step-by-step comprehension block."""
    snippet = (
        "\n\n---\n"
        "**Before starting — Full Comprehension Check**\n"
        "Output this at the start of your response:\n\n"
        "```\n"
        "Request:    [verbatim restatement of what was asked]\n"
        "Goal:       [the underlying outcome the user wants]\n"
        "Constraint: [all constraints, limits, quality bars mentioned]\n"
        "Assuming:   [list every non-obvious assumption you're making]\n"
        "Risks:      [what could go wrong or be misunderstood]\n"
        "Plan:       [numbered steps you will take]\n"
        "First step: [what you do right now]\n"
        "```\n"
        "---\n"
    )
    _append_to_system(agent, snippet)


def _append_to_system(agent, text: str):
    """Append text to the last system message in agent history."""
    try:
        history = agent.history if hasattr(agent, "history") else []
        for msg in reversed(history):
            role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
            if role == "system":
                if hasattr(msg, "content"):
                    msg.content = str(msg.content) + text
                elif isinstance(msg, dict):
                    msg["content"] = str(msg.get("content", "")) + text
                return
        # No system message found — this is fine, skip silently
    except Exception:
        pass
