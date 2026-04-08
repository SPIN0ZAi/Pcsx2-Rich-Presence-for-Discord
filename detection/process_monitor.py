"""
Process monitor for supported emulators.

Supports:
  - PCSX2
  - RPCS3
  - DuckStation
"""
from __future__ import annotations

import sys
import ctypes
import ctypes.wintypes
from dataclasses import dataclass

import psutil
from utils.logger import logger


@dataclass(frozen=True, slots=True)
class EmulatorProcess:
    emulator_key: str
    emulator_name: str
    pid: int
    process_name: str
    create_time: float
    window_title: str | None
    is_foreground: bool


EMULATOR_PROCESS_NAMES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "pcsx2": ("pcsx2", "PCSX2", ("pcsx2.exe", "pcsx2-qt.exe", "pcsx2-avx2.exe", "pcsx2")),
    "rpcs3": ("rpcs3", "RPCS3", ("rpcs3.exe", "rpcs3")),
    "duckstation": ("duckstation", "DuckStation", ("duckstation.exe", "duckstation-qt.exe", "duckstation")),
}


def _get_window_title_by_pid_windows(pid: int) -> str | None:
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None

        window_pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value != pid:
            return None

        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return None

        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, len(buf))
        title = buf.value.strip()
        if title:
            return title
    except Exception:
        return None
    return None


def _is_pid_foreground_windows(pid: int) -> bool:
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return False
        window_pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        return window_pid.value == pid
    except Exception:
        return False


class ProcessMonitor:
    """Scans running emulator processes and provides prioritised candidates."""

    def scan(self) -> list[EmulatorProcess]:
        running: list[EmulatorProcess] = []

        for proc in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                name = (proc.info.get("name") or "").lower()
                for key, (_, display_name, names) in EMULATOR_PROCESS_NAMES.items():
                    if name in names or any(n in name for n in names):
                        if "rpc" in name and key == "pcsx2":
                            continue
                        running.append(
                            EmulatorProcess(
                                emulator_key=key,
                                emulator_name=display_name,
                                pid=proc.pid,
                                process_name=proc.info.get("name") or name,
                                create_time=float(proc.info.get("create_time") or 0.0),
                                window_title=(
                                    _get_window_title_by_pid_windows(proc.pid)
                                    if sys.platform == "win32"
                                    else None
                                ),
                                is_foreground=(
                                    _is_pid_foreground_windows(proc.pid)
                                    if sys.platform == "win32"
                                    else False
                                ),
                            )
                        )
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as exc:  # noqa: BLE001
                logger.debug("Process scan skipped one process: {}", exc)

        return running

    def pick_active(self, running: list[EmulatorProcess]) -> EmulatorProcess | None:
        if not running:
            return None

        foreground = [p for p in running if p.is_foreground]
        pool = foreground or running

        # Most recently launched wins
        pool.sort(key=lambda p: p.create_time, reverse=True)
        return pool[0]


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
