"""
Discord RPC client — pypresence AioPresence wrapper.

Handles:
  - Initial connection with exponential backoff
  - Auto-reconnect on pipe disconnect (Discord restart)
  - Rate-limit compliance (min 15s between updates)
  - Clean shutdown
"""
from __future__ import annotations

import asyncio
import time

from pypresence import AioPresence, InvalidPipe, DiscordError, DiscordNotFound

from utils.logger import logger


class DiscordRPCClient:
    """
    Async Discord Rich Presence client.

    Usage:
        client = DiscordRPCClient(client_id="...")
        await client.connect()
        await client.update(details="Playing God of War II", ...)
        await client.disconnect()
    """

    _RECONNECT_DELAYS = [5, 10, 30, 60, 120]   # seconds between reconnect attempts

    def __init__(self, client_id: str) -> None:
        self._client_id = client_id
        self._rpc: AioPresence | None = None
        self._connected = False
        self._last_update: float = 0.0
        self._reconnect_attempt = 0

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """
        Attempt to connect to Discord.
        Returns True on success, False if Discord is not running.
        """
        try:
            self._rpc = AioPresence(self._client_id)
            await self._rpc.connect()
            self._connected = True
            self._reconnect_attempt = 0
            logger.info("Discord RPC: connected (client_id={})", self._client_id[:8] + "...")
            return True
        except DiscordNotFound:
            logger.debug("Discord RPC: Discord not running — will retry later")
            self._rpc = None
            self._connected = False
            return False
        except InvalidPipe:
            logger.debug("Discord RPC: IPC pipe not available — will retry later")
            self._rpc = None
            self._connected = False
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("Discord RPC: unexpected connect error: {}", exc)
            self._rpc = None
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Gracefully disconnect and clear presence."""
        if self._rpc and self._connected:
            try:
                await self._rpc.clear()
                await self._rpc.close()
            except Exception:  # noqa: BLE001
                pass
        self._connected = False
        self._rpc = None
        logger.info("Discord RPC: disconnected")

    async def ensure_connected(self) -> bool:
        """Reconnect if disconnected. Returns True if connection is live."""
        if self._connected and self._rpc:
            return True
        delay_idx = min(self._reconnect_attempt, len(self._RECONNECT_DELAYS) - 1)
        delay = self._RECONNECT_DELAYS[delay_idx]
        self._reconnect_attempt += 1
        logger.debug(
            "Discord RPC: reconnect attempt {} (delay was {}s)", self._reconnect_attempt, delay
        )
        return await self.connect()

    # ── Presence Updates ──────────────────────────────────────────────────────

    async def update(self, **kwargs: object) -> bool:
        """
        Update the Discord Rich Presence.

        Enforces a minimum 15-second interval between calls (Discord limit).
        Returns True on success, False on error/disconnected.
        """
        if not await self.ensure_connected():
            return False

        now = time.monotonic()
        elapsed = now - self._last_update
        min_interval = 15.0
        if elapsed < min_interval:
            wait = min_interval - elapsed
            logger.debug("Discord RPC: rate-limit wait {:.1f}s", wait)
            await asyncio.sleep(wait)

        try:
            await self._rpc.update(**kwargs)  # type: ignore[union-attr]
            self._last_update = time.monotonic()
            logger.info("Discord RPC: presence updated (state={})", kwargs.get("state", "?"))
            return True
        except (InvalidPipe, ConnectionError, BrokenPipeError, OSError):
            logger.warning("Discord RPC: pipe broken — marking as disconnected")
            self._connected = False
            self._rpc = None
            return False
        except DiscordError as exc:
            logger.warning("Discord RPC: API error: {}", exc)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("Discord RPC: unexpected error during update: {}", exc)
            return False

    async def clear(self) -> bool:
        """Clear current presence (show no game playing)."""
        if not self._connected or not self._rpc:
            return True  # already clear
        try:
            await self._rpc.clear()
            self._last_update = time.monotonic()
            logger.info("Discord RPC: presence cleared")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Discord RPC: clear failed: {}", exc)
            self._connected = False
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected
