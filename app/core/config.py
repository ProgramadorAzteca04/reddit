from functools import lru_cache
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Configuración pydantic-settings (v2)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",          # prohíbe variables no declaradas
        case_sensitive=False
    )

    # === Vars de tu proyecto ===
    DATABASE_URL: str
    REDDIT_SCREENSHOTS_DIR: str = "img"
    DEBUG: bool = False

    # === OpenAI ===
    # Lee OPENAI_API_KEY desde .env (o del entorno) y no rompe por "extra"
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY")
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()