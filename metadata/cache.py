"""
SQLite-backed metadata cache with TTL support.

Schema:
  games (
    serial       TEXT PRIMARY KEY,
    title        TEXT,
    cover_url    TEXT,
    igdb_id      INTEGER,
    igdb_url     TEXT,
    summary      TEXT,
    year         INTEGER,
    region       TEXT,
    source       TEXT,   -- 'igdb' | 'screenscraper' | 'gametdb' | 'manual'
    fetched_at   REAL    -- Unix timestamp
  )
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

from utils.logger import logger

_DB_PATH = Path.home() / ".pcsx2rpc" / "cache.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    serial      TEXT PRIMARY KEY,
    title       TEXT,
    cover_url   TEXT,
    igdb_id     INTEGER,
    igdb_url    TEXT,
    summary     TEXT,
    year        INTEGER,
    region      TEXT,
    source      TEXT,
    fetched_at  REAL NOT NULL DEFAULT 0
);
"""


@dataclass
class CachedGame:
    serial: str
    title: str | None
    cover_url: str | None
    igdb_id: int | None
    igdb_url: str | None
    summary: str | None
    year: int | None
    region: str | None
    source: str | None
    fetched_at: float


class MetadataCache:
    """Async SQLite metadata cache."""

    def __init__(self, db_path: Path = _DB_PATH, ttl_days: int = 7) -> None:
        self._db_path = db_path
        self._ttl = ttl_days * 86400  # seconds
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        """Open the database and ensure schema exists."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute(_SCHEMA)
        await self._db.commit()
        logger.debug("MetadataCache: opened DB at {}", self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    def _row_to_cached(self, row: aiosqlite.Row) -> CachedGame:
        return CachedGame(
            serial=row["serial"],
            title=row["title"],
            cover_url=row["cover_url"],
            igdb_id=row["igdb_id"],
            igdb_url=row["igdb_url"],
            summary=row["summary"],
            year=row["year"],
            region=row["region"],
            source=row["source"],
            fetched_at=row["fetched_at"],
        )

    async def get(self, serial: str) -> CachedGame | None:
        """
        Return cached entry if not expired (within TTL).
        Returns None on cache miss OR if TTL expired.
        """
        if not self._db:
            raise RuntimeError("Cache not opened")
        async with self._db.execute(
            "SELECT * FROM games WHERE serial = ?", (serial,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        cached = self._row_to_cached(row)
        age = time.time() - cached.fetched_at
        if age > self._ttl:
            logger.debug("MetadataCache: TTL expired for {} (age={:.0f}s)", serial, age)
            return None
        logger.debug("MetadataCache: hit for {}", serial)
        return cached

    async def get_stale(self, serial: str) -> CachedGame | None:
        """Return cached entry even if TTL is expired (stale-while-revalidate)."""
        if not self._db:
            raise RuntimeError("Cache not opened")
        async with self._db.execute(
            "SELECT * FROM games WHERE serial = ?", (serial,)
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_cached(row) if row else None

    async def put(self, entry: CachedGame) -> None:
        """Insert or replace a cache entry."""
        if not self._db:
            raise RuntimeError("Cache not opened")
        await self._db.execute(
            """
            INSERT OR REPLACE INTO games
                (serial, title, cover_url, igdb_id, igdb_url, summary, year, region, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.serial, entry.title, entry.cover_url,
                entry.igdb_id, entry.igdb_url, entry.summary,
                entry.year, entry.region, entry.source,
                entry.fetched_at or time.time(),
            ),
        )
        await self._db.commit()
        logger.debug("MetadataCache: stored {} (source={})", entry.serial, entry.source)

    async def invalidate(self, serial: str) -> None:
        """Force-expire a specific entry so it gets refetched."""
        if not self._db:
            raise RuntimeError("Cache not opened")
        await self._db.execute(
            "UPDATE games SET fetched_at = 0 WHERE serial = ?", (serial,)
        )
        await self._db.commit()
