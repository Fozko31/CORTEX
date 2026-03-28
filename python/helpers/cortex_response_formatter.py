"""
cortex_response_formatter.py — Medium-Aware Response Formatter
===============================================================
Transforms agent responses for different output media.

Media targets:
  telegram  — No markdown tables, no HTML, bullet points with •,
               bold preserved via *bold*, code blocks stripped to plain text.
               Respects Telegram's 4096-char message limit.
  voice     — All symbols stripped, markdown removed, natural speech.
               Numbers/units spelled out where ambiguous.
  web       — Unchanged markdown (passed through as-is).

Usage:
    formatter = CortexResponseFormatter()
    text = formatter.format_for_telegram("**Hello** | Name | Age |")
    audio_text = formatter.format_for_voice("**2.5M** users → 12% churn rate")
"""

import re
from typing import Literal


Medium = Literal["telegram", "voice", "web"]

# Telegram hard limit (leave buffer for system additions)
_TELEGRAM_MAX = 4000
_TRUNCATION_SUFFIX = "\n\n… _(message truncated — use /full for complete response)_"


class CortexResponseFormatter:
    """
    Medium-aware text formatter.

    All methods are synchronous — formatting is pure string transformation.
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def format(self, text: str, medium: Medium) -> str:
        """
        Format text for the target medium.

        Args:
            text:   Raw markdown text from the agent.
            medium: "telegram" | "voice" | "web"

        Returns:
            Formatted string.
        """
        if medium == "telegram":
            return self.format_for_telegram(text)
        if medium == "voice":
            return self.format_for_voice(text)
        return text  # web: pass through

    def format_for_telegram(self, text: str) -> str:
        """Convert markdown to Telegram-safe text."""
        result = text
        result = _strip_html(result)
        result = _tables_to_bullets(result)
        result = _fix_bold(result)
        result = _fix_italic(result)
        result = _code_blocks_to_plain(result)
        result = _inline_code_to_plain(result)
        result = _fix_bullets(result)
        result = _collapse_blank_lines(result)
        result = _truncate_telegram(result)
        return result.strip()

    def format_for_voice(self, text: str) -> str:
        """Strip all formatting for clean TTS input."""
        result = text
        result = _strip_html(result)
        result = _strip_markdown(result)
        result = _symbols_to_words(result)
        result = _collapse_blank_lines(result)
        result = re.sub(r"  +", " ", result)
        return result.strip()

    def format_for_web(self, text: str) -> str:
        """Web: pass through unchanged."""
        return text


# ------------------------------------------------------------------
# Telegram transformations
# ------------------------------------------------------------------

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _tables_to_bullets(text: str) -> str:
    """
    Convert markdown tables to bullet lists.

    | Name | Value |
    |------|-------|
    | A    | 1     |
    →
    • Name: A | Value: 1
    """
    lines = text.split("\n")
    result = []
    headers: list[str] = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Header separator row (---|---) — skip
            if all(re.match(r"^[-: ]+$", c) for c in cells):
                in_table = True
                continue
            if not headers:
                headers = cells
                in_table = True
                continue
            # Data row
            pairs = [f"{h}: {v}" for h, v in zip(headers, cells) if h or v]
            result.append("• " + " | ".join(pairs))
        else:
            if in_table:
                result.append("")
                in_table = False
                headers = []
            result.append(line)

    return "\n".join(result)


def _fix_bold(text: str) -> str:
    """Keep **bold** — Telegram supports it. Strip ___ triple-underscore variants."""
    # Normalize ___text___ and __text__ → **text** for Telegram
    text = re.sub(r"_{2,3}(.+?)_{2,3}", r"**\1**", text)
    return text


def _fix_italic(text: str) -> str:
    # Single underscore italic → strip (Telegram uses _ for italic but it's fragile)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", text)
    return text


def _code_blocks_to_plain(text: str) -> str:
    """Strip ``` code fences, keep content."""
    return re.sub(r"```[a-z]*\n?(.*?)```", r"\1", text, flags=re.DOTALL)


def _inline_code_to_plain(text: str) -> str:
    """Strip backtick inline code."""
    return re.sub(r"`([^`]+)`", r"\1", text)


def _fix_bullets(text: str) -> str:
    """Normalize -, *, + list items → •"""
    return re.sub(r"^[ \t]*[-*+] ", "• ", text, flags=re.MULTILINE)


def _collapse_blank_lines(text: str) -> str:
    """Max 2 consecutive blank lines."""
    return re.sub(r"\n{3,}", "\n\n", text)


def _truncate_telegram(text: str) -> str:
    if len(text) <= _TELEGRAM_MAX:
        return text
    cut = _TELEGRAM_MAX - len(_TRUNCATION_SUFFIX)
    return text[:cut] + _TRUNCATION_SUFFIX


# ------------------------------------------------------------------
# Voice transformations
# ------------------------------------------------------------------

def _strip_markdown(text: str) -> str:
    """Remove all markdown syntax."""
    # Headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Bold / italic
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"_{1,3}(.+?)_{1,3}", r"\1", text, flags=re.DOTALL)
    # Links
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Code
    text = re.sub(r"```[a-z]*\n?(.*?)```", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Bullets
    text = re.sub(r"^[ \t]*[-*+•] ", "", text, flags=re.MULTILINE)
    # Table pipes
    text = re.sub(r"\|", " ", text)
    # Horizontal rules
    text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)
    return text


def _symbols_to_words(text: str) -> str:
    """Replace symbols that TTS engines mis-pronounce."""
    replacements = [
        (r"€(\d)", r"€\1"),        # keep — Azure/Kokoro handle € ok
        (r"\$(\d+(?:\.\d+)?)", r"\1 dollars"),
        (r"(\d+)%", r"\1 percent"),
        (r"→",  " leads to "),
        (r"←",  " from "),
        (r"↑",  " up "),
        (r"↓",  " down "),
        (r"≥",  " greater than or equal to "),
        (r"≤",  " less than or equal to "),
        (r"≠",  " not equal to "),
        (r"&",  " and "),
        (r"\+", " plus "),
        (r"#",  " number "),
        (r"@",  " at "),
        (r"_",  " "),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text
