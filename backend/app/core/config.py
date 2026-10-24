"""Application configuration, loaded from environment variables (and an optional .env file).

Nothing in this module is a production secret. The development database URL below is a
local-only convenience default and is rejected when APP_ENV=production.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_DATABASE_URL = "postgresql+psycopg://brandpr:brandpr_dev_password@localhost:5432/brandpr"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = DEV_DATABASE_URL

    @field_validator("database_url", mode="before")
    @classmethod
    def clean_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lstrip("\ufeff")
        return v

    # Comma-separated list of browser origins allowed to call the API directly.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Local file storage for uploaded source documents. Must be persistent in deployment.
    storage_dir: Path = Path("./storage")
    gcs_bucket: str = ""
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pdf_pages: int = 500
    max_csv_rows: int = 50_000

    # Facts whose review_date falls within this many days are reported as "due soon".
    review_warning_days: int = 30

    docs_enabled: bool = True
    jwt_secret: str = "brandpr-production-secure-jwt-key-32chars"
    auth_enforced: bool = False

    # Testing aid (Phase 3): shifts the date used by validity and expiry rules, so expiry behaviour can be exercised
    # against a running server without waiting. Only today() is shifted; stored timestamps stay real. Refused in production.
    clock_offset_days: int = 0

    # --- Phase 2: content review (ProofGraph) ---
    max_content_chars: int = 20_000
    # The model provider is used only when LLM_API_KEY is set. Without a key the review engine runs in a
    # clearly labelled limited (deterministic-only) mode; it never pretends a full AI review happened.
    llm_provider: Literal["anthropic"] = "anthropic"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-5-5"
    llm_base_url: str = "https://api.anthropic.com"
    llm_timeout_seconds: float = 45.0
    llm_max_output_tokens: int = 2000
    # Optional JSON object overriding default severities, e.g. {"unsupported:comparative":"medium"}. Keys are "status:category" or "status:*".
    review_severity_overrides: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def assert_safe_for_environment(self) -> None:
        if self.app_env == "production":
            if self.clock_offset_days != 0:
                raise RuntimeError("CLOCK_OFFSET_DAYS is a testing aid and must be 0 in production.")
            if "brandpr_dev_password" in self.database_url:
                raise RuntimeError(
                    "DATABASE_URL still uses the development password; set a real credential."
                )
            if any("localhost" in o or "127.0.0.1" in o for o in self.cors_origin_list):
                raise RuntimeError("CORS_ORIGINS must not include localhost in production.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
