"""
Log file parser for PCSX2 game detection.

Parses PCSX2's emulog.txt, which contains lines like:
  [CDVD] Disc ID: SLUS-21548
  [CDVD] Disc type: PS2
  [Boot]  Running...
  (IOP) Game title: God of War II
  [EE] Pausing after 0 frames
  [EE] Resuming emulation.

This is the most reliable detection method — the log always contains the serial.
We tail the file efficiently using aiofiles so we never block the event loop.
"""
from __future__ import annotations

import asyncio
import platform
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import aiofiles

from utils.logger import logger


# ─── Matching patterns ───────────────────────────────────────────────────────

_DISC_ID_RE = re.compile(r"\[CDVD\]\s+Disc ID:\s*(?P<serial>[A-Z]{2,4}[-_]\d{3,5}(?:\.\d{1,2})?)", re.IGNORECASE)
_GAME_TITLE_RE = re.compile(r"(?:Game title|ELF).*?:\s*(?P<title>.+)", re.IGNORECASE)
_BOOT_RE = re.compile(r"\[Boot\]\s+Running\.\.\.", re.IGNORECASE)
_CDVD_NONE_RE = re.compile(r"\[CDVD\]\s+Disc ID:\s*(?:none|-)", re.IGNORECASE)
_PAUSE_RE = re.compile(r"\[EE\].*Paus(?:ing|ed)", re.IGNORECASE)
_RESUME_RE = re.compile(r"\[EE\].*Resum(?:ing|ed)", re.IGNORECASE)
_RESET_RE = re.compile(r"(?:VM|System)\s+Reset|Shutting down", re.IGNORECASE)


@dataclass
class LogState:
    """Mutable state parsed from the emulog so far."""
    serial: str | None = None
    game_title: str | None = None
    booting: bool = False
    paused: bool = False
    no_disc: bool = False
    # track file read position
    _file_position: int = field(default=0, repr=False, compare=False)


def _default_log_path() -> Path | None:
    """Return the platform default path for PCSX2's emulog.txt."""
    if sys.platform == "win32":
        appdata = Path.home() / "AppData" / "Roaming"
        candidates = [
            appdata / "PCSX2" / "logs" / "emulog.txt",
            appdata / "PCSX2" / "emulog.txt",
            # PCSX2 Qt portable mode puts logs next to the exe — can't detect easily
        ]
    else:
        home = Path.home()
        candidates = [
            home / ".config" / "PCSX2" / "logs" / "emulog.txt",
            home / "snap" / "pcsx2" / "current" / ".config" / "PCSX2" / "logs" / "emulog.txt",
        ]

    for p in candidates:
        if p.exists():
            logger.debug("Found emulog at: {}", p)
            return p

    logger.debug("No emulog found in default locations")
    return None


def _parse_line(line: str, state: LogState) -> None:
    """Mutate state based on a single log line."""
    if _RESET_RE.search(line):
        logger.debug("Log: system reset detected")
        state.serial = None
        state.game_title = None
        state.booting = False
        state.paused = False
        state.no_disc = False
        return

    if _CDVD_NONE_RE.search(line):
        state.serial = None
        state.no_disc = True
        return

    m = _DISC_ID_RE.search(line)
    if m:
        raw = m.group("serial").upper().replace("_", "-")
        state.serial = raw
        state.no_disc = False
        logger.debug("Log: disc ID detected: {}", raw)
        return

    m2 = _GAME_TITLE_RE.search(line)
    if m2 and state.serial:  # only set title once we have a serial
        title = m2.group("title").strip()
        if title and title.lower() not in ("none", "-", ""):
            state.game_title = title
            logger.debug("Log: game title detected: {}", title)
        return

    if _BOOT_RE.search(line):
        state.booting = True
        state.paused = False
        return

    if _PAUSE_RE.search(line):
        state.paused = True
        return

    if _RESUME_RE.search(line):
        state.paused = False
        return


class LogParser:
    """
    Async PCSX2 emulog tail parser.

    Call `read_new_lines()` on each poll cycle to process any new lines
    appended since the last call. Maintains a running LogState.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self._path: Path | None = log_path or _default_log_path()
        self.state = LogState()
        self._position: int = 0
        self._initialized = False

    @property
    def log_path(self) -> Path | None:
        return self._path

    def set_log_path(self, path: Path) -> None:
        self._path = path
        self._position = 0
        self._initialized = False
        self.state = LogState()

    async def _seek_to_end(self) -> None:
        """On first run, jump to the current end of file to avoid replaying history."""
        if not self._path or not self._path.exists():
            return
        async with aiofiles.open(self._path, "r", encoding="utf-8", errors="replace") as f:
            await f.seek(0, 2)  # seek to end
            self._position = await f.tell()
        self._initialized = True
        logger.debug("LogParser: seeked to end of emulog (pos={})", self._position)

    async def full_scan(self) -> None:
        """
        Scan the entire log from the beginning to reconstruct the current state.
        Called once at startup so we pick up games that were already running.
        """
        if not self._path or not self._path.exists():
            return
        logger.debug("LogParser: full scan of emulog")
        try:
            async with aiofiles.open(self._path, "r", encoding="utf-8", errors="replace") as f:
                async for line in f:
                    _parse_line(line.rstrip(), self.state)
                self._position = await f.tell()
        except OSError as exc:
            logger.warning("LogParser: can't open emulog: {}", exc)
        self._initialized = True

    async def read_new_lines(self) -> bool:
        """
        Read any new lines appended since the last call.
        Returns True if any new lines were processed.
        """
        if not self._path:
            # Try to auto-detect on each poll (PCSX2 might not have been open yet)
            self._path = _default_log_path()
            if not self._path:
                return False

        if not self._path.exists():
            return False

        if not self._initialized:
            await self.full_scan()
            return False

        processed = False
        try:
            async with aiofiles.open(self._path, "r", encoding="utf-8", errors="replace") as f:
                # Handle log rotation — if file is now smaller than our position, reset
                await f.seek(0, 2)
                end = await f.tell()
                if end < self._position:
                    logger.info("LogParser: emulog was rotated/truncated — resetting position")
                    self.state = LogState()
                    self._position = 0

                await f.seek(self._position)
                async for line in f:
                    _parse_line(line.rstrip(), self.state)
                    processed = True
                self._position = await f.tell()
        except OSError as exc:
            logger.warning("LogParser: read error: {}", exc)

        return processed
