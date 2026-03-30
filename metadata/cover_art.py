"""
Cover art downloader and processor.

Downloads cover images from URLs, resizes them to 960×960 (IGDB standard size
is already ~600px; Discord asset uploads max at 1024×1024), saves as JPEG.

For rich presence we use URLs directly where supported (Discord supports
external image URLs in large_image as of 2023). Local caching is only for
potential future CloudFlare/Cloudinary re-hosting.
"""
from __future__ import annotations

from pathlib import Path

import aiohttp
from PIL import Image
import io

from utils.logger import logger
from utils.retry import retry

_COVER_DIR = Path.home() / ".pcsx2rpc" / "covers"
_MAX_SIZE = (512, 512)


async def _download_bytes(url: str, session: aiohttp.ClientSession) -> bytes | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.debug("CoverArt: HTTP {} for {}", resp.status, url)
                return None
            return await resp.read()
    except Exception as exc:  # noqa: BLE001
        logger.debug("CoverArt: download failed: {}", exc)
        return None


def _process_image(data: bytes) -> bytes:
    """Open, resize, and re-encode image to JPEG bytes."""
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB")
        img.thumbnail(_MAX_SIZE, Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=90, optimize=True)
        return out.getvalue()


@retry(max_attempts=2, backoff=3.0, exceptions=(aiohttp.ClientError,))
async def fetch_and_cache_cover(
    serial: str,
    url: str,
    session: aiohttp.ClientSession,
) -> Path | None:
    """
    Download a cover image, process it, and cache it locally.
    Returns the local Path on success, None on failure.
    """
    _COVER_DIR.mkdir(parents=True, exist_ok=True)
    dest = _COVER_DIR / f"{serial.lower().replace('-', '_')}.jpg"

    if dest.exists():
        logger.debug("CoverArt: cache hit for {} at {}", serial, dest)
        return dest

    logger.debug("CoverArt: downloading cover for {} from {}", serial, url)
    data = await _download_bytes(url, session)
    if not data:
        return None

    try:
        processed = _process_image(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CoverArt: image processing failed for {}: {}", serial, exc)
        return None

    dest.write_bytes(processed)
    logger.debug("CoverArt: saved cover for {} to {}", serial, dest)
    return dest


def get_cached_cover_path(serial: str) -> Path | None:
    """Return the local cached cover path if it exists."""
    dest = _COVER_DIR / f"{serial.lower().replace('-', '_')}.jpg"
    return dest if dest.exists() else None
