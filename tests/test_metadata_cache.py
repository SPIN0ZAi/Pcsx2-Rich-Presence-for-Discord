"""
Tests for the metadata cache module.
"""
from __future__ import annotations

import time
import pytest
from pathlib import Path

from metadata.cache import MetadataCache, CachedGame


def _sample_entry(serial: str = "SLUS-21548") -> CachedGame:
    return CachedGame(
        serial=serial,
        title="God of War II",
        cover_url="https://images.igdb.com/test.jpg",
        igdb_id=12345,
        igdb_url="https://www.igdb.com/games/god-of-war-ii",
        summary="Test summary",
        year=2007,
        region="USA",
        source="igdb",
        fetched_at=time.time(),
    )


@pytest.fixture
async def cache(tmp_path: Path) -> MetadataCache:
    """Fresh in-memory-style cache backed by a temp file."""
    c = MetadataCache(db_path=tmp_path / "test_cache.db", ttl_days=7)
    await c.open()
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_cache_miss_returns_none(cache: MetadataCache):
    result = await cache.get("SLUS-99999")
    assert result is None


@pytest.mark.asyncio
async def test_cache_hit_within_ttl(cache: MetadataCache):
    entry = _sample_entry()
    await cache.put(entry)
    result = await cache.get(entry.serial)
    assert result is not None
    assert result.title == "God of War II"
    assert result.source == "igdb"


@pytest.mark.asyncio
async def test_cache_miss_after_ttl_expired(cache: MetadataCache):
    entry = _sample_entry()
    # Set fetched_at to way in the past
    entry = CachedGame(**{**entry.__dict__, "fetched_at": time.time() - 8 * 86400})
    await cache.put(entry)

    result = await cache.get(entry.serial)
    assert result is None  # TTL is 7 days, entry is 8 days old


@pytest.mark.asyncio
async def test_get_stale_returns_expired_entry(cache: MetadataCache):
    entry = _sample_entry()
    entry = CachedGame(**{**entry.__dict__, "fetched_at": time.time() - 8 * 86400})
    await cache.put(entry)

    stale = await cache.get_stale(entry.serial)
    assert stale is not None
    assert stale.title == "God of War II"


@pytest.mark.asyncio
async def test_put_overwrites_existing(cache: MetadataCache):
    entry = _sample_entry()
    await cache.put(entry)

    updated = CachedGame(**{**entry.__dict__, "title": "Updated Title", "source": "screenscraper"})
    await cache.put(updated)

    result = await cache.get(entry.serial)
    assert result is not None
    assert result.title == "Updated Title"


@pytest.mark.asyncio
async def test_invalidate_forces_miss(cache: MetadataCache):
    entry = _sample_entry()
    await cache.put(entry)

    await cache.invalidate(entry.serial)
    result = await cache.get(entry.serial)
    assert result is None  # fetched_at reset to 0, TTL check fails
