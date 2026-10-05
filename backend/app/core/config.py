from pathlib import Path

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