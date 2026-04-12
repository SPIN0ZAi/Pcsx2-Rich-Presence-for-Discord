from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time
from dataclasses import dataclass

from detection.game_state_extractor import ExtractedGameState, GameStateExtractor
from detection.process_monitor import ProcessMonitor, EmulatorProcess
from discord_rpc.client import DiscordRPCClient
from discord_rpc.unified_presence import UnifiedPresenceBuilder, PresenceOptions
from metadata.metadata_manager import MetadataManager, GameInfo
from utils.logger import logger, setup_logging
from utils.storage import load_settings

_shutdown_event: asyncio.Event
_rescan_event: asyncio.Event

# Set this to your production Discord Application Client ID to force all users
# to use the same application identity from your build.
PRODUCTION_DISCORD_CLIENT_ID = ""

# Optional production IGDB credentials. If set, they override user settings.
PRODUCTION_IGDB_CLIENT_ID = ""
PRODUCTION_IGDB_CLIENT_SECRET = ""

# Discord application asset name to show when no game is running.
PRODUCTION_IDLE_IMAGE_KEY = "emu_presence_idle"


@dataclass(frozen=True)
class AppRuntimeConfig:
    discord_client_id: str
    igdb_client_id: str
    igdb_client_secret: str
    poll_interval_seconds: int = 5
    clear_delay_seconds: int = 15
    show_notifications: bool = True
    presence_style: str = "minimal"
    show_menu_state: bool = True
    show_paused_state: bool = True
    show_buttons: bool = True
    show_elapsed_time: bool = True
    log_window_titles: bool = False


class MainApp:
    def __init__(self, cfg: AppRuntimeConfig) -> None:
        self._cfg = cfg
        self._monitor = ProcessMonitor()
        self._extractor = GameStateExtractor()
        self._discord = DiscordRPCClient(cfg.discord_client_id)
        self._metadata = MetadataManager(
            igdb_client_id=cfg.igdb_client_id,
            igdb_client_secret=cfg.igdb_client_secret,
        )
        self._presence = UnifiedPresenceBuilder(
            idle_image_key=PRODUCTION_IDLE_IMAGE_KEY.strip(),
            options=PresenceOptions(
                style=cfg.presence_style,
                show_menu_state=cfg.show_menu_state,
                show_paused_state=cfg.show_paused_state,
                show_buttons=cfg.show_buttons,
                show_elapsed_time=cfg.show_elapsed_time,
            ),
        )

        self._last_identity: tuple[str, int, str | None, str | None] | None = None
        self._last_game_info: GameInfo | None = None
        self._stopped_at: float | None = None
        self._discord_warning_shown = False
        self._active_pid: int | None = None

    async def run(self) -> None:
        logger.info("EmuPresence starting...")

        if not self._cfg.discord_client_id:
            logger.error("Discord client_id not configured.")
            return

        async with self._metadata:
            await self._discord.connect()

            while not _shutdown_event.is_set():
                try:
                    await self._tick()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Main loop tick failed: {}", exc)

                try:
                    wait_for = self._cfg.poll_interval_seconds
                    if _rescan_event.is_set():
                        _rescan_event.clear()
                        wait_for = 0
                    await asyncio.wait_for(_shutdown_event.wait(), timeout=wait_for)
                except asyncio.TimeoutError:
                    pass

            await self._discord.clear()
            await self._discord.disconnect()

        logger.info("EmuPresence stopped.")

    async def _tick(self) -> None:
        if not self._discord.is_connected:
            await self._discord.ensure_connected()

        running = self._monitor.scan()
        active = self._select_active_process(running)

        if not active:
            await self._handle_no_emulator()
            return

        self._stopped_at = None
        self._active_pid = active.pid
        extracted = self._extractor.extract(active)
        if self._cfg.log_window_titles:
            logger.debug(
                "Window title [{}:{}]: {}",
                extracted.emulator_name,
                extracted.pid,
                extracted.raw_title or "<empty>",
            )

        current_identity = (
            extracted.emulator_key,
            extracted.pid,
            extracted.serial,
            extracted.title,
        )
        if current_identity != self._last_identity:
            self._last_identity = current_identity
            if extracted.serial is None and extracted.title is None:
                self._last_game_info = None
            else:
                self._last_game_info = await self._fetch_metadata(extracted)

        payload = self._presence.build(extracted, self._last_game_info)
        if payload is None:
            return

        ok = await self._discord.update(**payload.to_kwargs())
        if not ok:
            self._notify_discord_failure_once()

    async def _fetch_metadata(self, extracted: ExtractedGameState) -> GameInfo | None:
        serial = extracted.serial
        if not serial and not extracted.title:
            return None

        try:
            return await self._metadata.get(
                raw_serial=serial or "UNKNOWN",
                title_hint=extracted.title,
                emulator_key=extracted.emulator_key,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Metadata fetch failed for {}: {}", extracted.emulator_name, exc)
            return None

    async def _handle_no_emulator(self) -> None:
        if self._stopped_at is None:
            self._stopped_at = time.monotonic()
            return

        if (time.monotonic() - self._stopped_at) < self._cfg.clear_delay_seconds:
            return

        await self._discord.clear()
        self._presence.force_clear()
        self._last_identity = None
        self._last_game_info = None
        self._active_pid = None

    def _select_active_process(self, running: list[EmulatorProcess]) -> EmulatorProcess | None:
        if not running:
            return None

        # 1) Foreground emulator always wins.
        foreground = [p for p in running if getattr(p, "is_foreground", False)]
        if foreground:
            foreground.sort(key=lambda p: getattr(p, "create_time", 0.0), reverse=True)
            return foreground[0]

        # 2) If current active emulator is still alive, keep it stable.
        if self._active_pid is not None:
            for proc in running:
                if getattr(proc, "pid", None) == self._active_pid:
                    return proc

        # 3) Otherwise, use most recently launched emulator.
        return self._monitor.pick_active(running)

    def _notify_discord_failure_once(self) -> None:
        if self._discord_warning_shown or not self._cfg.show_notifications:
            return

        self._discord_warning_shown = True
        logger.warning("Could not connect to Discord. Please make sure Discord is running.")


def _setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    def _request_shutdown(_: str) -> None:
        _shutdown_event.set()

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGINT, lambda: _request_shutdown("SIGINT"))
        loop.add_signal_handler(signal.SIGTERM, lambda: _request_shutdown("SIGTERM"))


def request_shutdown() -> None:
    if "_shutdown_event" in globals():
        _shutdown_event.set()


def request_rescan() -> None:
    if "_rescan_event" in globals():
        _rescan_event.set()


def _load_runtime_config() -> AppRuntimeConfig:
    cfg = load_settings()
    client_id = PRODUCTION_DISCORD_CLIENT_ID.strip() or str(
        cfg.get("discord", {}).get("client_id", "")
    ).strip()
    igdb_client_id = PRODUCTION_IGDB_CLIENT_ID.strip() or str(
        cfg.get("metadata", {}).get("igdb_client_id", "")
    ).strip()
    igdb_client_secret = PRODUCTION_IGDB_CLIENT_SECRET.strip() or str(
        cfg.get("metadata", {}).get("igdb_client_secret", "")
    ).strip()
    return AppRuntimeConfig(
        discord_client_id=client_id,
        igdb_client_id=igdb_client_id,
        igdb_client_secret=igdb_client_secret,
        poll_interval_seconds=int(cfg.get("app", {}).get("poll_interval_seconds", 5)),
        clear_delay_seconds=int(cfg.get("app", {}).get("clear_delay_seconds", 15)),
        show_notifications=bool(cfg.get("app", {}).get("show_notifications", True)),
        presence_style=str(cfg.get("app", {}).get("presence_style", "minimal")).strip().lower(),
        show_menu_state=bool(cfg.get("app", {}).get("show_menu_state", True)),
        show_paused_state=bool(cfg.get("app", {}).get("show_paused_state", True)),
        show_buttons=bool(cfg.get("app", {}).get("show_buttons", True)),
        show_elapsed_time=bool(cfg.get("app", {}).get("show_elapsed_time", True)),
        log_window_titles=bool(cfg.get("app", {}).get("log_window_titles", False)),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="emupresence",
        description="Unified Discord Rich Presence for PCSX2, RPCS3, and DuckStation",
    )
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")
    return parser.parse_args()


async def _async_main(_: object | None = None) -> None:
    global _shutdown_event
    global _rescan_event

    _shutdown_event = asyncio.Event()
    _rescan_event = asyncio.Event()

    args = _parse_args()
    setup_logging(level="DEBUG" if args.debug else "INFO", file_enabled=True)

    loop = asyncio.get_running_loop()
    _setup_signal_handlers(loop)

    cfg = _load_runtime_config()
    app = MainApp(cfg)
    await app.run()


def cli_entry() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    cli_entry()
