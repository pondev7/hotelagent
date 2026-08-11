"""Application configuration.

Invariant #9: all configuration arrives through environment variables. This is
the only module in the codebase that reads the environment — everything else
calls ``get_settings()``. Every new key is added here and to ``.env.example``,
with a comment, in the same commit.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "staging", "production"]


class Settings(BaseSettings):
    """Every value the application reads from its environment."""

    model_config = SettingsConfigDict(
        env_prefix="HOTELAGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = "local"
    log_json: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    database_url: str = "postgresql+asyncpg://hotelagent:hotelagent@postgres:5432/hotelagent"
    redis_url: str = "redis://redis:6379/0"

    # Object storage is reached through the S3-compatible API only, so the same
    # code path serves R2, S3 and MinIO. Unset until media handling lands.
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read from the environment once."""
    return Settings()
