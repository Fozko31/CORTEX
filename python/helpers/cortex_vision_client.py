"""
cortex_vision_client.py — Two-Step Image Understanding
=======================================================
Converts raw image bytes into a structured analysis dict.

Pipeline:
  Step 1 — Gemini 2.5 Flash-Lite (via OpenRouter)
            → raw description of what's in the image
            → cheap: ~$0.001-0.003 per image
  Step 2 — DeepSeek V3.2 (via OpenRouter)
            → structures description into standard schema
            → resolves ambiguity, extracts actionable items

Output schema:
  {
    "summary":          str,   # one-line description
    "key_elements":     list,  # main objects / people / UI elements visible
    "text_in_image":    str,   # all readable text, verbatim
    "data":             dict,  # tables, numbers, charts if present
    "ui_elements":      list,  # buttons, fields, links if it's a screenshot
    "actionable_items": list,  # "Approve payment", "Fill in field X", etc.
    "requires_decision": bool, # True if user action is needed
  }

Why this approach vs. Claude Sonnet:
  - ~10x cheaper per image
  - Gemini 2.5 Flash-Lite is GA stable (Gemini 3.x all Preview as of March 2026)
  - Two-step separates raw perception from structured reasoning
"""

import base64
import json
import os
from typing import Optional

import httpx


_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_GEMINI_MODEL   = "google/gemini-2.0-flash-lite-001"             # Gemini 2.0 Flash-Lite (GA stable on OpenRouter)
_DEEPSEEK_MODEL = "deepseek/deepseek-chat-v3-0324"               # DeepSeek V3.2


_STEP1_SYSTEM = """\
You are an expert image analyst. Describe what you see in the image completely and accurately.
Include: all text visible (verbatim), UI elements, people, objects, data/charts, context.
Be thorough — your description will be processed by another AI to extract structured information.
Do not speculate about what is outside the image. Do not refuse to describe visible content.\
"""

_STEP2_SYSTEM = """\
You receive a raw image description and must extract structured information from it.
Return ONLY a valid JSON object matching this exact schema — no markdown, no explanation:
{
  "summary": "one-line description of the image",
  "key_elements": ["list", "of", "main", "elements"],
  "text_in_image": "all readable text from the image, verbatim",
  "data": {},
  "ui_elements": ["list of buttons/fields/links if UI screenshot"],
  "actionable_items": ["list of actions the user may need to take"],
  "requires_decision": false
}
If a field is not applicable, use its zero value (empty string, empty list, empty dict, false).\
"""

_EMPTY_ANALYSIS = {
    "summary": "",
    "key_elements": [],
    "text_in_image": "",
    "data": {},
    "ui_elements": [],
    "actionable_items": [],
    "requires_decision": False,
}


class VisionError(Exception):
    """Raised when image analysis fails at the API level."""


class CortexVisionClient:
    """
    Two-step image analysis pipeline.

    Usage:
        client = CortexVisionClient.from_env()
        analysis = await client.analyze(image_bytes, hint="invoice")
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://cortex.local",
            "X-Title": "CORTEX Vision",
        }

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "CortexVisionClient":
        return cls(api_key=os.getenv("API_KEY_OPENROUTER", ""))

    @classmethod
    def from_agent_config(cls, agent) -> "CortexVisionClient":
        key = ""
        try:
            if agent and hasattr(agent, "config") and hasattr(agent.config, "get_api_key"):
                key = agent.config.get_api_key("API_KEY_OPENROUTER") or ""
        except Exception:
            pass
        if not key:
            key = os.getenv("API_KEY_OPENROUTER", "")
        return cls(api_key=key)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def analyze(
        self,
        image_bytes: bytes,
        hint: Optional[str] = None,
        mime_type: str = "image/jpeg",
    ) -> dict:
        """
        Analyze an image.

        Args:
            image_bytes: Raw image data (PNG, JPEG, WebP).
            hint:        Optional context hint ("invoice", "screenshot", "chart").
            mime_type:   MIME type of the image.

        Returns:
            Analysis dict matching the schema above.
        """
        # Step 1: Gemini describes the image
        raw_description = await self._describe(image_bytes, mime_type, hint)

        # Step 2: DeepSeek structures the description
        analysis = await self._structure(raw_description)

        return analysis

    # ------------------------------------------------------------------
    # Step 1: Gemini 2.5 Flash-Lite — raw description
    # ------------------------------------------------------------------

    async def _describe(
        self,
        image_bytes: bytes,
        mime_type: str,
        hint: Optional[str],
    ) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            }
        ]
        if hint:
            user_content.append({
                "type": "text",
                "text": f"Context hint: {hint}",
            })

        payload = {
            "model": _GEMINI_MODEL,
            "messages": [
                {"role": "system", "content": _STEP1_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(_OPENROUTER_URL, json=payload, headers=self._headers)

        if resp.status_code != 200:
            raise VisionError(
                f"Gemini step failed: HTTP {resp.status_code} — {resp.text[:300]}"
            )

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise VisionError("Gemini returned no choices")
        return choices[0]["message"]["content"]

    # ------------------------------------------------------------------
    # Step 2: DeepSeek V3.2 — structure the description
    # ------------------------------------------------------------------

    async def _structure(self, description: str) -> dict:
        payload = {
            "model": _DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": _STEP2_SYSTEM},
                {"role": "user", "content": description},
            ],
            "temperature": 0.0,
            "max_tokens": 512,
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(_OPENROUTER_URL, json=payload, headers=self._headers)

            if resp.status_code != 200:
                return {**_EMPTY_ANALYSIS, "summary": description[:200]}

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return {**_EMPTY_ANALYSIS, "summary": description[:200]}

            content = choices[0]["message"]["content"].strip()
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("```", 2)[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.rstrip("`").strip()

            return json.loads(content)

        except json.JSONDecodeError:
            # Return partial result rather than failing
            return {**_EMPTY_ANALYSIS, "summary": description[:200]}
        except Exception:
            return dict(_EMPTY_ANALYSIS)
