"""Engine settings — the minimal surface the guardrail engine consumes.

The parent project carries a much larger Settings object; the engine only ever
reads these fields (via ``EngineConfig.from_settings``). Override with
environment variables prefixed ``NIYAM_`` or construct directly in code.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NIYAM_", extra="ignore")

    db_path: str = "niyam.db"
    timezone: str = "Europe/Amsterdam"
    approval_ttl_seconds: int = 3600
    connector_timeout_seconds: float = 10.0
