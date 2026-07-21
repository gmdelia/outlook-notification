"""Diagnostics for desktop notification capabilities."""

from __future__ import annotations

import platform
from typing import Any, Dict, List

from outlook_notifier.config import AppConfig
from outlook_notifier.notifier import mac_terminal_notifier_path


def demo_calendar_url(config: AppConfig) -> str:
    return f"{config.outlook_url.rstrip('/')}/calendar"


def _backend_info() -> tuple[str, str, bool]:
    system = platform.system()
    if system == "Darwin":
        if mac_terminal_notifier_path():
            return "terminal-notifier", "terminal-notifier", True
        return "osascript", "osascript (fallback)", False

    if system in ("Windows", "Linux"):
        return "desktop-notifier", "desktop-notifier", True

    return "unknown", "sconosciuto", False


def get_notification_status(config: AppConfig) -> Dict[str, Any]:
    backend_key, backend_label, click_supported = _backend_info()
    warnings: List[str] = []

    if platform.system() == "Darwin" and backend_key == "osascript":
        warnings.append(
            "terminal-notifier non trovato. Installa con: brew install terminal-notifier"
        )

    popup_label = "attivi" if config.notifications_enabled else "disattivati"
    sound_label = "attivo" if config.sound_enabled else "disattivo"
    click_label = "sì" if click_supported and config.notifications_enabled else "no"

    lines = [
        f"Backend: {backend_label}",
        f"Popup: {popup_label} · Suono: {sound_label}",
        f"Click apre Outlook: {click_label}",
    ]

    return {
        "platform": platform.system(),
        "backend": backend_key,
        "backend_label": backend_label,
        "popup_enabled": config.notifications_enabled,
        "sound_enabled": config.sound_enabled,
        "click_to_open_supported": click_supported,
        "lines": lines,
        "warnings": warnings,
    }
