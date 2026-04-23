#!/usr/bin/env python3
"""Configuration for GPT2API_IIAP."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime settings loaded from environment or .env file."""

    # Server
    host: str = "127.0.0.1"
    port: int = 8787

    # Storage
    storage_dir: Path = Path("./data")

    # Admin
    admin_token: str = "change-me"

    # Upstream
    chatgpt_base_url: str = "https://chatgpt.com"
    upstream_proxy: str | None = None
    openai_access_token: str | None = None
    openai_session_token: str | None = None

    # Scheduling
    default_request_max_concurrency: int = 1
    default_request_min_start_interval_ms: int = 0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
