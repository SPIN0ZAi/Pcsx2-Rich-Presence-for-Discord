"""
utils/storage.py — Simple JSON user settings persistence.

Stores user config (Discord App ID, IGDB keys, etc.) in:
  Windows: %APPDATA%\pcsx2rpc\settings.json
  Linux:   ~/.pcsx2rpc/settings.json

This is written by the setup wizard and read by the service.
It intentionally has only the keys users set interactively —
everything else still comes from config.yaml defaults.
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
    d = base / "pcsx2rpc"
    d.mkdir(parents=True, exist_ok=True)
    return d


SETTINGS_PATH = _settings_dir() / "settings.json"


def load_settings() -> dict[str, Any]:
    """Load persisted user settings. Returns empty dict if not found."""
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_settings(data: dict[str, Any]) -> None:
    """Persist user settings to disk."""
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def is_first_run() -> bool:
    """Return True if no settings file exists yet."""
    return not SETTINGS_PATH.exists()
