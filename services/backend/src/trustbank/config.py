from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated configuration. Invalid or missing required values fail at startup."""

    model_config = SettingsConfigDict(env_prefix="TRUSTBANK_", env_file=".env", extra="ignore")

    environment: str = Field(default="local", pattern="^(local|test|deployed)$")

    google_cloud_project: str = "trustbank-local"
    firestore_emulator_host: str | None = None

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("trustbank-local-pw")

    token_secret: SecretStr | None = None
    investigator_code: SecretStr | None = None
    customer_token_hours: int = Field(default=8, ge=1, le=72)
    investigator_token_minutes: int = Field(default=120, ge=5, le=1440)
    investigator_attempts_per_minute: int = Field(default=5, ge=1, le=60)

    cors_origins: str = "http://localhost:4200"

    @model_validator(mode="after")
    def _require_secrets(self) -> Self:
        if self.token_secret is None or len(self.token_secret.get_secret_value()) < 32:
            raise ValueError(
                "TRUSTBANK_TOKEN_SECRET is required and must be at least 32 characters"
            )
        if self.investigator_code is None or not self.investigator_code.get_secret_value():
            raise ValueError("TRUSTBANK_INVESTIGATOR_CODE is required")
        return self

    @property
    def is_deployed(self) -> bool:
        return self.environment == "deployed"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
