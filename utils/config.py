"""
Config loading and validation using Pydantic v2 + YAML.

Priority (highest → lowest):
  1. config.local.yaml  (user secrets, gitignored)
  2. config.yaml        (shared defaults, committed)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


# ─── Sub-models ──────────────────────────────────────────────────────────────

class DiscordConfig(BaseModel):
    client_id: str = "YOUR_DISCORD_APP_CLIENT_ID"


class PCSX2Config(BaseModel):
    log_path: Path | None = None
    process_name: str = "pcsx2"
    poll_interval_seconds: int = Field(default=5, ge=1, le=60)


class MetadataConfig(BaseModel):
    igdb_client_id: str = ""
    igdb_client_secret: str = ""
    screenscraper_username: str = ""
    screenscraper_password: str = ""
    cache_ttl_days: int = Field(default=7, ge=1)
    gametdb_path: Path | None = None


class ButtonConfig(BaseModel):
    label: str
    enabled: bool = True


class PresenceConfig(BaseModel):
    privacy_mode: bool = False
    show_cover_art: bool = True
    show_elapsed_time: bool = True
    custom_details: str | None = None
    custom_state: str | None = None
    min_update_interval_seconds: int = Field(default=16, ge=15)
    clear_delay_seconds: int = Field(default=10, ge=0)
    buttons: list[ButtonConfig] = Field(
        default_factory=lambda: [ButtonConfig(label="View on IGDB", enabled=True)]
    )


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file_enabled: bool = True
    rotation_mb: int = Field(default=10, ge=1)

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"log level must be one of {allowed}")
        return v.upper()


class AppConfig(BaseModel):
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    pcsx2: PCSX2Config = Field(default_factory=PCSX2Config)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    presence: PresenceConfig = Field(default_factory=PresenceConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


# ─── Loader ──────────────────────────────────────────────────────────────────

def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base (override wins)."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load and validate configuration, merging config.yaml + config.local.yaml."""
    root = config_path.parent if config_path else Path(__file__).parent.parent

    base_path = config_path or (root / "config.yaml")
    local_path = root / "config.local.yaml"

    raw: dict[str, Any] = {}

    if base_path.exists():
        with open(base_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    if local_path.exists():
        with open(local_path, "r", encoding="utf-8") as f:
            local_raw = yaml.safe_load(f) or {}
        raw = _deep_merge(raw, local_raw)

    return AppConfig.model_validate(raw)


# Singleton accessor — populated by main.py at startup
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Return the global config. Raises if not yet initialised."""
    if _config is None:
        raise RuntimeError("Config not initialised. Call init_config() first.")
    return _config


def init_config(config_path: Path | None = None) -> AppConfig:
    """Load config and store as global singleton."""
    global _config
    _config = load_config(config_path)
    return _config
