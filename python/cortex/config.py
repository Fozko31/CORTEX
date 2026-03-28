"""
python/cortex/config.py — CortexConfig
========================================
CORTEX-specific configuration object.

Contains only the 16 fields CORTEX actually reads from agent.config.
During H1 transition: build via CortexConfig.from_agent_config(agent.config).
Post-H4: loaded from CORTEX's own config file, fully independent of AZ.

Usage:
    config = CortexConfig.from_agent_config(agent.config)
    profile = config.profile
    key = config.get_api_key("TAVILY_API_KEY")
    vision = config.chat_model_vision
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CortexConfig:
    """
    The fields CORTEX reads from agent.config, consolidated into one clean object.
    All fields have safe defaults — nothing crashes if a field is missing.
    """

    # Identity
    profile: str = ""
    memory_subdir: str = ""
    knowledge_subdirs: list[str] = field(default_factory=lambda: ["default", "custom"])

    # Model capabilities
    chat_model_vision: bool = False
    utility_model_ctx_length: int = 8192
    embeddings_model: Any = None

    # API keys (name → value)
    api_keys: dict[str, str] = field(default_factory=dict)

    # SSH code execution
    code_exec_ssh_enabled: bool = True
    code_exec_ssh_addr: str = "localhost"
    code_exec_ssh_port: int = 55022
    code_exec_ssh_user: str = "root"
    code_exec_ssh_pass: str = ""

    # Browser
    browser_http_headers: dict[str, str] = field(default_factory=dict)
    browser_model_vision: bool = False

    # Arbitrary CORTEX-specific settings (e.g., cortex_proactive_enabled)
    additional: dict[str, Any] = field(default_factory=dict)

    # Internal: reference to source config for API key delegation during transition
    _source_config: Any = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_api_key(self, key: str, default: str = "") -> str:
        """
        Retrieve an API key by name.
        During H1 transition: delegates to AZ's get_api_key() if available.
        Post-H4: reads from api_keys dict or environment.
        """
        # Delegate to AZ source config if available (has the real keys)
        if self._source_config is not None:
            try:
                result = self._source_config.get_api_key(key)
                if result:
                    return result
            except Exception:
                pass

        # Fall back to our dict or env
        return self.api_keys.get(key) or os.getenv(key, default)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a CORTEX-specific additional config value."""
        return self.additional.get(key, default)

    # ------------------------------------------------------------------
    # Factory: build from AZ's AgentConfig during H1 transition
    # ------------------------------------------------------------------

    @classmethod
    def from_agent_config(cls, agent_config: Any) -> "CortexConfig":
        """
        Build CortexConfig from AZ's AgentConfig.
        Called by any CORTEX code that receives an AZ agent and needs config.
        """
        def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
            try:
                return getattr(obj, attr, default)
            except Exception:
                return default

        def _safe_model_attr(model_obj: Any, attr: str, default: Any = None) -> Any:
            try:
                return getattr(model_obj, attr, default)
            except Exception:
                return default

        chat_model = _safe_get(agent_config, "chat_model")
        utility_model = _safe_get(agent_config, "utility_model")
        browser_model = _safe_get(agent_config, "browser_model")

        return cls(
            profile=_safe_get(agent_config, "profile", ""),
            memory_subdir=_safe_get(agent_config, "memory_subdir", ""),
            knowledge_subdirs=_safe_get(agent_config, "knowledge_subdirs", ["default", "custom"]),
            chat_model_vision=_safe_model_attr(chat_model, "vision", False),
            utility_model_ctx_length=_safe_model_attr(utility_model, "ctx_length", 8192),
            embeddings_model=_safe_get(agent_config, "embeddings_model"),
            code_exec_ssh_enabled=_safe_get(agent_config, "code_exec_ssh_enabled", True),
            code_exec_ssh_addr=_safe_get(agent_config, "code_exec_ssh_addr", "localhost"),
            code_exec_ssh_port=_safe_get(agent_config, "code_exec_ssh_port", 55022),
            code_exec_ssh_user=_safe_get(agent_config, "code_exec_ssh_user", "root"),
            code_exec_ssh_pass=_safe_get(agent_config, "code_exec_ssh_pass", ""),
            browser_http_headers=_safe_get(agent_config, "browser_http_headers", {}),
            browser_model_vision=_safe_model_attr(browser_model, "vision", False),
            additional=_safe_get(agent_config, "additional", {}),
            _source_config=agent_config,  # kept for get_api_key() delegation
        )

    @classmethod
    def from_env(cls) -> "CortexConfig":
        """
        Build a minimal CortexConfig from environment variables only.
        Used in standalone contexts (tests, scripts) without an AZ agent.
        """
        return cls(
            profile=os.getenv("CORTEX_PROFILE", "cortex"),
            memory_subdir=os.getenv("CORTEX_MEMORY_SUBDIR", ""),
        )
