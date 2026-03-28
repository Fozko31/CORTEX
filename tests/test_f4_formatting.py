"""
F-4 Tests — Response Formatting + Comprehension Check
=======================================================
Tests for:
  cortex_response_formatter.py  — Telegram / Voice / Web formatters
  _08_comprehension_check.py    — Action verb detection, mode routing

All tests are synchronous or async with mocked agent state.
No external API calls.
"""

import pytest
from unittest.mock import MagicMock, patch


# ===========================================================================
# Response Formatter — Telegram (tests 1–8)
# ===========================================================================

class TestTelegramFormatter:

    def _fmt(self):
        from python.helpers.cortex_response_formatter import CortexResponseFormatter
        return CortexResponseFormatter()

    # 1. Markdown table → bullet list
    def test_table_to_bullets(self):
        fmt = self._fmt()
        text = "| Name | Revenue |\n|------|--------|\n| MovingCo | €50k |\n| Acme | €120k |"
        result = fmt.format_for_telegram(text)
        assert "|" not in result or "•" in result
        assert "MovingCo" in result
        assert "€50k" in result

    # 2. Bold preserved
    def test_bold_preserved(self):
        fmt = self._fmt()
        result = fmt.format_for_telegram("**Important:** check this")
        assert "**Important:**" in result

    # 3. Bullet markers normalized to •
    def test_bullets_normalized(self):
        fmt = self._fmt()
        text = "- item one\n* item two\n+ item three"
        result = fmt.format_for_telegram(text)
        assert result.count("•") == 3
        assert "- item" not in result

    # 4. Code blocks stripped to plain text
    def test_code_blocks_stripped(self):
        fmt = self._fmt()
        text = "Here:\n```python\nprint('hello')\n```"
        result = fmt.format_for_telegram(text)
        assert "```" not in result
        assert "print" in result

    # 5. Inline code stripped
    def test_inline_code_stripped(self):
        fmt = self._fmt()
        result = fmt.format_for_telegram("Use the `run_ui.py` script")
        assert "`" not in result
        assert "run_ui.py" in result

    # 6. Long text truncated at 4000 chars with suffix
    def test_long_text_truncated(self):
        fmt = self._fmt()
        long_text = "word " * 1000   # ~5000 chars
        result = fmt.format_for_telegram(long_text)
        assert len(result) <= 4100   # buffer for suffix
        assert "truncated" in result

    # 7. Short text not truncated
    def test_short_text_not_truncated(self):
        fmt = self._fmt()
        text = "Short response."
        result = fmt.format_for_telegram(text)
        assert result == text

    # 8. Multiple blank lines collapsed
    def test_blank_lines_collapsed(self):
        fmt = self._fmt()
        text = "Line one\n\n\n\n\nLine two"
        result = fmt.format_for_telegram(text)
        assert "\n\n\n" not in result


# ===========================================================================
# Response Formatter — Voice (tests 9–14)
# ===========================================================================

class TestVoiceFormatter:

    def _fmt(self):
        from python.helpers.cortex_response_formatter import CortexResponseFormatter
        return CortexResponseFormatter()

    # 9. All markdown stripped for voice
    def test_markdown_stripped(self):
        fmt = self._fmt()
        result = fmt.format_for_voice("**Bold** and _italic_ and `code`")
        assert "**" not in result
        assert "_" not in result
        assert "`" not in result
        assert "Bold" in result
        assert "italic" in result

    # 10. Headers stripped
    def test_headers_stripped(self):
        fmt = self._fmt()
        result = fmt.format_for_voice("## Section Title\nContent here.")
        assert "##" not in result
        assert "Section Title" in result

    # 11. Percentage symbol → words
    def test_percent_to_words(self):
        fmt = self._fmt()
        result = fmt.format_for_voice("Revenue grew by 12%")
        assert "12 percent" in result
        assert "%" not in result

    # 12. Dollar symbol → words
    def test_dollar_to_words(self):
        fmt = self._fmt()
        result = fmt.format_for_voice("It costs $50 per month")
        assert "50 dollars" in result

    # 13. Arrow symbol → words
    def test_arrow_to_words(self):
        fmt = self._fmt()
        result = fmt.format_for_voice("Click next → submit")
        assert "→" not in result
        assert "leads to" in result

    # 14. Table pipes stripped
    def test_table_pipes_stripped(self):
        fmt = self._fmt()
        result = fmt.format_for_voice("| Name | Value |\n| A | 1 |")
        assert "|" not in result
        assert "Name" in result


# ===========================================================================
# Response Formatter — Web (tests 15–16)
# ===========================================================================

class TestWebFormatter:

    def _fmt(self):
        from python.helpers.cortex_response_formatter import CortexResponseFormatter
        return CortexResponseFormatter()

    # 15. Web format: pass through unchanged
    def test_web_passthrough(self):
        fmt = self._fmt()
        text = "**Bold** | table | `code` \n\n## Header"
        result = fmt.format_for_web(text)
        assert result == text

    # 16. format() dispatcher routes correctly
    def test_format_dispatcher(self):
        fmt = self._fmt()
        text = "- item"
        telegram = fmt.format("- item", "telegram")
        voice = fmt.format("- item", "voice")
        web = fmt.format("- item", "web")
        assert "•" in telegram
        assert "-" not in voice or "•" not in voice
        assert web == text


# ===========================================================================
# Comprehension Check Extension (tests 17–18)
# ===========================================================================

class TestComprehensionCheck:

    # 17. _has_action_verb: True for action messages
    def test_has_action_verb_true(self):
        from python.extensions.monologue_start._08_comprehension_check import _has_action_verb
        assert _has_action_verb("Draft an email to the client") is True
        assert _has_action_verb("Research competitor pricing") is True
        assert _has_action_verb("Send the invoice to Kovač") is True

    # 18. _has_action_verb: False for pure questions
    def test_has_action_verb_false(self):
        from python.extensions.monologue_start._08_comprehension_check import _has_action_verb
        assert _has_action_verb("What is the CVS score?") is False
        assert _has_action_verb("How does SurfSense work?") is False
