"""
IGDB (Internet Game Database) API client.

IGDB is powered by Twitch, so auth is OAuth2 client credentials.
Credentials: https://dev.twitch.tv/console → Create an App → copy Client ID + Secret.

API docs: https://api-docs.igdb.com/
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import aiohttp

from utils.logger import logger
from utils.retry import retry

_TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_IGDB_BASE = "https://api.igdb.com/v4"
_PS2_PLATFORM_ID = 8  # IGDB platform ID for PlayStation 2


@dataclass
class IGDBGame:
    igdb_id: int
    title: str
    cover_url: str | None
    summary: str | None
    year: int | None
    igdb_url: str | None


class IGDBClient:
    """Async IGDB client with token caching and retry."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expires: float = 0.0
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Accept": "application/json"},
            )
        return self._session

    async def _ensure_token(self) -> None:
        """Obtain/refresh the Twitch OAuth2 access token."""
        if self._token and time.time() < self._token_expires - 60:
            return

        session = await self._get_session()
        params = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "client_credentials",
        }
        async with session.post(_TWITCH_TOKEN_URL, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        self._token = data["access_token"]
        self._token_expires = time.time() + data["expires_in"]
        logger.debug("IGDBClient: token refreshed (expires in {}s)", data["expires_in"])

    @retry(max_attempts=3, backoff=2.0, exceptions=(aiohttp.ClientError, TimeoutError))
    async def _query(self, endpoint: str, body: str) -> list[dict]:
        """Run a raw IGDB APIv4 query."""
        await self._ensure_token()
        session = await self._get_session()
        headers = {
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "text/plain",
        }
        url = f"{_IGDB_BASE}/{endpoint}"
        async with session.post(url, headers=headers, data=body) as resp:
            if resp.status == 401:
                # Token expired mid-session — force re-auth
                self._token = None
                raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=401)
            resp.raise_for_status()
            return await resp.json()

    async def search_by_serial(self, serial: str, title_hint: str | None = None) -> IGDBGame | None:
        """
        Search IGDB for a PS2 game by serial code.

        Strategy:
          1. Try exact keyword search on the serial in the game's external_games (uid field)
          2. Fall back to title search if title_hint is provided
        """
        if not self._client_id or not self._client_secret:
            return None

        # First try: search external_games table (most accurate)
        if not serial.startswith("UNKNOWN"):
            result = await self._search_by_external_serial(serial)
            if result:
                return result

        # Second try: title keyword search restricted to PS2
        if title_hint:
            result = await self._search_by_title(title_hint)
            if result:
                return result

        return None

    async def _search_by_external_serial(self, serial: str) -> IGDBGame | None:
        """Look up by external_games.uid (PS2 serial stored by IGDB)."""
        # IGDB stores PS2 serials without hyphens sometimes; try both
        serial_variants = [serial, serial.replace("-", "")]
        for variant in serial_variants:
            try:
                body = (
                    f'fields game,uid; where uid = "{variant}" & category = 11;'
                )
                rows = await self._query("external_games", body)
                if rows:
                    game_id = rows[0].get("game")
                    if game_id:
                        return await self._fetch_game_by_id(game_id)
            except Exception as exc:  # noqa: BLE001
                logger.debug("IGDBClient: external_games lookup failed: {}", exc)
        return None

    async def _search_by_title(self, title: str) -> IGDBGame | None:
        """Search by game title, restricted to PS2 platform."""
        try:
            body = (
                f'search "{title}"; '
                f"fields id,name,summary,first_release_date,url,cover.*; "
                f"where platforms = ({_PS2_PLATFORM_ID}); "
                f"limit 1;"
            )
            rows = await self._query("games", body)
            if rows:
                return self._parse_game_row(rows[0])
        except Exception as exc:  # noqa: BLE001
            logger.debug("IGDBClient: title search failed: {}", exc)
        return None

    async def _fetch_game_by_id(self, game_id: int) -> IGDBGame | None:
        """Fetch full game info by IGDB game ID."""
        try:
            body = (
                f"fields id,name,summary,first_release_date,url,cover.*; "
                f"where id = {game_id};"
            )
            rows = await self._query("games", body)
            if rows:
                return self._parse_game_row(rows[0])
        except Exception as exc:  # noqa: BLE001
            logger.debug("IGDBClient: game ID fetch failed: {}", exc)
        return None

    def _parse_game_row(self, row: dict) -> IGDBGame:
        cover = row.get("cover")
        cover_url: str | None = None
        if isinstance(cover, dict):
            image_id = cover.get("image_id")
            if image_id:
                # 720p cover (t_720p)
                cover_url = f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"

        year: int | None = None
        ts = row.get("first_release_date")
        if ts:
            from datetime import datetime, timezone
            year = datetime.fromtimestamp(ts, tz=timezone.utc).year

        return IGDBGame(
            igdb_id=row["id"],
            title=row.get("name", ""),
            cover_url=cover_url,
            summary=row.get("summary"),
            year=year,
            igdb_url=row.get("url"),
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
