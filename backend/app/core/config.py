from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    database_url: str
    cors_origins: list[str] = ["http://localhost:5173"]

    import_max_file_bytes: int = Field(default=5 * 1024 * 1024, ge=1, le=20 * 1024 * 1024)
    import_max_rows: int = Field(default=5000, ge=1, le=5000)

    analytics_max_rows: int = Field(default=5000, ge=1, le=20000)
    extract_output_dir: Path = PROJECT_ROOT / "local-data" / "extracts"

    integration_output_dir: Path = PROJECT_ROOT / "local-data" / "integrations"
    allow_private_integration_targets: bool = False
    integration_credential_env_keys: list[str] = []
    integration_http_timeout_seconds: float = Field(default=5, ge=0.1, le=15)
    integration_max_items: int = Field(default=100, ge=1, le=100)

    ai_provider: Literal["mock", "openai"] = "mock"
    ai_model: str = "gpt-4.1-mini"
    ai_embedding_model: str = "text-embedding-3-small"
    ai_api_key_env: str = Field(default="OPENAI_API_KEY", pattern=r"^(OPENAI_API_KEY|AI_PROVIDER_KEY_[A-Z0-9_]+)$")
    ai_temperature: float = Field(default=0, ge=0, le=1)
    ai_timeout_seconds: float = Field(default=15, ge=1, le=30)
    ai_max_tokens: int = Field(default=500, ge=100, le=2000)
    ai_top_k: int = Field(default=3, ge=1, le=5)
    ai_min_score: float = Field(default=0.25, ge=0, le=1)
    ai_document_max_bytes: int = Field(default=2*1024*1024, ge=1024, le=5*1024*1024)
    ai_qdrant_url: str = "http://127.0.0.1:6333"
    ai_qdrant_collection: str = Field(default="fusionhcm_policies", pattern=r"^[a-z][a-z0-9_]{0,50}$")

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Refresh cookie
    refresh_cookie_name: str = "refresh_token"
    refresh_cookie_secure: bool = True
    refresh_cookie_samesite: str = "lax"
    refresh_cookie_path: str = "/auth"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()