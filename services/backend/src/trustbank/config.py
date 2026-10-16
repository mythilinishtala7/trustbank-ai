from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated configuration. Invalid or missing required values fail at startup."""

    model_config = SettingsConfigDict(
        env_prefix="TRUSTBANK_",
        env_file=".env",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    environment: str = Field(default="local", pattern="^(local|test|deployed)$")

    google_cloud_project: str = "trustbank-local"
    firestore_emulator_host: str | None = None

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("trustbank-local-pw")

    token_secret: SecretStr | None = None
    investigator_code: SecretStr | None = None
    token_ttl_hours: int = Field(default=8, ge=1, le=72)
    investigator_rate_limit: int = Field(default=5, ge=1)  # failed attempts per window per IP
    investigator_rate_window_seconds: int = Field(default=60, ge=1)

    model_name: str = "gemini-3.8-flash"

    anomaly_weight: float = Field(default=0.4, ge=0, le=1)
    network_weight: float = Field(default=0.6, ge=0, le=1)
    elevated_threshold: int = Field(default=30, ge=1, le=100)
    high_threshold: int = Field(default=60, ge=1, le=100)
    hold_seconds: int = Field(default=180, ge=1)

    cors_origins: tuple[str, ...] = ("http://localhost:4200",)

    @model_validator(mode="after")
    def _defaults_and_consistency(self) -> "Settings":
        if self.environment == "test":
            self.token_secret = self.token_secret or SecretStr(
                "test-token-secret-not-for-production"
            )
            self.investigator_code = self.investigator_code or SecretStr("test-investigator-code")
        if self.high_threshold <= self.elevated_threshold:
            raise ValueError("high_threshold must exceed elevated_threshold")
        return self

    def validate_for_serving(self) -> None:
        """Startup check for the API process (seed and ingest jobs do not need the secrets)."""
        missing = [
            f"TRUSTBANK_{name.upper()}"
            for name in ("token_secret", "investigator_code")
            if not (getattr(self, name) and getattr(self, name).get_secret_value())
        ]
        if missing:
            raise RuntimeError(f"missing required settings: {', '.join(missing)}")
        if self.is_deployed:
            assert self.token_secret and self.investigator_code
            secret = self.token_secret.get_secret_value()
            code = self.investigator_code.get_secret_value()
            if secret.startswith("change-me") or len(secret) < 32:
                raise RuntimeError("TRUSTBANK_TOKEN_SECRET must be a real secret of 32+ characters")
            if code.startswith("change-me"):
                raise RuntimeError("TRUSTBANK_INVESTIGATOR_CODE must not be a placeholder")

    @property
    def is_deployed(self) -> bool:
        return self.environment == "deployed"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
