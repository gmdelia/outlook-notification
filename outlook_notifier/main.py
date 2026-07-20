"""Application entry point."""

from __future__ import annotations

import atexit
import logging
import os
import sys
import threading

from outlook_notifier.browser_session import BrowserSession
from outlook_notifier.cleanup import cleanup_all
from outlook_notifier.config import AppConfig
from outlook_notifier.gui.launch import spawn_gui_module
from outlook_notifier.gui.settings_app import consume_reconnect_request
from outlook_notifier.gui.tray import TrayIcon
from outlook_notifier.notifier import EventNotifier
from outlook_notifier.scheduler import ReminderScheduler
from outlook_notifier.state import ReminderState
from outlook_notifier import subprocess_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class OutlookNotifierApp:
    def __init__(self) -> None:
        self._config = AppConfig.load()
        self._status = "Avvio…"
        self._stop_event = threading.Event()
        self._login_lock = threading.Lock()
        self._scheduler_started = False
        self._events_proc = None
        self._events_sync_lock = threading.Lock()
        self._browser = BrowserSession(self._config.outlook_url)
        self._notifier = EventNotifier(self._config)
        self._state = ReminderState()
        self._scheduler = ReminderScheduler(
            self._config,
            self._browser,
            self._notifier,
            self._state,
            on_status_change=self._set_status,
            stop_event=self._stop_event,
        )
        self._tray = TrayIcon(
            on_open_events=self._open_events,
            on_open_settings=self._open_settings,
            on_sync_now=self._sync_now,
            on_reconnect=self._reconnect,
            on_login=self._login,
            on_quit=self._quit,
            get_status=self._get_status_text,
        )

    def _get_status_text(self) -> str:
        session = self._browser.status()
        if session.user_email:
            return f"{self._status} ({session.user_email})"
        return self._status

    def _set_status(self, message: str) -> None:
        self._status = message
        self._tray.update_tooltip(message)

    def _reload_config(self) -> None:
        new_config = AppConfig.load()
        if new_config.outlook_url != self._config.outlook_url:
            self._browser = BrowserSession(new_config.outlook_url)
            self._scheduler.set_browser(self._browser)
        self._config = new_config

    def _open_settings(self) -> None:
        if self._stop_event.is_set():
            return
        env = os.environ.copy()
        spawn_gui_module("outlook_notifier.gui.settings_app", env=env)

    def _open_events(self) -> None:
        if self._stop_event.is_set():
            return
        if self._events_proc and self._events_proc.poll() is None:
            logger.info("Chiusura finestra eventi precedente per respawn.")
            try:
                self._events_proc.terminate()
                self._events_proc.wait(timeout=2)
            except Exception:
                try:
                    self._events_proc.kill()
                except Exception:
                    pass
        env = os.environ.copy()
        self._events_proc = spawn_gui_module("outlook_notifier.gui.events_app", env=env)
        threading.Thread(target=self._open_events_worker, daemon=True).start()

    def _open_events_worker(self) -> None:
        if not self._events_sync_lock.acquire(blocking=False):
            logger.info("Sincronizzazione eventi già in corso, richiesta ignorata.")
            return
        try:
            if self._stop_event.is_set():
                return
            if not self._browser.has_valid_session():
                with self._login_lock:
                    if self._stop_event.is_set():
                        return
                    returncode = subprocess_registry.run(
                        [sys.executable, "-m", "outlook_notifier.login_app"],
                    )
                if returncode != 0:
                    return
            if self._stop_event.is_set():
                return
            self._reload_config()
            self._scheduler.run_once()
        except Exception as exc:
            logger.error("Apertura eventi: %s", exc)
        finally:
            self._events_sync_lock.release()

    def _login(self) -> None:
        if self._stop_event.is_set():
            return
        with self._login_lock:
            subprocess_registry.spawn([sys.executable, "-m", "outlook_notifier.login_app"])

    def _sync_now(self) -> None:
        self._reload_config()
        threading.Thread(target=self._scheduler.run_once, daemon=True).start()

    def _reconnect(self) -> None:
        self._browser.request_reconnect()
        self._login()

    def _quit(self) -> None:
        if self._stop_event.is_set():
            return
        logger.info("Chiusura applicazione.")
        self._stop_event.set()
        self._scheduler.stop()
        self._notifier.shutdown()
        cleanup_all()

    def _watch_flags(self) -> None:
        while not self._stop_event.is_set():
            if consume_reconnect_request():
                if not self._stop_event.is_set():
                    self._reconnect()
            if self._stop_event.is_set():
                break
            self._reload_config()
            self._stop_event.wait(2)

    def _initial_sync(self) -> None:
        try:
            if self._stop_event.is_set():
                return
            if not self._browser.has_valid_session():
                logger.info("Nessuna sessione valida: avvio login browser…")
                self._set_status("Apertura browser per login…")
                self._notifier.notify(
                    "Outlook Notifier",
                    "Si aprirà il browser per il login. Completa l'accesso a Outlook.",
                    self._config,
                )
                with self._login_lock:
                    if self._stop_event.is_set():
                        return
                    returncode = subprocess_registry.run(
                        [sys.executable, "-m", "outlook_notifier.login_app"],
                    )
                if self._stop_event.is_set():
                    return
                if returncode != 0:
                    self._set_status("Login non completato — usa Login dal menu")
                    return

            if self._stop_event.is_set():
                return
            self._scheduler.run_once()
            self._set_status("Connesso")
        except Exception as exc:
            if self._stop_event.is_set():
                return
            logger.error("Sincronizzazione iniziale fallita: %s", exc)
            self._set_status(f"Login richiesto — usa Login dal menu")

    def _startup(self) -> None:
        self._initial_sync()
        if self._stop_event.is_set():
            return
        if not self._scheduler_started:
            self._scheduler.start()
            self._scheduler_started = True

    def _on_tray_ready(self, _icon) -> None:
        threading.Thread(target=self._watch_flags, daemon=True, name="flags").start()
        threading.Thread(target=self._startup, daemon=True, name="startup").start()

    def run(self) -> None:
        self._tray.run(setup=self._on_tray_ready)


def main() -> None:
    atexit.register(cleanup_all)
    app = OutlookNotifierApp()
    try:
        app.run()
    finally:
        cleanup_all()


if __name__ == "__main__":
    main()
