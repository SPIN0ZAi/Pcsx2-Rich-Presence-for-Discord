@echo off
REM Start the Discord RPC background service quietly
start "" "EmuPresence\EmuPresence.exe"

REM Start PCSX2 normally
start "" "pcsx2-qt.exe"
