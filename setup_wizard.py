"""
GUI setup/settings window for the standalone executable package.

- First run: onboarding flow
- Tray settings: edit previously saved values

Discord application client ID is intentionally not user-editable here.
"""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox, ttk

from utils.storage import load_settings, save_settings


class SettingsWindow(tk.Tk):
    def __init__(self, first_run: bool) -> None:
        super().__init__()
        self.first_run = first_run
        self.title("EmuPresence - Setup" if first_run else "EmuPresence - Settings")
        self.geometry("560x430")
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

        self.success = False
        self._build_ui()
        self._load_existing()

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding="16")
        main.pack(fill=tk.BOTH, expand=True)

        title = "Welcome to EmuPresence" if self.first_run else "Settings"
        subtitle = (
            "This build uses the app's built-in Discord Application ID.\n"
            "You can configure optional metadata and app behavior below."
        )

        ttk.Label(main, text=title, font=("Segoe UI", 12, "bold")).pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(main, text=subtitle, wraplength=520).pack(anchor=tk.W, pady=(0, 14))

        ttk.Label(main, text="Discord Application", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)
        ttk.Label(
            main,
            text="Managed by this build (not editable).",
            foreground="gray",
        ).pack(anchor=tk.W, pady=(2, 12))

        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 12))

        ttk.Label(main, text="App Behavior", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)
        appf = ttk.Frame(main)
        appf.pack(fill=tk.X, pady=(6, 14))

        ttk.Label(appf, text="Poll interval (seconds):").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.poll_var = tk.StringVar(value="5")
        ttk.Entry(appf, textvariable=self.poll_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=8)

        ttk.Label(appf, text="Clear delay after close (seconds):").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.clear_var = tk.StringVar(value="15")
        ttk.Entry(appf, textvariable=self.clear_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=8)

        self.notify_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            appf,
            text="Show one-time Discord connection warning",
            variable=self.notify_var,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=6)

        ttk.Label(
            main,
            text="Changes apply after restarting EmuPresence.",
            foreground="gray",
        ).pack(anchor=tk.W, pady=(2, 10))

        btns = ttk.Frame(main)
        btns.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btns, text="Save", command=self._save, default=tk.ACTIVE).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(btns, text="Cancel" if self.first_run else "Close", command=self.destroy).pack(side=tk.RIGHT)

    def _load_existing(self) -> None:
        cfg = load_settings()
        app = cfg.get("app", {})
        self.poll_var.set(str(app.get("poll_interval_seconds", 5)))
        self.clear_var.set(str(app.get("clear_delay_seconds", 15)))
        self.notify_var.set(bool(app.get("show_notifications", True)))

    def _save(self) -> None:
        try:
            poll_interval = int(self.poll_var.get().strip())
            clear_delay = int(self.clear_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid value", "Poll interval and clear delay must be numbers.", parent=self)
            return

        if poll_interval < 1 or poll_interval > 60:
            messagebox.showerror("Invalid value", "Poll interval must be between 1 and 60.", parent=self)
            return

        if clear_delay < 0 or clear_delay > 120:
            messagebox.showerror("Invalid value", "Clear delay must be between 0 and 120.", parent=self)
            return

        payload: dict[str, dict[str, str | int | bool]] = {
            "app": {
                "poll_interval_seconds": poll_interval,
                "clear_delay_seconds": clear_delay,
                "show_notifications": bool(self.notify_var.get()),
            },
        }

        try:
            save_settings(payload)
            self.success = True
            self.destroy()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Save error", f"Failed to save settings:\n{exc}", parent=self)


def _run_window(first_run: bool) -> bool:
    app = SettingsWindow(first_run=first_run)
    app.eval("tk::PlaceWindow . center")
    app.mainloop()
    return app.success


def run_wizard() -> bool:
    """First-run setup flow."""
    return _run_window(first_run=True)


def run_settings_editor() -> bool:
    """Tray settings flow."""
    return _run_window(first_run=False)
