"""Application settings loaded from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://cardcube:changeme@localhost:5432/cardcube"
    database_sync_url: str = "postgresql+psycopg2://cardcube:changeme@localhost:5432/cardcube"


settings = Settings()
