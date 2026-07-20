"""Tkinter settings window."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from outlook_notifier.config import AppConfig
from outlook_notifier.gui import theme


class SettingsWindow:
    def __init__(
        self,
        root: tk.Tk,
        config: AppConfig,
        on_save: Callable[[AppConfig], None],
        on_reconnect: Callable[[], None],
        get_status: Callable[[], str],
    ) -> None:
        self._root = root
        self._config = config
        self._on_save = on_save
        self._on_reconnect = on_reconnect
        self._get_status = get_status
        self._window: Optional[tk.Misc] = None
        self._standalone = False

    def show(self, standalone: bool = False) -> None:
        self._standalone = standalone

        if not standalone and self._window and self._window.winfo_exists():
            self._window.lift()
            self._window.focus_force()
            return

        self._config = AppConfig.load()

        if standalone:
            self._window = self._root
            self._root.title("Outlook Notifier — Impostazioni")
            self._root.geometry("480x520")
            self._root.resizable(False, False)
            self._root.configure(bg=theme.BG)
            self._root.protocol("WM_DELETE_WINDOW", self._hide)
        else:
            self._window = tk.Toplevel(self._root)
            self._window.title("Outlook Notifier — Impostazioni")
            self._window.geometry("480x520")
            self._window.resizable(False, False)
            self._window.configure(bg=theme.BG)
            self._window.protocol("WM_DELETE_WINDOW", self._hide)

        for child in self._window.winfo_children():
            child.destroy()

        frame = theme.frame(self._window, padx=16, pady=16)
        frame.pack(fill=tk.BOTH, expand=True)

        theme.label(frame, text="Intervallo sincronizzazione (minuti):").pack(anchor=tk.W)
        self._poll_var = tk.StringVar(value=str(self._config.poll_interval_minutes))
        theme.entry(frame, textvariable=self._poll_var).pack(fill=tk.X, pady=(0, 12))

        theme.label(
            frame,
            text="Promemoria prima dell'evento (minuti, separati da virgola):",
        ).pack(anchor=tk.W)
        reminders = ", ".join(str(m) for m in self._config.reminder_minutes)
        self._reminder_var = tk.StringVar(value=reminders)
        theme.entry(frame, textvariable=self._reminder_var).pack(fill=tk.X, pady=(0, 12))

        self._notify_var = tk.BooleanVar(value=self._config.notifications_enabled)
        theme.checkbutton(
            frame,
            text="Abilita notifiche popup",
            variable=self._notify_var,
        ).pack(anchor=tk.W, pady=2)

        self._sound_var = tk.BooleanVar(value=self._config.sound_enabled)
        theme.checkbutton(
            frame,
            text="Abilita suono",
            variable=self._sound_var,
        ).pack(anchor=tk.W, pady=2)

        theme.label(frame, text="File suono personalizzato (opzionale):").pack(anchor=tk.W, pady=(12, 0))
        sound_row = theme.frame(frame)
        sound_row.pack(fill=tk.X, pady=(0, 12))
        self._sound_file_var = tk.StringVar(value=self._config.sound_file)
        theme.entry(sound_row, textvariable=self._sound_file_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        theme.button(sound_row, text="Sfoglia…", command=self._browse_sound).pack(side=tk.LEFT, padx=(8, 0))

        self._all_day_var = tk.BooleanVar(value=self._config.notify_all_day_events)
        theme.checkbutton(
            frame,
            text="Notifica eventi tutto il giorno",
            variable=self._all_day_var,
        ).pack(anchor=tk.W, pady=(8, 2))

        theme.label(frame, text="Orario promemoria eventi tutto il giorno (HH:MM):").pack(anchor=tk.W)
        self._all_day_time_var = tk.StringVar(value=self._config.all_day_reminder_time)
        theme.entry(frame, textvariable=self._all_day_time_var).pack(fill=tk.X, pady=(0, 12))

        theme.label(frame, text="Fuso orario (IANA, es. Europe/Rome):").pack(anchor=tk.W)
        self._timezone_var = tk.StringVar(value=self._config.effective_timezone())
        theme.entry(frame, textvariable=self._timezone_var).pack(fill=tk.X, pady=(0, 12))

        theme.label(frame, text="URL Outlook:").pack(anchor=tk.W)
        self._outlook_url_var = tk.StringVar(value=self._config.outlook_url)
        theme.entry(frame, textvariable=self._outlook_url_var).pack(fill=tk.X, pady=(0, 12))

        self._status_label = theme.label(frame, text=f"Stato: {self._get_status()}")
        self._status_label.pack(anchor=tk.W, pady=(8, 12))

        buttons = theme.frame(frame)
        buttons.pack(fill=tk.X)
        theme.button(buttons, text="Salva", command=self._save).pack(side=tk.LEFT)
        theme.button(buttons, text="Riconnetti", command=self._reconnect).pack(side=tk.LEFT, padx=8)
        theme.button(buttons, text="Chiudi", command=self._hide).pack(side=tk.RIGHT)

        if standalone:
            self._window.update_idletasks()

    def _browse_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleziona file audio",
            filetypes=[
                ("Audio", "*.wav *.aiff *.aif *.mp3"),
                ("Tutti i file", "*.*"),
            ],
        )
        if path:
            self._sound_file_var.set(path)

    def _save(self) -> None:
        try:
            poll = int(self._poll_var.get().strip())
            if poll < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Errore", "Intervallo sincronizzazione non valido.")
            return

        try:
            reminders = [
                int(part.strip())
                for part in self._reminder_var.get().split(",")
                if part.strip()
            ]
            if not reminders:
                raise ValueError
        except ValueError:
            messagebox.showerror("Errore", "Inserisci almeno un valore per i promemoria.")
            return

        time_value = self._all_day_time_var.get().strip()
        if len(time_value.split(":")) != 2:
            messagebox.showerror("Errore", "Formato orario non valido (usa HH:MM).")
            return

        timezone_value = self._timezone_var.get().strip()
        if timezone_value:
            try:
                ZoneInfo(timezone_value)
            except Exception:
                messagebox.showerror(
                    "Errore",
                    "Fuso orario non valido. Usa un nome IANA, es. Europe/Rome.",
                )
                return

        self._config.timezone = timezone_value
        self._config.poll_interval_minutes = poll
        self._config.reminder_minutes = reminders
        self._config.notifications_enabled = self._notify_var.get()
        self._config.sound_enabled = self._sound_var.get()
        self._config.sound_file = self._sound_file_var.get().strip()
        self._config.notify_all_day_events = self._all_day_var.get()
        self._config.all_day_reminder_time = time_value
        self._config.outlook_url = self._outlook_url_var.get().strip() or "https://outlook.office.com"
        self._config.save()
        self._on_save(self._config)
        self._status_label.config(text=f"Stato: {self._get_status()}")
        messagebox.showinfo("Salvato", "Impostazioni salvate.")

    def _reconnect(self) -> None:
        self._on_reconnect()
        self._status_label.config(text=f"Stato: {self._get_status()}")
        messagebox.showinfo(
            "Riconnessione",
            "Si aprirà il browser per effettuare di nuovo il login.",
        )

    def _hide(self) -> None:
        if self._standalone:
            self._root.destroy()
            self._window = None
            return
        if self._window:
            self._window.destroy()
            self._window = None
