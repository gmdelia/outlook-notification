"""Validation and persistence helpers for the settings form."""

from __future__ import annotations

from typing import Any, Dict, Tuple
from zoneinfo import ZoneInfo

from outlook_notifier import autostart
from outlook_notifier.config import AppConfig


def config_to_dict(config: AppConfig) -> Dict[str, Any]:
    return {
        "start_at_login": autostart.is_enabled(),
        "show_events_on_startup": config.show_events_on_startup,
        "poll_interval_minutes": config.poll_interval_minutes,
        "reminder_minutes": ", ".join(str(m) for m in config.reminder_minutes),
        "notifications_enabled": config.notifications_enabled,
        "sound_enabled": config.sound_enabled,
        "sound_file": config.sound_file,
        "notify_all_day_events": config.notify_all_day_events,
        "all_day_reminder_time": config.all_day_reminder_time,
        "timezone": config.effective_timezone(),
        "outlook_url": config.outlook_url,
    }


def form_to_config(data: Dict[str, Any]) -> AppConfig:
    """Build AppConfig from form values without saving (for notification preview/test)."""
    config = AppConfig.load()
    if not data:
        return config

    config.notifications_enabled = bool(data.get("notifications_enabled", config.notifications_enabled))
    config.sound_enabled = bool(data.get("sound_enabled", config.sound_enabled))
    config.sound_file = str(data.get("sound_file", config.sound_file)).strip()
    outlook_url = str(data.get("outlook_url", config.outlook_url)).strip()
    if outlook_url:
        config.outlook_url = outlook_url
    return config


def validate_and_save(data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """Validate form data, save config, return (ok, message, config_dict)."""
    try:
        poll = int(str(data.get("poll_interval_minutes", "")).strip())
        if poll < 1:
            raise ValueError
    except (TypeError, ValueError):
        return False, "Intervallo sincronizzazione non valido.", {}

    try:
        reminders_raw = str(data.get("reminder_minutes", ""))
        reminders = [
            int(part.strip())
            for part in reminders_raw.split(",")
            if part.strip()
        ]
        if not reminders:
            raise ValueError
    except (TypeError, ValueError):
        return False, "Inserisci almeno un valore per i promemoria.", {}

    time_value = str(data.get("all_day_reminder_time", "")).strip()
    if len(time_value.split(":")) != 2:
        return False, "Formato orario non valido (usa HH:MM).", {}

    timezone_value = str(data.get("timezone", "")).strip()
    if timezone_value:
        try:
            ZoneInfo(timezone_value)
        except Exception:
            return False, "Fuso orario non valido. Usa un nome IANA, es. Europe/Rome.", {}

    config = AppConfig.load()
    config.timezone = timezone_value
    config.poll_interval_minutes = poll
    config.reminder_minutes = reminders
    config.notifications_enabled = bool(data.get("notifications_enabled", True))
    config.sound_enabled = bool(data.get("sound_enabled", True))
    config.sound_file = str(data.get("sound_file", "")).strip()
    config.notify_all_day_events = bool(data.get("notify_all_day_events", True))
    config.all_day_reminder_time = time_value
    config.outlook_url = str(data.get("outlook_url", "")).strip() or "https://outlook.office.com"
    config.show_events_on_startup = bool(data.get("show_events_on_startup", True))
    config.save()

    want_autostart = bool(data.get("start_at_login", False))
    try:
        if want_autostart != autostart.is_enabled():
            autostart.set_enabled(want_autostart)
    except Exception as exc:
        return (
            False,
            f"Impostazioni salvate, ma avvio automatico non aggiornato: {exc}",
            config_to_dict(config),
        )

    return True, "Impostazioni salvate.", config_to_dict(config)
