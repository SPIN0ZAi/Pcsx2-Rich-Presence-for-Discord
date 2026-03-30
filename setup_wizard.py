"""
GUI setup wizard for the standalone executable package.

Prompts the user for their Discord App ID and optionally IGDB keys,
saving them to settings.json in AppData.

Requires tkinter, which is built into Python.
"""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox, ttk

from utils.storage import save_settings


class SetupWizard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PCSX2 Discord Rich Presence - First Run")
        self.geometry("500x380")
        self.resizable(False, False)

        try:
            # Set window icon if running from the executable bundle
            # sys._MEIPASS is creating by PyInstaller
            import os
            icon_path = os.path.join(getattr(sys, "_MEIPASS", os.path.abspath(".")), "assets", "ps2_icon.png")
            if os.path.exists(icon_path):
                img = tk.PhotoImage(file=icon_path)
                self.iconphoto(False, img)
        except Exception:
            pass

        self.style = ttk.Style(self)
        self.style.theme_use("xpnative" if sys.platform == "win32" else "clam")

        self._build_ui()
        self.success = False

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        ttk.Label(
            main_frame,
            text="Welcome to PCSX2 Discord Rich Presence!",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(
            main_frame,
            text="To connect to Discord, you need a free Application ID.\n"
                 "1. Go to discord.com/developers/applications\n"
                 "2. Create a New Application\n"
                 "3. Copy the Application ID and paste it below.",
            wraplength=460,
        ).pack(anchor=tk.W, pady=(0, 20))

        # Discord ID
        ttk.Label(main_frame, text="Discord Application ID (Required):", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)
        self.discord_var = tk.StringVar()
        entry_discord = ttk.Entry(main_frame, textvariable=self.discord_var, width=50)
        entry_discord.pack(anchor=tk.W, pady=(5, 20))
        entry_discord.focus()

        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 20))

        # Optional: IGDB
        ttk.Label(
            main_frame,
            text="Cover Art / IGDB Integration (Optional):",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            main_frame,
            text="Get free keys at dev.twitch.tv/console to show game box art.",
            font=("Segoe UI", 8),
            foreground="gray",
        ).pack(anchor=tk.W, pady=(0, 5))

        igdb_frame = ttk.Frame(main_frame)
        igdb_frame.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(igdb_frame, text="Client ID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.igdb_id_var = tk.StringVar()
        ttk.Entry(igdb_frame, textvariable=self.igdb_id_var, width=40).grid(row=0, column=1, sticky=tk.W, padx=10, pady=2)

        ttk.Label(igdb_frame, text="Client Secret:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.igdb_secret_var = tk.StringVar()
        ttk.Entry(igdb_frame, textvariable=self.igdb_secret_var, width=40, show="*").grid(row=1, column=1, sticky=tk.W, padx=10, pady=2)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_frame, text="Save & Start", command=self._save_and_start, default=tk.ACTIVE).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(btn_frame, text="Quit", command=self.destroy).pack(side=tk.RIGHT)

    def _save_and_start(self) -> None:
        discord_id = self.discord_var.get().strip()

        if not discord_id:
            messagebox.showerror("Error", "Discord Application ID is required.", parent=self)
            return

        if not discord_id.isdigit():
            messagebox.showwarning("Warning", "Discord IDs are usually numbers only. Check if you pasted it correctly.", parent=self)

        settings = {
            "discord": {
                "client_id": discord_id
            },
            "metadata": {}
        }

        igdb_id = self.igdb_id_var.get().strip()
        igdb_secret = self.igdb_secret_var.get().strip()

        if igdb_id and igdb_secret:
            settings["metadata"]["igdb_client_id"] = igdb_id
            settings["metadata"]["igdb_client_secret"] = igdb_secret
        elif igdb_id or igdb_secret:
            messagebox.showwarning(
                "Missing IGDB Key",
                "You provided one IGDB key but not the other. Cover art won't work unless both are provided.",
                parent=self
            )
            # We still save it, they can edit it later

        try:
            save_settings(settings)
            self.success = True
            self.destroy()
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save settings: {e}", parent=self)


def run_wizard() -> bool:
    """Run the Tkinter setup wizard. Returns True if setup completed successfully."""
    app = SetupWizard()
    app.eval('tk::PlaceWindow . center')
    app.mainloop()
    return app.success
