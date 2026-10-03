"""Configuration centralisée (variables d'environnement / fichier .env)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Scanner Transport - Backend de test (MOCK)"
    app_version: str = "1.0.0"
    database_url: str = "postgresql+psycopg://scanner:scanner@localhost:5432/scanner_mock"
    log_level: str = "INFO"
    # Fenêtre (en minutes) pendant laquelle un 2e scan de la même carte, dans le même véhicule et sur
    # la même ligne, est considéré comme le MÊME voyage (-> TRIP_ALREADY_VALIDATED).
    trip_window_minutes: int = Field(default=60, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
