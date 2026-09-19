"""Application settings loaded from environment / .env file."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ENV_FILE, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://cardcube:changeme@localhost:5432/cardcube"
    database_sync_url: str = "postgresql+psycopg2://cardcube:changeme@localhost:5432/cardcube"
    mail_encryption_key: str = "cardcue-secret-key-32-bytes-long!"
    mail_storage_dir: str = str(_BASE_DIR / "data" / "mail_storage")
    mail_check_interval_minutes: int = 30

    # LLM statement extraction settings
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"


settings = Settings()
