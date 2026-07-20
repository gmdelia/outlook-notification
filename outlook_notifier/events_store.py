"""Persist today's fetched events for the events window (IPC via file)."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from typing import List, Optional

from outlook_notifier.config import CONFIG_DIR, EVENTS_FILE
from outlook_notifier.event import CalendarEvent

logger = logging.getLogger(__name__)


def save_events(events: List[CalendarEvent]) -> None:
    payload = {
        "synced_at": datetime.now().astimezone().isoformat(),
        "day": date.today().isoformat(),
        "events": [
            {
                "id": e.id,
                "subject": e.subject,
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
                "location": e.location,
                "is_all_day": e.is_all_day,
                "web_link": e.web_link,
            }
            for e in events
        ],
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = EVENTS_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp_path, EVENTS_FILE)


def load_events() -> Optional[dict]:
    if not EVENTS_FILE.exists():
        return None
    try:
        data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("Lettura events_today.json fallita: %s", exc)
        return None
    if data.get("day") != date.today().isoformat():
        return None
    return data
