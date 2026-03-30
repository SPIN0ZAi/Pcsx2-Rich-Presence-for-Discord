"""
Tests for the detection module.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from detection.window_title import parse_window_title, WindowInfo
from detection.log_parser import LogParser, LogState, _parse_line
from detection.detector import Detector, PCSX2State, GameState


# ─── window_title tests ───────────────────────────────────────────────────────

class TestWindowTitleParser:

    def test_full_qt_title(self):
        title = "PCSX2 Qt 2.1.0 | God of War II [SCES-55474] | 60 FPS"
        info = parse_window_title(title)
        assert info.serial == "SCES-55474"
        assert info.game_title == "God of War II"
        assert info.fps == 60

    def test_title_without_fps(self):
        title = "PCSX2 1.6.0 | Shadow of the Colossus [SCES-53245]"
        info = parse_window_title(title)
        assert info.serial == "SCES-53245"
        assert info.game_title == "Shadow of the Colossus"
        assert info.fps is None

    def test_idle_pcsx2_no_game(self):
        title = "PCSX2"
        info = parse_window_title(title)
        assert info.serial is None
        assert info.game_title is None

    def test_serial_with_underscore(self):
        title = "PCSX2 | God of War [SLUS_20717]"
        info = parse_window_title(title)
        # Underscores should be normalised to hyphens
        assert info.serial == "SLUS-20717"

    def test_usa_serial_prefix(self):
        info = parse_window_title("PCSX2 | Ratchet [SCUS-97199]")
        assert info.serial == "SCUS-97199"


# ─── log_parser tests ─────────────────────────────────────────────────────────

class TestLogParser:

    def test_disc_id_extraction(self):
        state = LogState()
        _parse_line("[CDVD] Disc ID: SLUS-21548", state)
        assert state.serial == "SLUS-21548"

    def test_disc_none_clears_serial(self):
        state = LogState(serial="SLUS-21548")
        _parse_line("[CDVD] Disc ID: none", state)
        assert state.serial is None
        assert state.no_disc is True

    def test_boot_line_sets_booting(self):
        state = LogState()
        _parse_line("[Boot] Running...", state)
        assert state.booting is True

    def test_pause_sets_paused(self):
        state = LogState(serial="SLUS-21548")
        _parse_line("[EE] Pausing after 100 frames", state)
        assert state.paused is True

    def test_resume_clears_paused(self):
        state = LogState(serial="SLUS-21548", paused=True)
        _parse_line("[EE] Resuming emulation.", state)
        assert state.paused is False

    def test_reset_clears_all(self):
        state = LogState(serial="SLUS-21548", booting=True, paused=True)
        _parse_line("VM Reset", state)
        assert state.serial is None
        assert state.booting is False
        assert state.paused is False

    def test_game_title_extracted_after_serial(self):
        state = LogState(serial="SLUS-21548")
        _parse_line("(IOP) Game title: God of War II", state)
        assert state.game_title == "God of War II"

    def test_game_title_not_set_without_serial(self):
        state = LogState()
        _parse_line("(IOP) Game title: God of War II", state)
        assert state.game_title is None  # no serial yet

    def test_underscore_serial_normalised(self):
        state = LogState()
        _parse_line("[CDVD] Disc ID: SLUS_215.48", state)
        # Should normalise underscores/dots
        assert state.serial is not None
        assert "_" not in state.serial


# ─── detector debounce tests ──────────────────────────────────────────────────

class TestDetectorDebounce:

    @pytest.mark.asyncio
    async def test_state_not_committed_before_debounce(self):
        """State change should not be committed in the first N seconds."""
        # Patch so PCSX2 appears running
        with patch("detection.detector.is_pcsx2_running", return_value=True):
            with patch("detection.detector.detect_from_window", return_value=None):
                detector = Detector()
                detector._log_parser.state.serial = "SLUS-21548"
                detector._log_parser.state.booting = False
                detector._log_parser._initialized = True

                # First poll — candidate is PLAYING but debounce hasn't expired
                with patch.object(detector._log_parser, "read_new_lines", AsyncMock(return_value=False)):
                    state = await detector.poll()

                # Initial current_state was STOPPED; new candidate PLAYING is pending
                assert state.state == PCSX2State.STOPPED

    @pytest.mark.asyncio
    async def test_stopped_state_when_no_process(self):
        """STOPPED should be returned immediately when PCSX2 is not running."""
        with patch("detection.detector.is_pcsx2_running", return_value=False):
            detector = Detector()
            detector._log_parser._initialized = True
            with patch.object(detector._log_parser, "read_new_lines", AsyncMock(return_value=False)):
                state = await detector.poll()
            assert state.state == PCSX2State.STOPPED


# ─── GameState equality tests ─────────────────────────────────────────────────

class TestGameStateEquality:

    def test_same_serial_same_state_equal(self):
        s1 = GameState(state=PCSX2State.PLAYING, serial="SLUS-21548", session_start=1000.0)
        s2 = GameState(state=PCSX2State.PLAYING, serial="SLUS-21548", session_start=2000.0)
        assert s1 == s2  # session_start excluded from equality

    def test_different_serial_not_equal(self):
        s1 = GameState(state=PCSX2State.PLAYING, serial="SLUS-21548")
        s2 = GameState(state=PCSX2State.PLAYING, serial="SCES-55474")
        assert s1 != s2

    def test_different_state_not_equal(self):
        s1 = GameState(state=PCSX2State.PLAYING, serial="SLUS-21548")
        s2 = GameState(state=PCSX2State.PAUSED, serial="SLUS-21548")
        assert s1 != s2
