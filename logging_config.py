"""
Centralised logging configuration for the Knowledge Graph pipeline.

Usage (call once at each CLI entry point, before any other imports that log):

    from logging_config import configure_logging
    configure_logging()

Environment variables:
    LOG_LEVEL   — DEBUG / INFO / WARNING / ERROR  (default: INFO)
    LOG_FORMAT  — "json" for structured JSON output; anything else for plain text
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv as _load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging() -> None:
    """
    Configure the root logger from environment variables.

    Also loads a .env file from the project root if python-dotenv is installed
    and the file exists. Safe to call multiple times.
    """
    if _DOTENV_AVAILABLE:
        _load_dotenv(override=False)  # env vars already in shell take priority

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    if os.environ.get("LOG_FORMAT", "").lower() == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
