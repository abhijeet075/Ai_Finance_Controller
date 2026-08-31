from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = (
        "postgresql+psycopg://finance_user:finance_password"
        "@localhost:5432/finance_controller"
    )
    llm_api_key: str | None = None
    llm_model: str | None = None
    cors_origins: list[str] = ["http://localhost:5173"]
    max_upload_bytes: int = 10_485_760
    max_upload_records: int = 10_000

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
