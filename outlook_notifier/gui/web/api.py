"""Python ↔ JS bridge for pywebview windows."""

from __future__ import annotations

import webbrowser
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import webview

from outlook_notifier import events_store
from outlook_notifier.config import AppConfig, CONFIG_DIR
from outlook_notifier.gui.web.config_form import config_to_dict, form_to_config, validate_and_save
from outlook_notifier.notification_status import demo_calendar_url, get_notification_status
from outlook_notifier.notifier import EventNotifier

RECONNECT_FLAG = CONFIG_DIR / "reconnect_requested"


def request_reconnect() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RECONNECT_FLAG.write_text("1", encoding="utf-8")


def consume_reconnect_request() -> bool:
    if RECONNECT_FLAG.exists():
        RECONNECT_FLAG.unlink(missing_ok=True)
        return True
    return False


def _format_status(data: Optional[dict]) -> str:
    if data is None:
        return "In attesa della prima sincronizzazione…"
    synced = data.get("synced_at")
    try:
        when = datetime.fromisoformat(synced).strftime("%H:%M:%S")
        suffix = f"Ultima sincronizzazione: {when}"
    except (TypeError, ValueError):
        suffix = "Sincronizzato"
    count = len(data.get("events", []))
    return f"{count} eventi · {suffix}"


def _format_title() -> str:
    today = datetime.now().strftime("%A %d %B %Y")
    return f"Eventi di oggi — {today}"


class EventsApi:
    def get_events(self) -> Dict[str, Any]:
        data = events_store.load_events()
        if data is None:
            return {
                "title": _format_title(),
                "status": _format_status(None),
                "synced_at": None,
                "events": [],
                "now": datetime.now().astimezone().isoformat(),
            }
        return {
            "title": _format_title(),
            "status": _format_status(data),
            "synced_at": data.get("synced_at"),
            "events": data.get("events", []),
            "now": datetime.now().astimezone().isoformat(),
        }

    def get_status_text(self) -> str:
        return _format_status(events_store.load_events())

    def open_event(self, url: str) -> Dict[str, Any]:
        link = str(url or "").strip()
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return {"ok": False, "message": "Link evento non valido."}
        try:
            webbrowser.open(link)
        except Exception as exc:
            return {"ok": False, "message": f"Impossibile aprire il browser: {exc}"}
        return {"ok": True, "message": "Evento aperto nel browser."}


class SettingsApi:
    def get_config(self) -> Dict[str, Any]:
        return config_to_dict(AppConfig.load())

    def save_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        ok, message, config = validate_and_save(data or {})
        return {"ok": ok, "message": message, "config": config}

    def request_reconnect(self) -> Dict[str, Any]:
        request_reconnect()
        return {
            "ok": True,
            "message": "Si aprirà il browser per effettuare di nuovo il login.",
        }

    def browse_sound_file(self) -> Dict[str, Any]:
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("Audio (*.wav;*.aiff;*.aif;*.mp3)", "All files (*.*)"),
        )
        if result and len(result) > 0:
            return {"ok": True, "path": result[0]}
        return {"ok": False, "path": ""}

    def test_notification(self) -> Dict[str, Any]:
        try:
            from outlook_notifier.notifier import EventNotifier

            notifier = EventNotifier(AppConfig.load())
            try:
                notifier.send_test()
            finally:
                notifier.shutdown()
            return {
                "ok": True,
                "message": (
                    "Notifica di prova inviata. Se non vedi un banner: "
                    "Impostazioni di Sistema → Notifiche → Script Editor / osascript → Abilita."
                ),
            }
        except Exception as exc:
            return {"ok": False, "message": f"Notifica di prova fallita: {exc}"}

    def close_window(self) -> None:
        if webview.windows:
            webview.windows[0].destroy()

    def get_notification_status(self, data: Dict[str, Any]) -> Dict[str, Any]:
        config = form_to_config(data or {})
        return get_notification_status(config)

    def test_notification(self, data: Dict[str, Any]) -> Dict[str, Any]:
        config = form_to_config(data or {})
        if not config.notifications_enabled:
            return {
                "ok": False,
                "message": "Abilita le notifiche popup per provare.",
            }

        notifier = EventNotifier(config)
        try:
            notifier.notify(
                "Outlook Notifier — Prova",
                "Questa è una notifica di test. Clicca per aprire il calendario Outlook.",
                config,
                url=demo_calendar_url(config),
            )
        finally:
            notifier.shutdown()

        return {"ok": True, "message": "Notifica di test inviata."}
