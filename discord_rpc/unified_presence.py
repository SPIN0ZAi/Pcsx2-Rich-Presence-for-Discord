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

_DISCORD_STATE_LIMIT = 128
_DISCORD_DETAILS_LIMIT = 128
_DISCORD_LARGE_TEXT_LIMIT = 128
_DISCORD_BUTTON_LABEL_LIMIT = 32

EMULATOR_URLS: dict[str, str] = {
    "pcsx2": "https://pcsx2.net/",
    "rpcs3": "https://rpcs3.net/",
    "duckstation": "https://www.duckstation.org/",
    "cemu": "https://cemu.info/",
    "dolphin": "https://dolphin-emu.org/",
    "ryujinx": "https://ryujinx.org/",
    "suyu": "https://suyu.dev/",
    "yuzu": "https://yuzu-emu.org/",
    "mesen": "https://mesen.ca/",
    "fusion": "https://www.eidolons-inn.net/tiki-index.php?page=KegaFusion",
}


@dataclass(frozen=True)
class UnifiedPresencePayload:
    details: str
    state: str
    large_image: str | None
    large_text: str | None
    start: int | None
    buttons: list[dict[str, str]]

    def to_kwargs(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "details": _truncate(self.details, _DISCORD_DETAILS_LIMIT),
            "state": _truncate(self.state, _DISCORD_STATE_LIMIT),
        }
        if self.large_image:
            out["large_image"] = self.large_image
        if self.large_text:
            out["large_text"] = _truncate(self.large_text, _DISCORD_LARGE_TEXT_LIMIT)
        if self.start is not None:
            out["start"] = self.start
        if self.buttons:
            out["buttons"] = [
                {
                    "label": _truncate(button.get("label", ""), _DISCORD_BUTTON_LABEL_LIMIT),
                    "url": button["url"],
                }
                for button in self.buttons
                if button.get("label") and button.get("url")
            ][:2]
        return out


@dataclass(frozen=True)
class PresenceOptions:
    style: str = "minimal"
    show_menu_state: bool = True
    show_paused_state: bool = True
    show_buttons: bool = True
    show_elapsed_time: bool = True


class UnifiedPresenceBuilder:
    def __init__(
        self,
        idle_image_key: str = DEFAULT_IDLE_IMAGE_KEY,
        options: PresenceOptions | None = None,
    ) -> None:
        self._last_payload: UnifiedPresencePayload | None = None
        self._idle_image_key = idle_image_key
        self._options = options or PresenceOptions()

    def force_clear(self) -> None:
        self._last_payload = None

    def build(self, state: ExtractedGameState, info: GameInfo | None) -> UnifiedPresencePayload | None:
        options = self._options
        game_title = (info.title if info else None) or state.title or self._raw_title_fallback(state)
        cover = (info.cover_url if info else None) or EMULATOR_FALLBACK_IMAGES.get(state.emulator_key)
        is_menu = game_title is None and state.serial is None
        is_paused = bool(options.show_paused_state and state.paused)

        if is_menu:
            state_line = self._menu_state_text(state) if options.show_menu_state else "No game detected"
            large_text = state.emulator_name
        elif is_paused:
            paused_target = game_title or state.serial or "Game"
            state_line = f"Paused {paused_target}"
            large_text = paused_target
        elif game_title:
            state_line = f"Playing {game_title}"
            large_text = game_title
        elif state.serial:
            state_line = f"Playing {state.serial}"
            large_text = state.serial
        else:
            state_line = "In menu / no game detected"
            large_text = state.emulator_name

        if is_menu and self._idle_image_key:
            cover = self._idle_image_key

        if options.style == "detailed":
            details_line = f"{state.emulator_name} — Active"
        else:
            details_line = state.emulator_name

        buttons: list[dict[str, str]] = []
        if options.show_buttons:
            if info and info.igdb_url:
                buttons.append({"label": "View on IGDB", "url": info.igdb_url})
            emu_url = EMULATOR_URLS.get(state.emulator_key)
            if emu_url:
                buttons.append({"label": f"{state.emulator_name} Website", "url": emu_url})
            buttons = buttons[:2]

        payload = UnifiedPresencePayload(
            details=_truncate(details_line, _DISCORD_DETAILS_LIMIT),
            state=_truncate(state_line, _DISCORD_STATE_LIMIT),
            large_image=cover,
            large_text=_truncate(large_text, _DISCORD_LARGE_TEXT_LIMIT),
            start=(int(state.process_start) if (state.process_start and options.show_elapsed_time and not is_menu) else None),
            buttons=buttons,
        )

        if payload == self._last_payload:
            return None

        self._last_payload = payload
        return payload

    def _raw_title_fallback(self, state: ExtractedGameState) -> str | None:
        raw = (state.raw_title or "").strip()
        if not raw:
            return None

        lower = raw.lower()
        if state.emulator_key == "rpcs3":
            if any(marker in lower for marker in ("game list", "settings", "home", "welcome", "firmware", "debugger")):
                return None
        elif state.emulator_key == "duckstation":
            if any(marker in lower for marker in ("game list", "settings", "controller settings", "memory card", "bios", "achievements")):
                return None
        elif state.emulator_key == "pcsx2":
            if any(marker in lower for marker in ("pcsx2", "settings", "game list", "configuration", "debugger", "about")):
                return None

        parts = [part.strip() for part in raw.split("|") if part.strip()]
        for part in parts:
            cleaned = part.replace("DuckStation", "").replace("RPCS3", "").replace("PCSX2", "").strip(" -")
            if cleaned and not cleaned.lower().startswith(("v", "0.")):
                return cleaned

        cleaned = raw.replace("DuckStation", "").replace("RPCS3", "").replace("PCSX2", "").strip(" -|")
        return cleaned or None

    def _menu_state_text(self, state: ExtractedGameState) -> str:
        raw = (state.raw_title or "").lower()

        if state.emulator_key == "rpcs3":
            if "game list" in raw:
                return "At RPCS3 game list"
            if "settings" in raw:
                return "In RPCS3 settings"
            return "In RPCS3 menu"

        if state.emulator_key == "duckstation":
            if "settings" in raw:
                return "In DuckStation settings"
            if "game list" in raw:
                return "At DuckStation game list"
            return "In DuckStation menu"

        if state.emulator_key == "pcsx2":
            if "bios" in raw:
                return "In PCSX2 BIOS"
            return "In PCSX2 menu"

        if state.emulator_key == "cemu":
            if "graphic" in raw or "settings" in raw:
                return "In Cemu settings"
            return "In Cemu menu"

        if state.emulator_key == "dolphin":
            if "settings" in raw:
                return "In Dolphin settings"
            return "In Dolphin menu"

        if state.emulator_key == "ryujinx":
            if "settings" in raw:
                return "In Ryujinx settings"
            return "In Ryujinx menu"

        if state.emulator_key == "suyu":
            if "settings" in raw:
                return "In suyu settings"
            return "In suyu menu"

        if state.emulator_key == "yuzu":
            if "settings" in raw:
                return "In yuzu settings"
            return "In yuzu menu"

        if state.emulator_key == "mesen":
            if "settings" in raw:
                return "In Mesen settings"
            return "In Mesen menu"

        if state.emulator_key == "fusion":
            if "settings" in raw:
                return "In Fusion settings"
            return "In Fusion menu"

        return "In menu"


def _truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    if limit <= 1:
        return stripped[:limit]
    return stripped[: limit - 1].rstrip() + "…"
