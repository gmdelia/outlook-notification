"""Standalone settings window (pywebview / WebKit)."""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

import webview

from outlook_notifier.config import CONFIG_DIR
from outlook_notifier.gui.web.api import SettingsApi, consume_reconnect_request, request_reconnect

UI_ERRORS_FILE = CONFIG_DIR / "ui-errors.log"
GUI_PROBE_FILE = CONFIG_DIR / "gui_probe.json"
STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"
SETTINGS_HTML = STATIC_DIR / "settings.html"

# Re-export for main.py
__all__ = ["consume_reconnect_request", "request_reconnect", "run_settings_app"]


def _log_ui_error(prefix: str, exc: Exception) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(UI_ERRORS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{prefix}: {exc}\n")
        f.write(traceback.format_exc())
        f.write("\n")


def _write_probe(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GUI_PROBE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _probe(api: SettingsApi) -> None:
    config = api.get_config()
    fields = [
        "poll_interval_minutes",
        "reminder_minutes",
        "notifications_enabled",
        "sound_enabled",
        "sound_file",
        "notify_all_day_events",
        "all_day_reminder_time",
        "timezone",
        "outlook_url",
    ]
    present = sum(1 for key in fields if key in config)
    _write_probe(
        {
            "app": "settings",
            "engine": "pywebview",
            "fields": present,
            "labels": present,
            "html_exists": SETTINGS_HTML.exists(),
            "title": "Outlook Notifier — Impostazioni",
            "config_keys": list(config.keys()),
        }
    )


def run_settings_app(probe: bool = False) -> None:
    api = SettingsApi()
    if probe:
        try:
            _probe(api)
        except Exception as exc:
            _log_ui_error("settings_app_probe", exc)
            _write_probe(
                {
                    "app": "settings",
                    "engine": "pywebview",
                    "error": str(exc),
                    "fields": 0,
                }
            )
            raise SystemExit(1) from exc
        return

    try:
        webview.create_window(
            "Outlook Notifier — Impostazioni",
            url=SETTINGS_HTML.resolve().as_uri(),
            js_api=api,
            width=520,
            height=700,
            min_size=(420, 520),
        )
        webview.start()
    except Exception as exc:
        _log_ui_error("settings_app", exc)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    run_settings_app(probe=args.probe)
