"""Structured JSON logging.

Every decision and every order is reconstructable from the log alone, so records
are machine-readable and secrets never reach a handler.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_REDACT = ("api_key", "apikey", "secret", "token", "password", "authtoken")


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("***" if any(s in k.lower() for s in _REDACT) else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [_redact(v) for v in obj]
    return obj


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload |= _redact(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure(level: str = "INFO") -> None:
    """Idempotent root-logger setup. Safe to call from every entry point."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, msg: str, /, **fields: Any) -> None:
    """Emit a structured event: ``log_event(log, INFO, "order.placed", id=..., qty=...)``."""
    logger.log(level, msg, extra={"extra_fields": fields})
