from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from detection.game_state_extractor import ExtractedGameState
from metadata.metadata_manager import GameInfo


EMULATOR_FALLBACK_IMAGES: dict[str, str] = {
    "pcsx2": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/77/PCSX2_icon.svg/512px-PCSX2_icon.svg.png",
    "rpcs3": "https://rpcs3.net/cdn/images/logo.png",
    "duckstation": "https://raw.githubusercontent.com/stenzek/duckstation/master/data/resources/images/duckstation.png",
}


DEFAULT_IDLE_IMAGE_KEY = "emu_presence_idle"


@dataclass(frozen=True)
class UnifiedPresencePayload:
    details: str
    state: str
    large_image: str | None
    large_text: str | None
    start: int | None

    def to_kwargs(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "details": self.details,
            "state": self.state,
        }
        if self.large_image:
            out["large_image"] = self.large_image
        if self.large_text:
            out["large_text"] = self.large_text
        if self.start is not None:
            out["start"] = self.start
        return out


class UnifiedPresenceBuilder:
    def __init__(self, idle_image_key: str = DEFAULT_IDLE_IMAGE_KEY) -> None:
        self._last_payload: UnifiedPresencePayload | None = None
        self._idle_image_key = idle_image_key

    def force_clear(self) -> None:
        self._last_payload = None

    def build(self, state: ExtractedGameState, info: GameInfo | None) -> UnifiedPresencePayload | None:
        game_title = (info.title if info else None) or state.title
        cover = (info.cover_url if info else None) or EMULATOR_FALLBACK_IMAGES.get(state.emulator_key)

        if game_title:
            state_line = f"Playing {game_title}"
            large_text = game_title
        elif state.serial:
            state_line = f"Playing {state.serial}"
            large_text = state.serial
        else:
            state_line = "In menu / no game detected"
            large_text = state.emulator_name

        if not game_title and self._idle_image_key:
            cover = self._idle_image_key

        payload = UnifiedPresencePayload(
            details=state.emulator_name,
            state=state_line,
            large_image=cover,
            large_text=large_text,
            start=int(state.process_start) if state.process_start else None,
        )

        if payload == self._last_payload:
            return None

        self._last_payload = payload
        return payload
