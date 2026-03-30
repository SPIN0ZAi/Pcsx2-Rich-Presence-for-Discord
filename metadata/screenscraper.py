"""
ScreenScraper.fr API client — secondary metadata source.

Docs: https://www.screenscraper.fr/webapi.php
Free tier: ~20 000 calls/day (unauthenticated), more with an account.

We only use it when IGDB has no result.
"""
from __future__ import annotations

from dataclasses import dataclass

import aiohttp

from utils.logger import logger
from utils.retry import retry

_BASE = "https://www.screenscraper.fr/api2"
_SYSTEM_ID = 57  # PS2 system ID on ScreenScraper


@dataclass
class ScraperGame:
    title: str
    cover_url: str | None
    year: int | None
    region: str | None


class ScreenScraperClient:
    """Lightweight async ScreenScraper API client."""

    def __init__(
        self,
        username: str = "",
        password: str = "",
        devid: str = "pcsx2rpc",
        devpassword: str = "pcsx2rpc",
    ) -> None:
        self._username = username
        self._password = password
        self._devid = devid
        self._devpassword = devpassword
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=12),
            )
        return self._session

    @retry(max_attempts=2, backoff=3.0, exceptions=(aiohttp.ClientError, TimeoutError))
    async def search_by_serial(self, serial: str) -> ScraperGame | None:
        """Search ScreenScraper by PS2 serial (romnom / crc)."""
        session = await self._get_session()
        params: dict[str, str] = {
            "devid": self._devid,
            "devpassword": self._devpassword,
            "softname": "pcsx2rpc",
            "output": "json",
            "ssid": self._username,
            "sspassword": self._password,
            "systemeid": str(_SYSTEM_ID),
            "romnom": serial,
        }
        url = f"{_BASE}/jeuInfos.php"
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 404:
                    logger.debug("ScreenScraper: no result for {}", serial)
                    return None
                if resp.status == 430:
                    logger.warning("ScreenScraper: API quota exceeded")
                    return None
                if resp.status != 200:
                    logger.debug("ScreenScraper: HTTP {} for {}", resp.status, serial)
                    return None
                data = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            logger.debug("ScreenScraper: request failed: {}", exc)
            return None

        return self._parse(data)

    def _parse(self, data: dict) -> ScraperGame | None:
        try:
            jeu = data["response"]["jeu"]
        except (KeyError, TypeError):
            return None

        # Title: prefer 'en' region, then 'ss' (ScreenScraper default)
        title: str | None = None
        noms = jeu.get("noms", [])
        for nom in noms:
            if nom.get("region") in ("en", "us"):
                title = nom.get("text")
                break
        if not title and noms:
            title = noms[0].get("text")

        if not title:
            return None

        # Cover: prefer 'mixrbv2' (box front mixed), then 'box-2D'
        cover_url: str | None = None
        medias = jeu.get("medias", [])
        preferred_types = ("mixrbv2", "box-2D", "box-2D-back")
        for pref in preferred_types:
            for media in medias:
                if media.get("type") == pref and media.get("url"):
                    cover_url = media["url"]
                    break
            if cover_url:
                break

        # Year
        year: int | None = None
        dates = jeu.get("dates", [])
        for d in dates:
            val = d.get("text", "")[:4]
            if val.isdigit():
                year = int(val)
                break

        region = jeu.get("regionshortname")

        return ScraperGame(title=title, cover_url=cover_url, year=year, region=region)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
