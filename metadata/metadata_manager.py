"""
MetadataManager — unified metadata orchestrator.

Priority chain (first hit wins):
  1. SQLite cache (within TTL)
  2. IGDB (by serial external lookup, then title search)
  3. ScreenScraper.fr (by serial)
  4. GameTDB (local XML/TSV, offline)
  5. Bare minimum info from detection (serial only)

Implements stale-while-revalidate: if a stale cache entry exists, return it
immediately and trigger a background refresh.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import aiohttp

from metadata.cache import MetadataCache, CachedGame
from metadata.game_id import normalise_serial, get_region
from metadata.igdb import IGDBClient
from metadata.screenscraper import ScreenScraperClient
from metadata.gametdb import GameTDBParser
from utils.logger import logger


@dataclass
class GameInfo:
    """Fully-resolved game metadata ready for Discord Rich Presence."""
    serial: str
    title: str
    cover_url: str | None        # HTTPS URL usable directly in Discord large_image
    igdb_url: str | None         # Link for Discord button
    summary: str | None
    year: int | None
    region: str | None
    source: str                  # Where the data came from


_DEFAULT_COVER = "ps2_default"   # Discord asset key or URL for the default PS2 cover


class MetadataManager:
    """
    Async metadata manager. Must be used as an async context manager
    or have open() / close() called explicitly.
    """

    def __init__(
        self,
        igdb_client_id: str = "",
        igdb_client_secret: str = "",
        screenscraper_username: str = "",
        screenscraper_password: str = "",
        gametdb_path: Path | None = None,
        cache_ttl_days: int = 7,
    ) -> None:
        self._cache = MetadataCache(ttl_days=cache_ttl_days)
        self._igdb = IGDBClient(igdb_client_id, igdb_client_secret)
        self._scraper = ScreenScraperClient(screenscraper_username, screenscraper_password)
        self._gametdb = GameTDBParser(gametdb_path)
        self._http: aiohttp.ClientSession | None = None
        self._pending_fetches: set[str] = set()

    async def open(self) -> None:
        await self._cache.open()
        self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        self._gametdb.load()

    async def close(self) -> None:
        await self._cache.close()
        await self._igdb.close()
        await self._scraper.close()
        if self._http and not self._http.closed:
            await self._http.close()

    async def __aenter__(self) -> "MetadataManager":
        await self.open()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def get(self, raw_serial: str, title_hint: str | None = None) -> GameInfo:
        """
        Resolve full GameInfo for a PS2 serial.
        
        Returns a GameInfo immediately (possibly from cache or minimal info),
        and kicks off a background fetch if the cache is stale/missing.
        """
        serial = normalise_serial(raw_serial) or raw_serial.upper()

        # ── 1. Cache hit (fresh) ──────────────────────────────────────────────
        cached = await self._cache.get(serial)
        if cached:
            return self._cached_to_game_info(cached)

        # ── 2. Cache hit (stale) — return immediately, refresh in background ──
        stale = await self._cache.get_stale(serial)
        if stale and serial not in self._pending_fetches:
            logger.debug("MetadataManager: stale cache for {} — background refresh", serial)
            self._pending_fetches.add(serial)
            asyncio.create_task(
                self._fetch_and_cache(serial, title_hint),
                name=f"meta_refresh_{serial}",
            )
            return self._cached_to_game_info(stale)

        # ── 3. Full fetch (blocking for first-time lookups) ───────────────────
        if serial not in self._pending_fetches:
            self._pending_fetches.add(serial)
            info = await self._fetch_and_cache(serial, title_hint)
            self._pending_fetches.discard(serial)
            return info

        # Serial is already being fetched — return minimal info for now
        return self._minimal_info(serial, title_hint)

    async def _fetch_and_cache(self, serial: str, title_hint: str | None) -> GameInfo:
        """Fetch from APIs in priority order and store in cache."""
        info: GameInfo | None = None

        # ── IGDB ──────────────────────────────────────────────────────────────
        try:
            igdb_game = await self._igdb.search_by_serial(serial, title_hint)
            if igdb_game:
                logger.info("MetadataManager: IGDB match for {} → {}", serial, igdb_game.title)
                info = GameInfo(
                    serial=serial,
                    title=igdb_game.title,
                    cover_url=igdb_game.cover_url,
                    igdb_url=igdb_game.igdb_url,
                    summary=igdb_game.summary,
                    year=igdb_game.year,
                    region=get_region(serial),
                    source="igdb",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MetadataManager: IGDB failed for {}: {}", serial, exc)

        # ── ScreenScraper ─────────────────────────────────────────────────────
        if not info:
            try:
                sg = await self._scraper.search_by_serial(serial)
                if sg:
                    logger.info("MetadataManager: ScreenScraper match for {} → {}", serial, sg.title)
                    info = GameInfo(
                        serial=serial,
                        title=sg.title,
                        cover_url=sg.cover_url,
                        igdb_url=None,
                        summary=None,
                        year=sg.year,
                        region=sg.region or get_region(serial),
                        source="screenscraper",
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("MetadataManager: ScreenScraper failed for {}: {}", serial, exc)

        # ── GameTDB ───────────────────────────────────────────────────────────
        if not info:
            entry = self._gametdb.lookup(serial)
            if entry:
                logger.info("MetadataManager: GameTDB match for {} → {}", serial, entry.title)
                info = GameInfo(
                    serial=serial,
                    title=entry.title,
                    cover_url=None,
                    igdb_url=None,
                    summary=None,
                    year=None,
                    region=entry.region or get_region(serial),
                    source="gametdb",
                )

        # ── Fallback: title_hint or serial only ───────────────────────────────
        if not info:
            logger.warning("MetadataManager: no metadata found for {}", serial)
            info = self._minimal_info(serial, title_hint)

        # ── Cache result ──────────────────────────────────────────────────────
        await self._cache.put(CachedGame(
            serial=serial,
            title=info.title,
            cover_url=info.cover_url,
            igdb_id=None,
            igdb_url=info.igdb_url,
            summary=info.summary,
            year=info.year,
            region=info.region,
            source=info.source,
            fetched_at=time.time(),
        ))

        self._pending_fetches.discard(serial)
        return info

    def _cached_to_game_info(self, c: CachedGame) -> GameInfo:
        return GameInfo(
            serial=c.serial,
            title=c.title or c.serial,
            cover_url=c.cover_url,
            igdb_url=c.igdb_url,
            summary=c.summary,
            year=c.year,
            region=c.region,
            source=c.source or "cache",
        )

    def _minimal_info(self, serial: str, title_hint: str | None) -> GameInfo:
        return GameInfo(
            serial=serial,
            title=title_hint or serial,
            cover_url=None,
            igdb_url=None,
            summary=None,
            year=None,
            region=get_region(serial),
            source="unknown",
        )
