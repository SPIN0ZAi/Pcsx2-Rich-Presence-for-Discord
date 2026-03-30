"""
launcher.py — Entry point for the PyInstaller single executable.

Handles:
1. First-run setup wizard (GUI)
2. Loading merged config (config.yaml + settings.json)
3. Starting the system tray icon
4. Starting the async background service (main.py)
"""
from __future__ import annotations

import asyncio
import os
import sys

# Ensure root allows imports
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.storage import is_first_run, load_settings, SETTINGS_PATH
from setup_wizard import run_wizard
from tray_icon import TrayApp
from utils.config import init_config, _deep_merge, load_config
from utils.logger import logger, setup_logging
from main import _async_main


def _run_settings() -> None:
    """Open settings.json in the default text editor."""
    import subprocess
    if sys.platform == "win32":
        os.startfile(SETTINGS_PATH)
    else:
        subprocess.run(["xdg-open", str(SETTINGS_PATH)])


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

    # 2. Load merged config (base yaml + user settings.json)
    try:
        base_cfg = load_config()
        user_settings = load_settings()
        
        # Merge the JSON settings over the YAML defaults
        merged_raw = _deep_merge(base_cfg.model_dump(), user_settings)
        
        # Re-validate with Pydantic
        from utils.config import AppConfig
        final_cfg = AppConfig.model_validate(merged_raw)
        
        # Override the global _config
        import utils.config as cfg_module
        cfg_module._config = final_cfg
        logger.info("Merged config loaded successfully from {}", SETTINGS_PATH)

    except Exception as exc:
        logger.error("Failed to load configuration: {}", exc)
        import tkinter.messagebox as mb
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        mb.showerror("Config Error", f"Failed to load settings.json:\n{exc}")
        sys.exit(1)

    # 3. Start the main service in the background event loop
    def _on_quit() -> None:
        logger.info("Quit requested from tray icon.")
        import main
        if hasattr(main, "_shutdown_event"):
            main._shutdown_event.set()
        
        # If running in PyInstaller mode, forcibly exit if needed
        import threading
        threading.Timer(2.0, lambda: os._exit(0)).start()

    tray = TrayApp(on_quit=_on_quit, on_settings=_run_settings)

    try:
        logger.info("Starting system tray icon...")
        tray.run_detached()

        logger.info("Starting async service...")
        asyncio.run(_async_main())

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        tray.stop()
        logger.info("Launcher exited cleanly.")


if __name__ == "__main__":
    run_launcher()
