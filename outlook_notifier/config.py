"""Config persistence for Outlook Calendar Notifier."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

CONFIG_DIR = Path.home() / ".outlook-notifier"
CONFIG_FILE = CONFIG_DIR / "config.json"
BROWSER_PROFILE_DIR = CONFIG_DIR / "browser_profile"
STATE_FILE = CONFIG_DIR / "state.json"
EVENTS_FILE = CONFIG_DIR / "events_today.json"


def detect_local_timezone() -> str:
    """Best-effort IANA timezone name (e.g. 'Europe/Rome')."""
    p = Path("/etc/localtime")
    try:
        if p.is_symlink():
            target = os.readlink(p)
            if "zoneinfo/" in target:
                return target.split("zoneinfo/")[-1]
    except OSError:
        pass
    return os.environ.get("TZ") or "UTC"


@dataclass
class AppConfig:
    outlook_url: str = "https://outlook.office.com"
    poll_interval_minutes: int = 5
    reminder_minutes: List[int] = field(default_factory=lambda: [15, 5])
    notifications_enabled: bool = True
    sound_enabled: bool = True
    sound_file: str = ""
    all_day_reminder_time: str = "09:00"
    notify_all_day_events: bool = True
    timezone: str = ""
    show_events_on_startup: bool = True

    @classmethod
    def load(cls) -> "AppConfig":
        if not CONFIG_FILE.exists():
            return cls()
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return cls(
                outlook_url=data.get("outlook_url", cls.outlook_url),
                poll_interval_minutes=int(data.get("poll_interval_minutes", 5)),
                reminder_minutes=[
                    int(x) for x in data.get("reminder_minutes", [15, 5])
                ],
                notifications_enabled=bool(data.get("notifications_enabled", True)),
                sound_enabled=bool(data.get("sound_enabled", True)),
                sound_file=data.get("sound_file", ""),
                all_day_reminder_time=data.get("all_day_reminder_time", "09:00"),
                notify_all_day_events=bool(data.get("notify_all_day_events", True)),
                timezone=data.get("timezone", ""),
                show_events_on_startup=bool(data.get("show_events_on_startup", True)),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def reminder_minutes_sorted(self) -> List[int]:
        return sorted({m for m in self.reminder_minutes if m > 0}, reverse=True)

    def effective_reminder_minutes(self) -> List[int]:
        """Configured advance reminders plus always-on reminder at event start (0 min)."""
        return sorted({*self.reminder_minutes, 0}, reverse=True)

    def effective_timezone(self) -> str:
        return self.timezone or detect_local_timezone()
