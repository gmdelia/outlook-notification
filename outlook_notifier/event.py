"""Calendar event model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    subject: str
    start: datetime
    end: datetime
    location: str = ""
    is_all_day: bool = False
    web_link: str = ""

    @property
    def display_time(self) -> str:
        if self.is_all_day:
            return "Tutto il giorno"
        return f"{self.start.strftime('%H:%M')} – {self.end.strftime('%H:%M')}"
