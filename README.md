# PCSX2 Discord Rich Presence

> **Production-quality Discord Rich Presence for PCSX2 (PlayStation 2 Emulator)**  
> Displays game title, cover art, playtime, and game state — comparable in quality to RPCS3's built-in integration.

![Discord Rich Presence Preview](https://img.shields.io/badge/Discord-Rich%20Presence-5865F2?logo=discord&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)

---

## ✨ Features

| Feature | Details |
|---|---|
| 🎮 **Game Detection** | Log parsing (primary) + Window title (fallback) + Process monitor |
| 🖼️ **Cover Art** | Fetched from IGDB / ScreenScraper — no manual upload needed |
| 📊 **Rich State** | Playing / Paused / Loading / At BIOS |
| ⏱️ **Playtime** | Per-game session timer |
| 🔗 **IGDB Button** | "View on IGDB" clickable button in presence |
| 🔒 **Privacy Mode** | Hides game title on demand |
| ⚡ **Low CPU** | Async polling, configurable interval, smart diff (no redundant API calls) |
| 💾 **Local Cache** | SQLite cache with 7-day TTL + stale-while-revalidate |
| 🌐 **Multi-source** | IGDB → ScreenScraper → GameTDB XML (offline) fallback chain |

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.10+
- PCSX2 (any recent version)
- Discord (running on the same machine)

### 2. Install Dependencies

```powershell
cd "c:\Users\USER\Pscx2 discord rich presence"
pip install -r requirements.txt
```

### 3. Create a Discord Application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → give it a name like `PCSX2`
3. Upload a PS2 logo as the application icon (shown in Discord as the small image)
4. Go to **Rich Presence → Art Assets** and upload:
   - An asset named **`ps2_logo`** (PS2 logo image)
   - An asset named **`ps2_default`** (fallback cover, e.g. PS2 startup screen)
5. Copy the **Application ID** from the General Information page

### 4. Configure

Create `config.local.yaml` (never committed to git):

```yaml
discord:
  client_id: "YOUR_APPLICATION_ID_HERE"

metadata:
  igdb_client_id: "your_igdb_client_id"
  igdb_client_secret: "your_igdb_client_secret"
```

> **Get IGDB credentials** (free):  
> Go to [dev.twitch.tv/console](https://dev.twitch.tv/console) → Register an app → Copy Client ID + Secret.

### 5. Run

```powershell
python main.py
# With debug logging:
python main.py --debug
```

---

## ⚙️ Configuration Reference

All options are documented in [`config.yaml`](config.yaml). Key options:

```yaml
presence:
  privacy_mode: false        # true → shows "Playing a PS2 game" instead of title
  show_cover_art: true       # false → uses ps2_default image always
  show_elapsed_time: true    # false → no timer shown
  poll_interval_seconds: 5   # how often to check for game changes

metadata:
  cache_ttl_days: 7          # days before re-fetching game info
  gametdb_path: null         # path to PS2db.txt for offline fallback
```

Put secrets (API keys, client ID) in `config.local.yaml` — it's gitignored.

---

## 🏗️ Architecture

```
main.py                   ← Async service entry point
│
├── detection/            ← How we detect the running game
│   ├── log_parser.py     ← Primary: tail PCSX2's emulog.txt
│   ├── window_title.py   ← Fallback: parse PCSX2 window title
│   ├── process_monitor.py← Alive/dead PCSX2 process check
│   └── detector.py       ← Unified façade with 3s debounce
│
├── metadata/             ← Game info & cover art
│   ├── cache.py          ← SQLite cache (7-day TTL)
│   ├── igdb.py           ← IGDB API (primary source)
│   ├── screenscraper.py  ← ScreenScraper.fr (secondary)
│   ├── gametdb.py        ← Offline XML fallback
│   └── metadata_manager.py ← Orchestrates all sources
│
├── discord_rpc/          ← Discord integration
│   ├── client.py         ← pypresence wrapper (auto-reconnect)
│   └── presence.py       ← Payload builder with smart diff
│
└── utils/
    ├── config.py         ← Pydantic v2 config loader
    ├── logger.py         ← Loguru setup
    └── retry.py          ← Async retry decorator
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| **Python + asyncio** | Single thread, event-driven — CPU usage stays < 1% during idle polls |
| **Log parsing as primary** | PCSX2 always writes the serial to its log; more reliable than heuristic window parsing |
| **3-second debounce** | Prevents flickering during disc load transitions (PCSX2 resets/rewrites state briefly) |
| **External URL cover art** | Discord supports external image URLs in `large_image` since 2023 — no manual asset uploads needed |
| **Stale-while-revalidate** | Cache returns stale data immediately and refreshes in background — no visible delay |
| **Pydantic v2 config** | Auto-validation with clear error messages if config is malformed |

---

## 🧪 Running Tests

```powershell
pip install pytest pytest-asyncio pytest-mock
python -m pytest tests/ -v
```

---

## 📋 PCSX2 Log Path Reference

| OS | Default Path |
|---|---|
| Windows | `%APPDATA%\PCSX2\logs\emulog.txt` |
| Linux | `~/.config/PCSX2/logs/emulog.txt` |
| Linux (Snap) | `~/snap/pcsx2/current/.config/PCSX2/logs/emulog.txt` |

If your log is in a non-standard location, set `pcsx2.log_path` in your config.

---

## 🗺️ Roadmap

- [ ] **RetroAchievements integration** — show unlocked achievement count
- [ ] **System tray icon** (Windows) — enable/disable without terminal
- [ ] **PyInstaller packaging** — single `.exe` for non-Python users
- [ ] **Auto-start on Windows login** — via Task Scheduler
- [ ] **Web dashboard** — `localhost:8080` status viewer (FastAPI)

---

## 📄 License

MIT
