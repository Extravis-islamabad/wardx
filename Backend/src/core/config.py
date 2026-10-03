"""Settings, read from WARDX_* environment variables (and .env)."""

from __future__ import annotations

import base64
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Development-only keys are generated here on first start; never used in production.
DEV_STATE_DIR = Path(".wardx")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="WARDX_", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_role: Literal["api", "api_only", "scheduler", "gateway"] = "api"
    database_url: str = "postgresql+asyncpg://wardx:wardx@localhost:5432/wardx"
    db_pool_size: int = 10

    jwt_secret: str = ""
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 7

    vault_kek: str = ""
    vault_kek_retired: str = ""

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""

    cors_origins: list[str] = ["http://localhost:5173"]

    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    # How long a pending request waits for a decision, and how long an approval
    # stays usable before the check-out must start.
    request_window_minutes: int = 240
    expiry_sweep_seconds: int = 30

    # ── Session gateway (APP_ROLE=gateway) ──
    gateway_listen_host: str = "0.0.0.0"  # noqa: S104 - a gateway listens for users
    gateway_port: int = 2222
    # Shown to users in the "how to connect" hint.
    gateway_public_host: str = "localhost"
    # Required in production; development generates .wardx/gateway_host_key.
    gateway_host_key_file: str = ""
    gateway_node: str = ""
    recording_dir: str = "recordings"
    target_connect_timeout_seconds: int = 15
    # How often a gateway checks for kill requests and expired check-outs.
    gateway_watch_seconds: float = 2.0

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def runs_api(self) -> bool:
        return self.app_role in ("api", "api_only")

    def runs_scheduler(self) -> bool:
        return self.app_role in ("api", "scheduler")


def _dev_secret_file(name: str, nbytes: int) -> str:
    """Read or create a base64 secret under .wardx/ (mode 0600)."""
    DEV_STATE_DIR.mkdir(mode=0o700, exist_ok=True)
    path = DEV_STATE_DIR / name
    if not path.exists():
        value = base64.b64encode(secrets.token_bytes(nbytes)).decode()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(value)
    return path.read_text().strip()


def resolve_jwt_secret(settings: Settings) -> str:
    if settings.jwt_secret:
        if len(settings.jwt_secret) < 32:
            raise RuntimeError("WARDX_JWT_SECRET must be at least 32 characters")
        return settings.jwt_secret
    if settings.is_production:
        raise RuntimeError("WARDX_JWT_SECRET is required in production")
    return _dev_secret_file("jwt.key", 48)


def resolve_gateway_host_key_file(settings: Settings) -> Path:
    if settings.gateway_host_key_file:
        return Path(settings.gateway_host_key_file)
    if settings.is_production:
        raise RuntimeError("WARDX_GATEWAY_HOST_KEY_FILE is required in production")
    return DEV_STATE_DIR / "gateway_host_key"


def resolve_vault_kek(settings: Settings) -> str:
    if settings.vault_kek:
        return settings.vault_kek
    if settings.is_production:
        raise RuntimeError("WARDX_VAULT_KEK is required in production")
    return _dev_secret_file("kek.key", 32)


@lru_cache
def get_settings() -> Settings:
    return Settings()
