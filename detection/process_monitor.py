"""
Process monitor — watches for PCSX2 process alive/dead transitions.

Uses psutil so it works cross-platform (Windows priority).
"""
from __future__ import annotations

import psutil
from utils.logger import logger


def find_pcsx2_process(name_fragment: str = "pcsx2") -> psutil.Process | None:
    """
    Return the first running PCSX2 process, or None if not found.

    Matches any process whose name contains `name_fragment` (case-insensitive).
    Handles AccessDenied gracefully — some processes can't be inspected.
    """
    fragment = name_fragment.lower()
    try:
        for proc in psutil.process_iter(["pid", "name", "status"]):
            try:
                proc_name = (proc.info["name"] or "").lower()
                if fragment in proc_name and "rpc" not in proc_name:
                    logger.debug("Found PCSX2 process: {} (pid={})", proc.info["name"], proc.pid)
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error scanning processes: {}", exc)
    return None


def is_pcsx2_running(name_fragment: str = "pcsx2") -> bool:
    """Return True if PCSX2 is currently running."""
    return find_pcsx2_process(name_fragment) is not None
