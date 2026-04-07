from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always resolve to server/.env regardless of the working directory
_ENV_FILE = Path(__file__).parent / ".env"


class ServerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # Database URL (SQLite default; swap for postgresql://... in production)
    database_url: str = "sqlite:///./accessguard.db"

    # Secret key used to encrypt stored provider credentials (Fernet key)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str = ""

    # API key that agents must include in X-API-Key header to submit events
    # Can be set per-company (enforced in router) — this is a global fallback
    agent_api_key: str = ""

    # API key required to access the /admin routes
    admin_api_key: str = "change-me"

    # Toggle to allow requests without X-API-Key (development only)
    auth_enabled: bool = True


@lru_cache
def get_config() -> ServerConfig:
    return ServerConfig()
