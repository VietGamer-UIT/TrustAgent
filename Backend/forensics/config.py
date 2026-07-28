"""
TrustAgent — Forensics feature configuration

Loads settings from environment variables / .env (TrustAgent root or Backend).
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


FORENSICS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = FORENSICS_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
_DEFAULT_SQLITE = f"sqlite+aiosqlite:///{(BACKEND_DIR / 'trustagent_forensics.db').as_posix()}"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_env: str = Field(default="development")
    app_debug: bool = Field(default=True)
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_secret_key: str = Field(default="dev-secret-key-change-in-production")

    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.0-flash")

    database_url: str = Field(default=_DEFAULT_SQLITE)

    z3_timeout_ms: int = Field(default=5000)
    z3_max_retries: int = Field(default=3)
    langgraph_max_iterations: int = Field(default=10)
    langgraph_human_approval_threshold: int = Field(default=50_000_000)

    model_config = {
        "env_file": (
            str(PROJECT_ROOT / ".env"),
            str(BACKEND_DIR / ".env"),
        ),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def _normalize(self) -> "Settings":
        # Docker thường chỉ có GOOGLE_API_KEY
        if not (self.gemini_api_key or "").strip():
            for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                val = os.getenv(key, "").strip()
                if val:
                    self.gemini_api_key = val
                    break
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
