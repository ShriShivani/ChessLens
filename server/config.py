"""Server settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_TOKEN = "change-me"


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./chesslens.db"
    ingest_token: str = DEFAULT_TOKEN
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    rate_limit_per_min: int = 120  # per client IP, applied to /api requests
    max_viewers_per_game: int = 500
    log_level: str = "INFO"
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Settings:
        origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
        return cls(
            database_url=os.environ.get("DATABASE_URL", cls.database_url),
            ingest_token=os.environ.get("INGEST_TOKEN", DEFAULT_TOKEN),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
            rate_limit_per_min=int(os.environ.get("RATE_LIMIT_PER_MIN", "120")),
            max_viewers_per_game=int(os.environ.get("MAX_VIEWERS_PER_GAME", "500")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
