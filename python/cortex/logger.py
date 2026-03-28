"""
python/cortex/logger.py — CortexLogger
========================================
Structured logging for CORTEX — no SocketIO coupling.

Outputs to:
  - stdout (via Python's logging module, respects log level)
  - Rotating file: {memory_subdir}/cortex.log (10 MB max, 3 backups)

Levels: DEBUG, INFO, WARNING, ERROR (standard Python logging levels)

Usage:
    logger = CortexLogger.for_agent(agent)
    logger.info("Proactive pulse fired", venture="verdant", findings=3)
    logger.warning("SurfSense unreachable")
    logger.error("Discovery gate failed", error=str(e))

    # Module-level logger (no agent context):
    log = CortexLogger.get("cortex_proactive_engine")
    log.info("Starting pulse scan")

H1 transition: extensions/tools still use agent.context.log (AZ's SocketIO logger).
CortexLogger used for new CORTEX helpers and background tasks that have no SocketIO context.
H1-C: replace agent.context.log usage in extensions with CortexLogger.
"""
from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

_LOG_FILENAME = "cortex.log"
_LOG_MAX_BYTES = 10 * 1024 * 1024   # 10 MB
_LOG_BACKUP_COUNT = 3
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Registry of named loggers
_loggers: dict[str, "CortexLogger"] = {}


class CortexLogger:
    """
    Thin wrapper around Python's logging.Logger.
    Adds structured key-value pairs to log messages.
    """

    def __init__(self, name: str, log_path: Optional[Path] = None):
        self._name = name
        self._logger = self._build(name, log_path)

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def for_agent(cls, agent: Any, name: str = "cortex") -> "CortexLogger":
        """Get a logger scoped to this agent's memory subdir."""
        try:
            from python.cortex.memory import get_agent_memory_subdir, abs_db_dir
            subdir = get_agent_memory_subdir(agent)
            base = Path(abs_db_dir(subdir))
        except Exception:
            import tempfile
            base = Path(tempfile.gettempdir())

        log_path = base / _LOG_FILENAME
        cache_key = f"{name}:{log_path}"
        if cache_key not in _loggers:
            _loggers[cache_key] = cls(name, log_path)
        return _loggers[cache_key]

    @classmethod
    def get(cls, name: str) -> "CortexLogger":
        """Get a named logger (stdout only, no file)."""
        if name not in _loggers:
            _loggers[name] = cls(name, log_path=None)
        return _loggers[name]

    # ------------------------------------------------------------------
    # Logging API
    # ------------------------------------------------------------------

    def debug(self, msg: str, **kvps: Any) -> None:
        self._logger.debug(self._format(msg, kvps))

    def info(self, msg: str, **kvps: Any) -> None:
        self._logger.info(self._format(msg, kvps))

    def warning(self, msg: str, **kvps: Any) -> None:
        self._logger.warning(self._format(msg, kvps))

    def error(self, msg: str, **kvps: Any) -> None:
        self._logger.error(self._format(msg, kvps))

    def exception(self, msg: str, **kvps: Any) -> None:
        self._logger.exception(self._format(msg, kvps))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _format(self, msg: str, kvps: dict[str, Any]) -> str:
        if not kvps:
            return msg
        try:
            kv_str = " | ".join(f"{k}={json.dumps(v, default=str)}" for k, v in kvps.items())
            return f"{msg} [{kv_str}]"
        except Exception:
            return msg

    @staticmethod
    def _build(name: str, log_path: Optional[Path]) -> logging.Logger:
        logger = logging.getLogger(f"cortex.{name}")
        if logger.handlers:
            return logger  # already configured

        logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

        # Stdout handler
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(
            logging.DEBUG if os.getenv("CORTEX_LOG_DEBUG") else logging.INFO
        )
        logger.addHandler(stream_handler)

        # File handler (rotating) — only if log_path provided
        if log_path is not None:
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                file_handler = RotatingFileHandler(
                    str(log_path),
                    maxBytes=_LOG_MAX_BYTES,
                    backupCount=_LOG_BACKUP_COUNT,
                    encoding="utf-8",
                )
                file_handler.setFormatter(formatter)
                file_handler.setLevel(logging.DEBUG)
                logger.addHandler(file_handler)
            except Exception:
                pass  # file logging failure is non-fatal

        logger.propagate = False
        return logger
