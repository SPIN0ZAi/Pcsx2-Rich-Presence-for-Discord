"""
Unified game detection façade.

Chains detection methods in priority order:
  1. Log parser  → most reliable (has serial + title from PCSX2 internals)
  2. Window title → reliable backup (serial + title from Qt window)
  3. Process monitor → only tells us if PCSX2 is alive/dead

Implements a debounce mechanism to avoid flickering when PCSX2 briefly
reports an intermediate state (e.g. disc loading, BIOS animation).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from detection.log_parser import LogParser, LogState
from detection.process_monitor import is_pcsx2_running
from detection.window_title import detect_from_window
from utils.logger import logger


class PCSX2State(Enum):
    """Overall emulator state."""
    STOPPED = auto()   # PCSX2 not running
    IDLE = auto()      # Running, no game loaded (BIOS / menu)
    BOOTING = auto()   # Game loading / BIOS boot
    PLAYING = auto()   # In-game, running normally
    PAUSED = auto()    # Emulation paused


@dataclass(frozen=True)
class GameState:
    """Snapshot of the current game state at a point in time."""
    state: PCSX2State
    serial: str | None = None      # e.g. "SLUS-21548"
    game_title: str | None = None  # e.g. "God of War II"
    session_start: float | None = None  # Unix timestamp when game started

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GameState):
            return NotImplemented
        # session_start intentionally excluded from equality checks
        return (
            self.state == other.state
            and self.serial == other.serial
            and self.game_title == other.game_title
        )

    def __hash__(self) -> int:
        return hash((self.state, self.serial, self.game_title))

    @property
    def display_title(self) -> str:
        return self.game_title or self.serial or "Unknown Game"

    @property
    def is_in_game(self) -> bool:
        return self.state in (PCSX2State.PLAYING, PCSX2State.PAUSED, PCSX2State.BOOTING)


class Detector:
    """
    Async game state detector.

    Usage:
        detector = Detector(config)
        await detector.initialize()
        while True:
            state = await detector.poll()
            ...
            await asyncio.sleep(config.pcsx2.poll_interval_seconds)
    """

    DEBOUNCE_SECONDS = 3.0  # Wait this long before committing a state change

    def __init__(
        self,
        process_name: str = "pcsx2",
        log_path: Path | None = None,
        poll_interval: int = 5,
    ) -> None:
        self._process_name = process_name
        self._poll_interval = poll_interval
        self._log_parser = LogParser(log_path)
        self._current_state = GameState(state=PCSX2State.STOPPED)
        self._pending_state: GameState | None = None
        self._pending_since: float = 0.0
        self._session_start: float | None = None

    async def initialize(self) -> None:
        """Perform startup scan of log to recover existing game state."""
        logger.info("Detector: initialising (full log scan)...")
        await self._log_parser.full_scan()
        # Synthesise initial state from existing log state
        self._current_state = self._synthesise_state(self._log_parser.state)
        if self._current_state.is_in_game:
            self._session_start = time.time()  # approximate; we don't know exact start
            logger.info("Detector: resumed in-game state: {}", self._current_state)

    def _synthesise_state(self, log_state: LogState) -> GameState:
        """Turn a LogState + process liveness into a GameState."""
        alive = is_pcsx2_running(self._process_name)

        if not alive:
            return GameState(state=PCSX2State.STOPPED)

        if not log_state.serial and not log_state.booting:
            # Running but no disc — try window title as backup
            win = detect_from_window()
            if win and win.serial:
                log_state.serial = win.serial
                if win.game_title and not log_state.game_title:
                    log_state.game_title = win.game_title

        if not log_state.serial:
            return GameState(state=PCSX2State.IDLE)

        if log_state.booting and not log_state.game_title:
            return GameState(
                state=PCSX2State.BOOTING,
                serial=log_state.serial,
                game_title=log_state.game_title,
                session_start=self._session_start,
            )

        if log_state.paused:
            return GameState(
                state=PCSX2State.PAUSED,
                serial=log_state.serial,
                game_title=log_state.game_title,
                session_start=self._session_start,
            )

        return GameState(
            state=PCSX2State.PLAYING,
            serial=log_state.serial,
            game_title=log_state.game_title,
            session_start=self._session_start,
        )

    async def poll(self) -> GameState:
        """
        Read new log lines and compute the current GameState.

        Applies a debounce: a new state must persist for DEBOUNCE_SECONDS
        before it becomes the current state. This prevents flickering during
        disc loading transitions.

        Returns the current (possibly debounced) GameState.
        """
        try:
            await self._log_parser.read_new_lines()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Detector: log read error: {}", exc)

        candidate = self._synthesise_state(self._log_parser.state)

        # If a game starts, record the session start time
        if (candidate.is_in_game and candidate.serial
                and (self._current_state.serial != candidate.serial)):
            self._session_start = time.time()
            logger.info(
                "Detector: new game session started: {} ({})",
                candidate.serial, candidate.game_title or "?"
            )

        # Reset session timer when emulator stops
        if candidate.state == PCSX2State.STOPPED and self._current_state.state != PCSX2State.STOPPED:
            self._session_start = None

        # ── Debounce ──────────────────────────────────────────────────────────
        now = time.monotonic()
        if candidate == self._current_state:
            self._pending_state = None
            return self._current_state

        # New candidate: start or extend debounce timer
        if self._pending_state != candidate:
            self._pending_state = candidate
            self._pending_since = now
            logger.debug("Detector: state change pending: {} → {}", self._current_state, candidate)
            return self._current_state  # Keep old state until debounce expires

        # Debounce elapsed — commit the new state
        if (now - self._pending_since) >= self.DEBOUNCE_SECONDS:
            # Attach session_start to the new state
            committed = GameState(
                state=candidate.state,
                serial=candidate.serial,
                game_title=candidate.game_title,
                session_start=self._session_start,
            )
            logger.info(
                "Detector: state committed: {} → {}", self._current_state.state.name, committed.state.name
            )
            self._current_state = committed
            self._pending_state = None

        return self._current_state

    @property
    def current_state(self) -> GameState:
        return self._current_state

    @property
    def log_path(self) -> Path | None:
        return self._log_parser.log_path
