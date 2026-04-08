"""Detection package for PCSX2 Discord Rich Presence."""
from detection.detector import Detector, GameState, PCSX2State
from detection.process_monitor import ProcessMonitor, EmulatorProcess
from detection.game_state_extractor import GameStateExtractor, ExtractedGameState

__all__ = [
	"Detector",
	"GameState",
	"PCSX2State",
	"ProcessMonitor",
	"EmulatorProcess",
	"GameStateExtractor",
	"ExtractedGameState",
]
