"""
Async retry decorator with exponential backoff.

Usage:
    from utils.retry import retry

    @retry(max_attempts=3, backoff=2.0, exceptions=(aiohttp.ClientError,))
    async def fetch_data():
        ...
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, Type, Tuple

from utils.logger import logger


def retry(
    max_attempts: int = 3,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    jitter: float = 0.1,
) -> Callable:
    """
    Async retry decorator with exponential backoff and optional jitter.

    Args:
        max_attempts: Maximum number of total attempts (including first).
        backoff:      Backoff multiplier (seconds). 1st retry = backoff^1, 2nd = backoff^2, ...
        exceptions:   Tuple of exception types to retry on.
        jitter:       Random fraction of delay added to prevent thundering herd.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        logger.warning(
                            "{} failed after {} attempts: {}",
                            func.__qualname__, max_attempts, exc,
                        )
                        raise
                    delay = (backoff ** attempt) + (jitter * backoff * attempt)
                    logger.debug(
                        "{} attempt {}/{} failed ({}). Retrying in {:.1f}s.",
                        func.__qualname__, attempt, max_attempts, exc, delay,
                    )
                    await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
