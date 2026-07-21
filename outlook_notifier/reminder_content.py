"""Shared reminder title/body text."""

from __future__ import annotations

from datetime import datetime

from outlook_notifier.event import CalendarEvent


def reminder_identifier(event_id: str, reminder_minutes: int, start: datetime) -> str:
    return f"outlook-notifier:{event_id}:{reminder_minutes}:{start.isoformat()}"


def format_reminder(
    event: CalendarEvent,
    reminder_minutes: int,
    *,
    all_day: bool = False,
    now: datetime | None = None,
) -> tuple[str, str]:
    if all_day:
        body = event.display_time
        if event.location:
            body += f"\n{event.location}"
        return f"Oggi: {event.subject}", body

    body = f"Inizia alle {event.start.strftime('%H:%M')}"
    if event.location:
        body += f"\n{event.location}"

    if reminder_minutes <= 0:
        return f"Ora: {event.subject}", body

    display_min = reminder_minutes
    if now is not None:
        remaining = max(0, int((event.start - now).total_seconds() // 60))
        if 0 < remaining < reminder_minutes:
            display_min = remaining

    return f"Tra {display_min} min: {event.subject}", body
