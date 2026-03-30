"""
PCSX2 Discord Rich Presence — Main Service Entry Point

This is an async service that:
  1. Polls for the running PCSX2 game (log + window + process)
  2. Fetches game metadata (IGDB → ScreenScraper → GameTDB → cache)
  3. Updates Discord Rich Presence accordingly

Run with:
    python main.py
    python main.py --config path/to/config.yaml --debug
"""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time
from pathlib import Path

# ── Ensure project root is on sys.path when running directly ─────────────────
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Local imports (after sys.path fix) ───────────────────────────────────────
from utils.config import init_config, AppConfig
from utils.logger import logger, setup_logging
from detection.detector import Detector, PCSX2State, GameState
from metadata.metadata_manager import MetadataManager, GameInfo
from discord_rpc.client import DiscordRPCClient
from discord_rpc.presence import PresenceBuilder


# ─────────────────────────────────────────────────────────────────────────────
# Shutdown coordination
# ─────────────────────────────────────────────────────────────────────────────
_shutdown_event: asyncio.Event


def _setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Register SIGINT/SIGTERM handlers for clean shutdown."""
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    def _request_shutdown(sig_name: str) -> None:
        logger.info("Received {} — shutting down gracefully...", sig_name)
        _shutdown_event.set()

    if sys.platform != "win32":
        # POSIX: use loop.add_signal_handler (non-blocking)
        loop.add_signal_handler(signal.SIGINT, lambda: _request_shutdown("SIGINT"))
        loop.add_signal_handler(signal.SIGTERM, lambda: _request_shutdown("SIGTERM"))
    else:
        # Windows: KeyboardInterrupt is caught in the main try/except below


        pass


# ─────────────────────────────────────────────────────────────────────────────
# Core service loop
# ─────────────────────────────────────────────────────────────────────────────

class PCSX2RichPresenceService:
    """Main service that ties detection, metadata, and Discord together."""

    def __init__(self, config: AppConfig) -> None:
        self._cfg = config
        self._detector = Detector(
            process_name=config.pcsx2.process_name,
            log_path=config.pcsx2.log_path,
            poll_interval=config.pcsx2.poll_interval_seconds,
        )
        self._metadata = MetadataManager(
            igdb_client_id=config.metadata.igdb_client_id,
            igdb_client_secret=config.metadata.igdb_client_secret,
            screenscraper_username=config.metadata.screenscraper_username,
            screenscraper_password=config.metadata.screenscraper_password,
            gametdb_path=config.metadata.gametdb_path,
            cache_ttl_days=config.metadata.cache_ttl_days,
        )
        self._discord = DiscordRPCClient(config.discord.client_id)
        self._builder = PresenceBuilder(config.presence)

        self._last_serial: str | None = None
        self._current_info: GameInfo | None = None
        self._stopped_at: float | None = None

    async def run(self) -> None:
        """Main service coroutine."""
        logger.info("PCSX2 Discord Rich Presence starting up...")

        # Validate client ID
        if self._cfg.discord.client_id == "YOUR_DISCORD_APP_CLIENT_ID":
            logger.error(
                "Discord client_id is not configured! "
                "Please edit config.yaml (or config.local.yaml) and set discord.client_id."
            )
            return

        async with self._metadata:
            await self._detector.initialize()
            await self._discord.connect()

            poll_interval = self._cfg.pcsx2.poll_interval_seconds
            logger.info(
                "Service running (poll interval={}s). Press Ctrl+C to stop.", poll_interval
            )

            try:
                while not _shutdown_event.is_set():
                    await self._tick()
                    try:
                        await asyncio.wait_for(
                            _shutdown_event.wait(), timeout=poll_interval
                        )
                    except asyncio.TimeoutError:
                        pass
            finally:
                logger.info("Cleaning up...")
                await self._discord.clear()
                await self._discord.disconnect()

        logger.info("PCSX2 Discord Rich Presence stopped.")

    async def _tick(self) -> None:
        """Single poll cycle."""
        game_state = await self._detector.poll()
        await self._handle_state(game_state)

    async def _handle_state(self, game_state: GameState) -> None:
        """React to the current GameState."""
        cfg = self._cfg.presence

        # ── PCSX2 stopped ─────────────────────────────────────────────────────
        if game_state.state == PCSX2State.STOPPED:
            if self._stopped_at is None:
                self._stopped_at = time.monotonic()
                logger.info("PCSX2 not running — will clear presence in {}s", cfg.clear_delay_seconds)

            elapsed_stopped = time.monotonic() - self._stopped_at
            if elapsed_stopped >= cfg.clear_delay_seconds:
                if self._builder._last_payload is not None:
                    await self._discord.clear()
                    self._builder.force_clear()
                    self._last_serial = None
                    self._current_info = None
                    logger.info("Presence cleared (PCSX2 has been closed)")
            return

        # PCSX2 is running — reset stopped timer
        self._stopped_at = None

        # ── Fetch metadata if game changed ────────────────────────────────────
        if game_state.serial and game_state.serial != self._last_serial:
            self._last_serial = game_state.serial
            logger.info("Game changed → fetching metadata for {}", game_state.serial)
            try:
                self._current_info = await self._metadata.get(
                    game_state.serial, game_state.game_title
                )
                logger.info(
                    "Metadata: {} / {} / {} (source: {})",
                    self._current_info.serial,
                    self._current_info.title,
                    self._current_info.cover_url or "no cover",
                    self._current_info.source,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Metadata fetch failed: {}", exc)
                self._current_info = None

        # ── Build + send presence payload ─────────────────────────────────────
        payload = self._builder.build(game_state, self._current_info)
        if payload:
            kwargs = payload.to_kwargs()
            logger.debug("Sending presence: {}", kwargs)
            await self._discord.update(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pcsx2-rpc",
        description="Discord Rich Presence for PCSX2 (PlayStation 2 Emulator)",
    )
    parser.add_argument(
        "--config", "-c",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to config.yaml (default: config.yaml in the project root)",
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable DEBUG log level (overrides config)",
    )
    return parser.parse_args()


async def _async_main() -> None:
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    args = _parse_args()
    config = init_config(args.config)

    log_level = "DEBUG" if args.debug else config.logging.level
    setup_logging(
        level=log_level,
        file_enabled=config.logging.file_enabled,
        rotation_mb=config.logging.rotation_mb,
    )

    loop = asyncio.get_running_loop()
    _setup_signal_handlers(loop)

    service = PCSX2RichPresenceService(config)
    await service.run()


def cli_entry() -> None:
    """Entry point registered in pyproject.toml."""
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    cli_entry()
