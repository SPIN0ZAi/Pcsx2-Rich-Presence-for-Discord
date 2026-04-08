"""
utils/storage.py — unified JSON config persistence.

Stores user config in:
    Windows: %APPDATA%\\EmuPresence\\config.json
    Linux:   ~/.emupresence/config.json

Backward compatible with the previous settings.json location.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _settings_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home()
    d = base / "EmuPresence"
    d.mkdir(parents=True, exist_ok=True)
    return d


SETTINGS_PATH = _settings_dir() / "config.json"
_LEGACY_SETTINGS_PATH = (
    (Path(os.environ.get("APPDATA", Path.home())) / "pcsx2rpc" / "settings.json")
    if sys.platform == "win32"
    else (Path.home() / ".pcsx2rpc" / "settings.json")
)


DEFAULT_SETTINGS: dict[str, Any] = {
    "discord": {
        "client_id": "",
    },
    "metadata": {
        "igdb_client_id": "",
        "igdb_client_secret": "",
    },
    "app": {
        "poll_interval_seconds": 5,
        "clear_delay_seconds": 15,
        "show_notifications": True,
        "presence_style": "minimal",
        "show_menu_state": True,
        "show_paused_state": True,
        "show_buttons": True,
        "show_elapsed_time": True,
        "log_window_titles": False,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings() -> dict[str, Any]:
    """Load persisted config merged over defaults."""
    source_path = SETTINGS_PATH
    if not source_path.exists() and _LEGACY_SETTINGS_PATH.exists():
        source_path = _LEGACY_SETTINGS_PATH

    if source_path.exists():
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            return _deep_merge(DEFAULT_SETTINGS, user_cfg)
        except Exception:
            return dict(DEFAULT_SETTINGS)
    return dict(DEFAULT_SETTINGS)


def save_settings(data: dict[str, Any]) -> None:
    """Persist config to disk."""
    payload = _deep_merge(DEFAULT_SETTINGS, data)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def is_first_run() -> bool:
    """Return True if no config exists (including legacy path)."""
    return not SETTINGS_PATH.exists() and not _LEGACY_SETTINGS_PATH.exists()
