@echo off
REM Start the Discord RPC background service quietly
start "" "pcsx2-rpc\pcsx2-rpc.exe"

REM Start PCSX2 normally
start "" "pcsx2-qt.exe"
