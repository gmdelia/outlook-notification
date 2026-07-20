"""Standalone today's-events window (pywebview / WebKit)."""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

import webview

from outlook_notifier.config import CONFIG_DIR, EVENTS_FILE
from outlook_notifier.gui.web.api import EventsApi

UI_ERRORS_FILE = CONFIG_DIR / "ui-errors.log"
GUI_PROBE_FILE = CONFIG_DIR / "gui_probe.json"
STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"
EVENTS_HTML = STATIC_DIR / "events.html"


def _log_ui_error(prefix: str, exc: Exception) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(UI_ERRORS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{prefix}: {exc}\n")
        f.write(traceback.format_exc())
        f.write("\n")


def _write_probe(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GUI_PROBE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _probe(api: EventsApi) -> None:
    payload = api.get_events()
    events = payload.get("events", [])
    status = payload.get("status", "")
    _write_probe(
        {
            "app": "events",
            "engine": "pywebview",
            "events": len(events),
            "title": payload.get("title", ""),
            "status": status,
            "status_nonempty": bool(str(status).strip()),
            "html_exists": EVENTS_HTML.exists(),
            "cache_present": EVENTS_FILE.exists(),
        }
    )


def run_events_app(probe: bool = False) -> None:
    api = EventsApi()
    if probe:
        try:
            _probe(api)
        except Exception as exc:
            _log_ui_error("events_app_probe", exc)
            _write_probe(
                {
                    "app": "events",
                    "engine": "pywebview",
                    "error": str(exc),
                    "events": 0,
                    "status_nonempty": False,
                }
            )
            raise SystemExit(1) from exc
        return

    try:
        webview.create_window(
            "Outlook — Eventi di oggi",
            url=EVENTS_HTML.resolve().as_uri(),
            js_api=api,
            width=560,
            height=680,
            min_size=(420, 480),
        )
        webview.start()
    except Exception as exc:
        _log_ui_error("events_app", exc)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    run_events_app(probe=args.probe)
