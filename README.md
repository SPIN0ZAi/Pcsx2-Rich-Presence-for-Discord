# EmuPresence

Unified Discord Rich Presence for Windows emulators:

- PCSX2
- RPCS3
- DuckStation

EmuPresence runs quietly in the system tray, detects the active emulator automatically, and updates Discord Rich Presence with game art and state.

## Features

- Auto-detects supported emulator processes
- Parses emulator window titles to identify games
- Fetches cover art through IGDB when available
- Falls back to an emulator icon when no game is running
- Supports minimal/detailed display styles
- Supports menu and paused state indicators
- Supports optional action buttons (IGDB + emulator website)
- Clears Discord presence shortly after the emulator closes
- Ships as a portable Windows `.exe`
- Uses a simple first-run/settings window instead of editing config files

## How it works

1. Launch `EmuPresence.exe`
2. Enter optional metadata settings in the first-run window
3. Keep the app running in the tray
4. Launch PCSX2, RPCS3, or DuckStation
5. Discord updates automatically

When no game is running, EmuPresence shows the emulator context instead of stale game metadata.

## Settings

The tray menu includes a Settings option that opens a GUI window where you can edit:

- Poll interval
- Presence clear delay
- Connection warning toggle

The Discord Application Client ID and production backend identity can be locked into the build by the project owner.

## Discord Application

Discord Rich Presence requires a Discord Application Client ID.

For production builds, the developer can embed a single shared client ID in the app so users do not need to create their own Discord application.

Important:

- The Client ID is public and safe to ship in the app
- Never ship a Discord client secret inside the executable
- If you want your own branding, create a dedicated Discord application and upload the assets there

## Build

Build a Windows release with:

```powershell
.\build_release.ps1
```

The built executable is placed in:

```text
dist\EmuPresence\EmuPresence.exe
```

## Development

Run from source with:

```powershell
python main_unified.py
```

## Notes

- Cover art is best-effort; if IGDB fails, the app still works
- Menu states use emulator imagery instead of stale game art
- Advanced memory-based features are not part of the baseline release
