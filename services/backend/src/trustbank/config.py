from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated configuration. Invalid values fail at startup."""

    model_config = SettingsConfigDict(env_prefix="TRUSTBANK_", env_file=".env", extra="ignore")

    environment: str = Field(default="local", pattern="^(local|test|deployed)$")

    google_cloud_project: str = "trustbank-local"
    firestore_emulator_host: str | None = None

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("trustbank-local-pw")

    @property
    def is_deployed(self) -> bool:
        return self.environment == "deployed"


@lru_cache
def get_settings() -> Settings:
    return Settings()
