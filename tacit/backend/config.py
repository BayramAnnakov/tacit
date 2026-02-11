"""Application configuration using pydantic-settings."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    GITHUB_TOKEN: str = ""
    ANTHROPIC_API_KEY: str = ""
    WEBHOOK_SECRET: str = ""
    DB_PATH: str = str(Path(__file__).parent / "tacit.db")
    LOG_DIR: str = str(Path(__file__).parent / "logs")
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Ensure log directory exists
os.makedirs(settings.LOG_DIR, exist_ok=True)
