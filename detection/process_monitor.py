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
import re
from dataclasses import dataclass

import psutil
from utils.logger import logger


_SERIAL_HINT_RE = re.compile(r"\[[A-Z0-9_-]{6,}\]", re.IGNORECASE)


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


def _infer_emulator_key_from_title(title: str) -> str | None:
    lower = title.lower()
    if "rpcs3" in lower:
        return "rpcs3"
    if "duckstation" in lower:
        return "duckstation"
    if "pcsx2" in lower:
        return "pcsx2"
    return None


def _get_window_title_by_pid_windows(pid: int) -> str | None:
    candidates: list[tuple[str, int]] = []

    def _score(title: str, is_foreground: bool) -> int:
        lower = title.lower().strip()
        score = 0
        if is_foreground:
            score += 100
        if _SERIAL_HINT_RE.search(title):
            score += 60
        if "|" in title:
            score += 20
        if "rpcs3" in lower or "duckstation" in lower or "pcsx2" in lower:
            score -= 10
        if lower in {"rpcs3", "pcsx2", "duckstation"}:
            score -= 50
        score += min(len(title), 80) // 4
        return score

    foreground_hwnd = 0
    try:
        foreground_hwnd = ctypes.windll.user32.GetForegroundWindow()

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.wintypes.HWND,
            ctypes.wintypes.LPARAM,
        )

        def callback(hwnd: int, _: int) -> bool:
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return True

            window_pid = ctypes.wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value != pid:
                return True

            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True

            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, len(buf))
            title = buf.value.strip()
            if not title:
                return True

            candidates.append((title, _score(title, hwnd == foreground_hwnd)))
            return True

        ctypes.windll.user32.EnumWindows(EnumWindowsProc(callback), 0)
    except Exception:
        return None

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[1], reverse=True)
    selected = candidates[0][0]
    logger.debug("Selected window title for pid {}: {}", pid, selected)
    return selected


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


def _scan_visible_windows_windows() -> list[EmulatorProcess]:
    found: list[EmulatorProcess] = []
    try:
        foreground_hwnd = ctypes.windll.user32.GetForegroundWindow()

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.wintypes.HWND,
            ctypes.wintypes.LPARAM,
        )

        def callback(hwnd: int, _: int) -> bool:
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return True

            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True

            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, len(buf))
            title = buf.value.strip()
            if not title:
                return True

            key = _infer_emulator_key_from_title(title)
            if not key:
                return True

            window_pid = ctypes.wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            pid = int(window_pid.value)
            display_name = EMULATOR_PROCESS_NAMES[key][1]
            try:
                create_time = float(psutil.Process(pid).create_time())
            except Exception:
                create_time = 0.0

            found.append(
                EmulatorProcess(
                    emulator_key=key,
                    emulator_name=display_name,
                    pid=pid,
                    process_name=display_name,
                    create_time=create_time,
                    window_title=title,
                    is_foreground=(hwnd == foreground_hwnd),
                )
            )
            return True

        ctypes.windll.user32.EnumWindows(EnumWindowsProc(callback), 0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Window fallback scan skipped: {}", exc)
    return found


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

        if sys.platform == "win32" and not running:
            running.extend(_scan_visible_windows_windows())

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
