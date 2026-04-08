from __future__ import annotations

import re
from dataclasses import dataclass

from detection.process_monitor import EmulatorProcess


@dataclass(frozen=True, slots=True)
class ExtractedGameState:
    emulator_key: str
    emulator_name: str
    pid: int
    title: str | None
    serial: str | None
    process_start: float


class GameStateExtractor:
    """Emulator-specific title/serial parsing based on window captions."""

    _SERIAL_BRACKETS = re.compile(r"[\[(](?P<serial>[A-Z]{3,5}[-_]?\d{4,6})[\])]", re.IGNORECASE)
    _RPCS3_VERSION = re.compile(r"^v?\d+\.\d+\.\d+(?:[-\.][0-9A-Za-z]+)*$", re.IGNORECASE)
    _RPCS3_NOISE = {
        "rpcs3",
        "vulkan",
        "opengl",
        "directx 12",
        "fps",
        "rsx",
        "ppu",
        "spu",
        "compiling shaders",
        "loading",
    }
    _PCSX2_NOISE = {
        "pcsx2",
        "pcsx2 qt",
        "game list",
        "settings",
        "configuration",
        "debugger",
        "about",
    }

    def extract(self, proc: EmulatorProcess) -> ExtractedGameState:
        title = proc.window_title or ""

        if proc.emulator_key == "pcsx2":
            game_title, serial = self._parse_pcsx2(title)
        elif proc.emulator_key == "rpcs3":
            game_title, serial = self._parse_rpcs3(title)
        elif proc.emulator_key == "duckstation":
            game_title, serial = self._parse_duckstation(title)
        else:
            game_title, serial = self._parse_generic(title, proc.emulator_name)

        return ExtractedGameState(
            emulator_key=proc.emulator_key,
            emulator_name=proc.emulator_name,
            pid=proc.pid,
            title=game_title,
            serial=serial,
            process_start=proc.create_time,
        )

    def _parse_pcsx2(self, title: str) -> tuple[str | None, str | None]:
        # Examples:
        # "Gran Turismo 4 (SCUS-97328) [PCSX2]"
        # "PCSX2 Qt 2.x | God of War II [SCES-55474] | 60 FPS"
        serial = self._extract_serial(title)
        parts = [p.strip() for p in title.split("|") if p.strip()]
        for part in parts:
            if "pcsx2" in part.lower() or "fps" in part.lower():
                continue
            cleaned = self._strip_serial(part).strip("- ")
            if cleaned and not self._looks_like_pcsx2_ui_text(cleaned):
                return (cleaned, serial) if serial else (None, None)
        cleaned = self._strip_serial(title)
        if (
            cleaned
            and "pcsx2" not in cleaned.lower()
            and not self._looks_like_pcsx2_ui_text(cleaned)
        ):
            return (cleaned.strip(), serial) if serial else (None, None)
        return None, serial

    def _parse_rpcs3(self, title: str) -> tuple[str | None, str | None]:
        # Example:
        # "RPCS3 v0.0.31-... | Persona 5 [BLUS31604] | Vulkan | 60.00 FPS"
        serial = self._extract_serial(title)
        parts = [p.strip() for p in title.split("|") if p.strip()]
        for part in parts:
            lower = part.lower()
            if (
                "rpcs3" in lower
                or "fps" in lower
                or "vulkan" in lower
                or "opengl" in lower
                or lower in self._RPCS3_NOISE
            ):
                continue
            cleaned = self._strip_serial(part).strip("- ")
            if cleaned and not self._looks_like_rpcs3_version(cleaned):
                return cleaned, serial
        cleaned = self._strip_serial(title)
        if (
            cleaned
            and "rpcs3" not in cleaned.lower()
            and not self._looks_like_rpcs3_version(cleaned)
        ):
            return (cleaned.strip(), serial) if serial else (None, None)
        return None, serial

    def _parse_duckstation(self, title: str) -> tuple[str | None, str | None]:
        # Examples:
        # "DuckStation - Crash Team Racing (SCUS-94426)"
        # "Crash Team Racing [SCUS-94426] - DuckStation"
        serial = self._extract_serial(title)

        cleaned = title.replace("DuckStation", "").replace("duckstation", "")
        cleaned = self._strip_serial(cleaned)
        cleaned = cleaned.replace("--", "-").strip(" -|")
        if cleaned and serial:
            return cleaned, serial
        return None, serial

    def _parse_generic(self, title: str, emulator_name: str) -> tuple[str | None, str | None]:
        serial = self._extract_serial(title)
        cleaned = self._strip_serial(title).replace(emulator_name, "").strip(" -|")
        return (cleaned or None), serial

    def _extract_serial(self, title: str) -> str | None:
        m = self._SERIAL_BRACKETS.search(title)
        if not m:
            return None
        serial = m.group("serial").upper().replace("_", "-")
        if "-" not in serial and len(serial) > 4:
            serial = f"{serial[:4]}-{serial[4:]}"
        return serial

    def _strip_serial(self, text: str) -> str:
        return self._SERIAL_BRACKETS.sub("", text).strip()

    def _looks_like_rpcs3_version(self, text: str) -> bool:
        token = text.strip().lower()
        token = token.removeprefix("rpcs3").strip(" -")
        if not token:
            return True
        if token in self._RPCS3_NOISE:
            return True
        if self._RPCS3_VERSION.match(token):
            return True
        # Common format: "0.0.40-19175-..."
        if token.startswith("0.") and any(ch.isdigit() for ch in token):
            return True
        return False

    def _looks_like_pcsx2_ui_text(self, text: str) -> bool:
        token = text.strip().lower()
        if not token:
            return True
        if token in self._PCSX2_NOISE:
            return True
        if "nightly" in token or "svn" in token or "avx2" in token or "qt" in token:
            return True
        # version-like strings, e.g. 2.3.120, v2.0.0-dev
        if re.match(r"^v?\d+\.\d+(?:\.\d+)?(?:[-\.][0-9a-z]+)*$", token, re.IGNORECASE):
            return True
        return False
