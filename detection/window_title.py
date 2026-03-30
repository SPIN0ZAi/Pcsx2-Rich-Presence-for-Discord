"""
Window title parser for PCSX2 game detection.

PCSX2-Qt window title formats observed across versions:
  "PCSX2 Qt 2.x | God of War II [SCES-55474] | 60 FPS"
  "PCSX2 1.6.0 | God of War II [SCES-55474]"
  "PCSX2"  (idle, no game loaded)

We parse these with progressively less strict regexes.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

from utils.logger import logger


@dataclass(frozen=True, slots=True)
class WindowInfo:
    raw_title: str
    serial: str | None
    game_title: str | None
    fps: int | None


# Matches:  "... | God of War II [SCES-55474] | 60 FPS"
_FULL_RE = re.compile(
    r"\|\s*(?P<title>.+?)\s*\[(?P<serial>[A-Z]{2,4}[-_]\d{3,5}(?:\.\d{1,2})?)\]"
    r"(?:\s*\|\s*(?P<fps>\d+)\s*FPS)?",
    re.IGNORECASE,
)

# Broader fallback — just extract a serial anywhere in the title
_SERIAL_RE = re.compile(
    r"\b(?P<serial>[A-Z]{2,4}[-_]\d{3,5}(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)


def _get_pcsx2_window_title_windows() -> str | None:
    """Use Win32 API to find and read the PCSX2 window title."""
    try:
        found_titles: list[str] = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.wintypes.HWND,
            ctypes.wintypes.LPARAM,
        )

        def callback(hwnd: int, _: int) -> bool:
            buf = ctypes.create_unicode_buffer(512)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value
            if title and "pcsx2" in title.lower():
                found_titles.append(title)
            return True

        ctypes.windll.user32.EnumWindows(EnumWindowsProc(callback), 0)
        if found_titles:
            logger.debug("PCSX2 window title: {}", found_titles[0])
            return found_titles[0]
    except Exception as exc:  # noqa: BLE001
        logger.debug("Win32 window enumeration failed: {}", exc)
    return None


def _get_pcsx2_window_title_linux() -> str | None:
    """Use xdotool (subprocess) to find PCSX2 window title on Linux."""
    import subprocess
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", "pcsx2", "--sync", "--onlyvisible"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        wid = result.stdout.strip().split()[0]
        result2 = subprocess.run(
            ["xdotool", "getwindowname", wid],
            capture_output=True, text=True, timeout=2,
        )
        title = result2.stdout.strip()
        if title:
            logger.debug("PCSX2 window title (xdotool): {}", title)
            return title
    except Exception as exc:  # noqa: BLE001
        logger.debug("xdotool window lookup failed: {}", exc)
    return None


def get_pcsx2_window_title() -> str | None:
    """Platform-agnostic call to fetch the PCSX2 window title."""
    if sys.platform == "win32":
        return _get_pcsx2_window_title_windows()
    return _get_pcsx2_window_title_linux()


def parse_window_title(title: str) -> WindowInfo:
    """Parse a PCSX2 window title string into structured WindowInfo."""
    m = _FULL_RE.search(title)
    if m:
        serial_raw = m.group("serial").upper().replace("_", "-")
        fps_str = m.group("fps")
        return WindowInfo(
            raw_title=title,
            serial=serial_raw,
            game_title=m.group("title").strip(),
            fps=int(fps_str) if fps_str else None,
        )

    # Fallback: just get the serial
    m2 = _SERIAL_RE.search(title)
    if m2:
        return WindowInfo(
            raw_title=title,
            serial=m2.group("serial").upper().replace("_", "-"),
            game_title=None,
            fps=None,
        )

    return WindowInfo(raw_title=title, serial=None, game_title=None, fps=None)


def detect_from_window() -> WindowInfo | None:
    """
    Attempt to read the PCSX2 window title and parse it.
    Returns None if PCSX2 is not running or no window found.
    """
    title = get_pcsx2_window_title()
    if not title:
        return None
    return parse_window_title(title)
