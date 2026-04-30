"""Runtime configuration loaded from env / .env.

Add new tunables as fields here, not as ad-hoc os.environ reads elsewhere.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    database_url: str = Field(
        default=f"sqlite:///{REPO_ROOT / 'data' / 'polyforecast.db'}",
        alias="DATABASE_URL",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("database_url")
    @classmethod
    def _normalize_pg_driver(cls, v: str) -> str:
        # Neon (and most providers) hand out URLs as postgresql://...; SQLAlchemy 2.x
        # picks psycopg2 from that prefix by default. We use psycopg v3, so rewrite to
        # postgresql+psycopg:// here. Users paste the URL exactly as Neon gives it.
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://") :]
        return v


settings: Settings = Settings()
