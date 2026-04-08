# Changelog

All notable changes to EmuPresence will be documented in this file.

## [1.0.1] - 2026-04-08

### Added
- Optional diagnostics logging for raw emulator window titles via Settings GUI (helps troubleshoot detection issues)

### Fixed
- **RPCS3**: Prevent stale game titles from showing after quitting a game (now requires valid serial + non-menu state)
- **DuckStation**: Detect in-game titles without serial in window caption
- **DuckStation**: Improved filtering of version strings and menu text to avoid false detections
- **General**: Stronger menu/idle state detection across all emulators

### Improved
- Window title parsing robustness for edge cases in RPCS3 and DuckStation
- More reliable active process selection with foreground + creation-time heuristics

## [1.0.0] - 2026-04-07

### Initial Release
- Unified Discord Rich Presence for PCSX2, RPCS3, and DuckStation
- Auto-detection of emulator processes
- Game detection via window title parsing
- IGDB cover art integration with fallback chain
- Minimal/detailed presence styles
- Menu, paused, and elapsed time state indicators
- Optional action buttons (IGDB + emulator website)
- Tray app with Settings GUI
- First-run setup wizard
- Portable Windows executable
