"""Schedule future macOS notifications via launchd (works without .app bundle)."""

from __future__ import annotations

import hashlib
import json
import logging
import plistlib
import platform
import subprocess
import sys
from datetime import date, datetime, time as dt_time, timedelta
from typing import Set

from outlook_notifier.config import CONFIG_DIR, AppConfig
from outlook_notifier.event import CalendarEvent
from outlook_notifier.reminder_content import format_reminder, reminder_identifier

logger = logging.getLogger(__name__)

_LAUNCHD_DIR = CONFIG_DIR / "launchd"
_MANIFEST = CONFIG_DIR / "launchd_jobs.json"
_LABEL_PREFIX = "com.outlook-notifier.reminder."


def is_available() -> bool:
    return platform.system() == "Darwin"


def reschedule(events: list[CalendarEvent], config: AppConfig) -> Set[str]:
    """Replace pending launchd reminders; returns identifiers successfully scheduled."""
    if not is_available() or not config.notifications_enabled:
        _clear_all_jobs()
        return set()

    try:
        return _reschedule(events, config)
    except Exception as exc:
        logger.warning("Schedulazione reminder macOS non disponibile: %s", exc)
        return set()


def _reschedule(events: list[CalendarEvent], config: AppConfig) -> Set[str]:
    _clear_all_jobs()
    _LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now().astimezone()
    scheduled: Set[str] = set()
    labels: list[str] = []

    for event in events:
        if event.is_all_day:
            if not config.notify_all_day_events:
                continue
            ident = _schedule_all_day(event, config, now, labels)
            if ident:
                scheduled.add(ident)
            continue

        for reminder_min in config.reminder_minutes_sorted():
            trigger_at = event.start - timedelta(minutes=reminder_min)
            if trigger_at <= now or now >= event.start:
                continue

            title, body = format_reminder(event, reminder_min, now=trigger_at)
            ident = reminder_identifier(event.id, reminder_min, event.start)
            label = _label_for(ident)
            if _submit_job(label, ident, title, body, trigger_at):
                scheduled.add(ident)
                labels.append(label)

    _MANIFEST.write_text(json.dumps(labels, indent=2), encoding="utf-8")
    if scheduled:
        logger.info("macOS: %d reminder schedulati con launchd", len(scheduled))
    return scheduled


def _schedule_all_day(
    event: CalendarEvent,
    config: AppConfig,
    now: datetime,
    labels: list[str],
) -> str | None:
    try:
        hour, minute = map(int, config.all_day_reminder_time.split(":"))
    except ValueError:
        hour, minute = 9, 0

    trigger_at = datetime.combine(date.today(), dt_time(hour, minute), tzinfo=now.tzinfo)
    if trigger_at <= now or now >= event.end:
        return None

    title, body = format_reminder(event, 0, all_day=True)
    ident = reminder_identifier(event.id, 0, event.start)
    label = _label_for(ident)
    if _submit_job(label, ident, title, body, trigger_at):
        labels.append(label)
        return ident
    return None


def _label_for(ident: str) -> str:
    digest = hashlib.sha256(ident.encode("utf-8")).hexdigest()[:20]
    return f"{_LABEL_PREFIX}{digest}"


def _submit_job(
    label: str,
    ident: str,
    title: str,
    body: str,
    trigger_at: datetime,
) -> bool:
    plist_path = _LAUNCHD_DIR / f"{label}.plist"
    plist = {
        "Label": label,
        "ProgramArguments": [
            sys.executable,
            "-m",
            "outlook_notifier.macos_notify_cli",
            "--label",
            label,
            "--title",
            title,
            "--message",
            body,
        ],
        "StartCalendarInterval": {
            "Month": trigger_at.month,
            "Day": trigger_at.day,
            "Hour": trigger_at.hour,
            "Minute": trigger_at.minute,
        },
        "StandardOutPath": str(CONFIG_DIR / "launchd.log"),
        "StandardErrorPath": str(CONFIG_DIR / "launchd.log"),
    }
    plist_path.write_bytes(plistlib.dumps(plist))
    uid = _gui_uid()
    result = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        logger.error("launchctl bootstrap %s fallito: %s", label, err)
        plist_path.unlink(missing_ok=True)
        return False
    logger.debug("Schedulato %s alle %s", ident, trigger_at.strftime("%H:%M"))
    return True


def _clear_all_jobs() -> None:
    if _MANIFEST.exists():
        try:
            labels = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            labels = []
    else:
        labels = []

    if _LAUNCHD_DIR.exists():
        for plist in _LAUNCHD_DIR.glob("*.plist"):
            labels.append(plist.stem)

    uid = _gui_uid()
    seen: set[str] = set()
    for label in labels:
        if not isinstance(label, str) or label in seen:
            continue
        seen.add(label)
        subprocess.run(
            ["launchctl", "bootout", f"gui/{uid}", label],
            capture_output=True,
            text=True,
        )
        (_LAUNCHD_DIR / f"{label}.plist").unlink(missing_ok=True)

    _MANIFEST.unlink(missing_ok=True)


def _gui_uid() -> int:
    import os

    return os.getuid()
