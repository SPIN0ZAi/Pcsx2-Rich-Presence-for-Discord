"""
System tray icon utility using pystray and pillow.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Callable

import pystray
from PIL import Image


class TrayApp:
    def __init__(
        self,
        on_quit: Callable[[], None],
        on_settings: Callable[[], None],
        on_rescan: Callable[[], None],
    ) -> None:
        self.on_quit = on_quit
        self.on_settings = on_settings
        self.on_rescan = on_rescan
        self.icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def _create_image(self) -> Image.Image:
        """Load the PS2 tray icon or generate a fallback solid color block."""
        try:
            base_dir = getattr(sys, "_MEIPASS", os.path.abspath("."))
            icon_path = os.path.join(base_dir, "assets", "ps2_icon.png")
            return Image.open(icon_path)
        except Exception:
            # Fallback icon if asset missing
            img = Image.new("RGBA", (64, 64), color=(26, 26, 46, 255))
            return img

    def run_detached(self) -> None:
        """Start the system tray icon in a separate background thread."""
        image = self._create_image()
        menu = pystray.Menu(
            pystray.MenuItem("EmuPresence is Running", lambda: None, enabled=False),
            pystray.MenuItem("Rescan Now", self._handle_rescan),
            pystray.MenuItem("Settings (Restart required)", self._handle_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._handle_quit),
        )

        self.icon = pystray.Icon("emu-presence", image, "EmuPresence", menu)

        # pystray requires the icon to run in a thread if the main thread 
        # is occupied by the asyncio event loop.
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()

    def _handle_quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self.icon:
            self.icon.stop()
        self.on_quit()

    def _handle_settings(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        # Pystray callbacks run on the tray thread; Settings opens fixing files.
        self.on_settings()

    def _handle_rescan(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.on_rescan()

    def stop(self) -> None:
        """Stop and remove the tray icon."""
        if self.icon:
            self.icon.stop()
