"""Track which reminders have already been sent."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Set

from outlook_notifier.config import STATE_FILE


class ReminderState:
    def __init__(self, path: Path = STATE_FILE) -> None:
        self._path = path
        self._sent: Set[str] = set()
        self._current_day: str = date.today().isoformat()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._current_day = data.get("day", self._current_day)
            self._sent = set(data.get("sent", []))
        except (json.JSONDecodeError, TypeError):
            self._sent = set()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"day": self._current_day, "sent": sorted(self._sent)}, indent=2),
            encoding="utf-8",
        )

    def reset_if_new_day(self) -> None:
        today = date.today().isoformat()
        if today != self._current_day:
            self._current_day = today
            self._sent.clear()
            self._save()

    def was_sent(self, event_id: str, reminder_minutes: int) -> bool:
        key = f"{event_id}:{reminder_minutes}:{self._current_day}"
        return key in self._sent

    def mark_sent(self, event_id: str, reminder_minutes: int) -> None:
        key = f"{event_id}:{reminder_minutes}:{self._current_day}"
        self._sent.add(key)
        self._save()
