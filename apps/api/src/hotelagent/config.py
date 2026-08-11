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

    # Defaults target localhost, because host-side tooling (`make migrate`,
    # pytest) runs outside the Compose network. Containers get the in-network
    # hostnames injected by docker-compose.yml, which override these.
    database_url: str = "postgresql+asyncpg://hotelagent:hotelagent@localhost:5432/hotelagent"
    redis_url: str = "redis://localhost:6379/0"

    # Integration tests run against a separate database so they never touch
    # development data. Defaults to localhost because pytest runs on the host,
    # outside the Compose network where the service is called "postgres".
    test_database_url: str = (
        "postgresql+asyncpg://hotelagent:hotelagent@localhost:5432/hotelagent_test"
    )

    # SQL echoed to the log. Useful when learning what the ORM actually emits.
    database_echo: bool = False

    # --- Channel ---------------------------------------------------------
    # Which adapter serves the gateway. "console" needs no Meta account and no
    # public URL, so the whole inbound flow is testable locally.
    channel_adapter: Literal["cloud_api", "console"] = "console"

    # Meta app secret, used to verify the X-Hub-Signature-256 header on every
    # inbound webhook. An empty value means signature verification cannot pass.
    whatsapp_app_secret: str = ""
    # The token echoed back during Meta's GET subscription handshake.
    whatsapp_verify_token: str = ""

    # M1 runs one city. The gateway needs a city_id for every conversation
    # (invariant #1), and resolves it from this slug until routing by phone
    # number or entry point exists.
    default_city_slug: str = "kanyakumari"

    # Sending credentials. The token is a secret and is never logged.
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_base_url: str = "https://graph.facebook.com"
    whatsapp_api_version: str = "v21.0"

    # --- Outbound HTTP ---------------------------------------------------
    # Every outbound call is bounded. A request with no timeout can hang for
    # as long as the peer keeps the socket open, and one hung coroutine per
    # stuck conversation is how an event loop quietly fills up.
    http_timeout_seconds: float = 10.0
    # Total attempts, not retries — 3 means one try plus two retries.
    http_max_attempts: int = 3

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
