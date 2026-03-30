"""
Presence builder — maps GameState + GameInfo → Discord activity payload.

Responsible for:
  - Building the correct Discord RPC kwargs dict
  - Smart diffing (only triggers update when payload actually changed)
  - Privacy mode masking
  - Button generation with IGDB links
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from detection.detector import GameState, PCSX2State
from metadata.metadata_manager import GameInfo
from utils.config import PresenceConfig
from utils.logger import logger

# Small image shown in the corner — PS2 logo Discord asset key
_PS2_SMALL_IMAGE = "ps2_logo"
_PS2_SMALL_TEXT = "PlayStation 2"

# Default large image when no cover is found — a PS2 themed asset
_DEFAULT_LARGE_IMAGE = "ps2_default"
_DEFAULT_LARGE_TEXT = "PlayStation 2"

# State strings
_STATE_PLAYING = "In Game"
_STATE_PAUSED = "Paused"
_STATE_BOOTING = "Loading..."
_STATE_BIOS = "At BIOS"
_STATE_IDLE = "Idle"


@dataclass
class PresencePayload:
    """Hashable snapshot of a Discord presence payload for diffing."""
    details: str | None
    state: str | None
    large_image: str | None
    large_text: str | None
    small_image: str | None
    small_text: str | None
    start: int | None
    buttons: list[dict[str, str]] = field(default_factory=list, compare=False)

    def to_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self.details:
            kwargs["details"] = self.details
        if self.state:
            kwargs["state"] = self.state
        if self.large_image:
            kwargs["large_image"] = self.large_image
        if self.large_text:
            kwargs["large_text"] = self.large_text
        if self.small_image:
            kwargs["small_image"] = self.small_image
        if self.small_text:
            kwargs["small_text"] = self.small_text
        if self.start is not None:
            kwargs["start"] = self.start
        if self.buttons:
            kwargs["buttons"] = self.buttons
        return kwargs

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PresencePayload):
            return NotImplemented
        return (
            self.details == other.details
            and self.state == other.state
            and self.large_image == other.large_image
            and self.start == other.start
        )

    def __hash__(self) -> int:
        return hash((self.details, self.state, self.large_image, self.start))


class PresenceBuilder:
    """
    Builds and diffs Discord presence payloads.

    The last-sent payload is stored so we can avoid redundant API calls.
    """

    def __init__(self, config: PresenceConfig) -> None:
        self._config = config
        self._last_payload: PresencePayload | None = None

    def build(
        self,
        game_state: GameState,
        game_info: GameInfo | None = None,
    ) -> PresencePayload | None:
        """
        Build a PresencePayload from the current GameState and optional GameInfo.

        Returns None if PCSX2 is stopped (caller should clear presence).
        Returns None if the payload is identical to the last sent one.
        """
        payload = self._build_payload(game_state, game_info)

        if payload is None:
            return None

        # Smart diff — suppress update if nothing meaningful changed
        if payload == self._last_payload:
            logger.debug("PresenceBuilder: no change, skipping update")
            return None

        self._last_payload = payload
        return payload

    def force_clear(self) -> None:
        """Reset last payload so the next build always triggers an update."""
        self._last_payload = None

    def _build_payload(
        self,
        game_state: GameState,
        game_info: GameInfo | None,
    ) -> PresencePayload | None:
        cfg = self._config

        if game_state.state == PCSX2State.STOPPED:
            return None

        # ── Details (top line) ────────────────────────────────────────────────
        if cfg.privacy_mode:
            details = "Playing a PS2 game"
        elif cfg.custom_details:
            details = cfg.custom_details
        else:
            title = (game_info.title if game_info else None) or game_state.display_title
            if game_state.state == PCSX2State.IDLE:
                details = "In the PS2 BIOS"
            else:
                details = f"Playing {title}"

        # ── State (second line) ───────────────────────────────────────────────
        if cfg.custom_state:
            state_str = cfg.custom_state
        else:
            state_map = {
                PCSX2State.IDLE: _STATE_BIOS,
                PCSX2State.BOOTING: _STATE_BOOTING,
                PCSX2State.PLAYING: _STATE_PLAYING,
                PCSX2State.PAUSED: _STATE_PAUSED,
            }
            state_str = state_map.get(game_state.state, _STATE_PLAYING)

        # ── Large image (cover art) ───────────────────────────────────────────
        large_image = _DEFAULT_LARGE_IMAGE
        large_text = _DEFAULT_LARGE_TEXT

        if cfg.show_cover_art and not cfg.privacy_mode and game_info:
            if game_info.cover_url:
                large_image = game_info.cover_url
                large_text = game_info.title or game_state.display_title
                if game_info.year:
                    large_text += f" ({game_info.year})"

        # ── Timestamp ─────────────────────────────────────────────────────────
        start: int | None = None
        if cfg.show_elapsed_time and game_state.session_start:
            start = int(game_state.session_start)

        # ── Buttons ───────────────────────────────────────────────────────────
        buttons: list[dict[str, str]] = []
        if not cfg.privacy_mode and game_info:
            for btn_cfg in cfg.buttons:
                if not btn_cfg.enabled:
                    continue
                if btn_cfg.label == "View on IGDB" and game_info.igdb_url:
                    buttons.append({"label": "View on IGDB", "url": game_info.igdb_url})
            # Cap at Discord's 2-button limit
            buttons = buttons[:2]

        return PresencePayload(
            details=details,
            state=state_str,
            large_image=large_image,
            large_text=large_text,
            small_image=_PS2_SMALL_IMAGE,
            small_text=_PS2_SMALL_TEXT,
            start=start,
            buttons=buttons,
        )
