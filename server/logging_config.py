"""Structured (JSON lines) logging."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        data.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED})
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("chesslens")
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    root.propagate = False
