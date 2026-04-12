"""Entry point for the PyInstaller single executable."""
from __future__ import annotations

import asyncio
import os
import sys

# Ensure root allows imports
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.storage import is_first_run, SETTINGS_PATH
from setup_wizard import run_wizard, run_settings_editor
from tray_icon import TrayApp
from utils.logger import logger, setup_logging
from main_unified import _async_main, request_shutdown, request_rescan


def _run_settings() -> None:
    """Open graphical settings editor."""
    try:
        run_settings_editor()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to open settings UI: {}", exc)


def run_launcher() -> None:
    """Main entry point for the desktop executable."""
    setup_logging(level="INFO", file_enabled=True)

    # 1. First-run wizard
    if is_first_run():
        logger.info("First run detected. Starting GUI wizard...")
        success = run_wizard()
        if not success:
            logger.info("Wizard cancelled. Exiting.")
            sys.exit(0)

    logger.info("Config loaded from {}", SETTINGS_PATH)

    # 3. Start the main service in the background event loop
    def _on_quit() -> None:
        logger.info("Quit requested from tray icon.")
        request_shutdown()
        
        # If running in PyInstaller mode, forcibly exit if needed
        import threading
        threading.Timer(2.0, lambda: os._exit(0)).start()

    tray = TrayApp(on_quit=_on_quit, on_settings=_run_settings, on_rescan=request_rescan)

    try:
        try:
            logger.info("Starting system tray icon...")
            tray.run_detached()
        except Exception as tray_err:
            logger.warning("Failed to start tray icon: {}. Running without tray.", tray_err)

        logger.info("Starting async service...")
        asyncio.run(_async_main())

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        try:
            tray.stop()
        except Exception:
            pass
        logger.info("Launcher exited cleanly.")


if __name__ == "__main__":
    run_launcher()
