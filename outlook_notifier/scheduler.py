"""Poll calendar and trigger reminders."""

from __future__ import annotations

import logging
import math
import platform
import threading
import time
from datetime import date, datetime, time as dt_time, timedelta
from typing import Callable, Literal, Optional, Set

from outlook_notifier import events_store
from outlook_notifier.browser_session import BrowserSession
from outlook_notifier.config import AppConfig
from outlook_notifier.event import CalendarEvent
from outlook_notifier.notifier import EventNotifier
from outlook_notifier.reminder_content import format_reminder, reminder_identifier
from outlook_notifier.state import ReminderState

logger = logging.getLogger(__name__)

_WAKE_DRIFT_SECONDS = 30
_WAIT_CHUNK_SECONDS = 15

ReminderSendMode = Literal["normal", "catchup"]


class ReminderScheduler:
    def __init__(
        self,
        config: AppConfig,
        browser: BrowserSession,
        notifier: EventNotifier,
        state: ReminderState,
        on_status_change: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        self._config = config
        self._browser = browser
        self._notifier = notifier
        self._state = state
        self._on_status_change = on_status_change
        self._stop_event = stop_event
        self._internal_stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_error = ""
        self._tick_lock = threading.Lock()
        self._os_scheduled: Set[str] = set()

    @property
    def last_error(self) -> str:
        return self._last_error

    def set_browser(self, browser: BrowserSession) -> None:
        self._browser = browser

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._internal_stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._internal_stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def run_once(self) -> None:
        if self._is_stopping():
            return
        if not self._tick_lock.acquire(blocking=False):
            logger.info("Sincronizzazione già in corso, richiesta ignorata.")
            return
        try:
            self._tick()
        finally:
            self._tick_lock.release()

    def _is_stopping(self) -> bool:
        if self._internal_stop.is_set():
            return True
        if self._stop_event and self._stop_event.is_set():
            return True
        return False

    def _run(self) -> None:
        while not self._is_stopping():
            if self._tick_lock.acquire(blocking=False):
                try:
                    self._tick()
                finally:
                    self._tick_lock.release()
            else:
                logger.info("Sincronizzazione già in corso, ciclo scheduler salta questo giro.")
            interval = max(1, self._config.poll_interval_minutes) * 60
            if self._wait_for_next_tick(interval):
                break

    def _wait_for_next_tick(self, interval: float) -> bool:
        """Wait until the next poll. Returns True if the scheduler should stop."""
        deadline = time.time() + interval
        while time.time() < deadline:
            if self._is_stopping():
                return True
            remaining = deadline - time.time()
            wait_for = min(_WAIT_CHUNK_SECONDS, remaining)
            wall_before = time.time()
            mono_before = time.monotonic()
            if self._internal_stop.wait(wait_for):
                return True
            wall_elapsed = time.time() - wall_before
            mono_elapsed = time.monotonic() - mono_before
            drift = wall_elapsed - mono_elapsed
            if drift > _WAKE_DRIFT_SECONDS:
                logger.info(
                    "Risveglio sistema rilevato (sospensione ~%.0fs), sync immediata",
                    drift,
                )
                return False
        return False

    def _tick(self) -> None:
        if self._is_stopping():
            return
        self._config = AppConfig.load()
        self._state.reset_if_new_day()

        try:
            events = self._browser.fetch_today_events()
            events_store.save_events(events)
            self._last_error = ""
            self._notify_status("Sincronizzato")
            self._reschedule_os_notifications(events)
            self._process_events(events)
        except PermissionError as exc:
            self._last_error = str(exc)
            logger.warning("%s", exc)
            self._browser.request_reconnect()
            self._notify_status("Sessione scaduta — usa Riconnetti dal menu")
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("Errore sincronizzazione: %s", exc)
            self._notify_status(f"Errore: {exc}")

    def _reschedule_os_notifications(self, events: list[CalendarEvent]) -> None:
        if platform.system() != "Darwin":
            self._os_scheduled.clear()
            return
        from outlook_notifier.macos_scheduled_notifications import reschedule

        self._os_scheduled = reschedule(events, self._config)

    def _reminder_send_mode(
        self,
        now: datetime,
        event: CalendarEvent,
        reminder_min: int,
        poll_window: timedelta,
    ) -> Optional[ReminderSendMode]:
        if self._state.was_sent(event.id, reminder_min, event.start):
            return None

        trigger_at = event.start - timedelta(minutes=reminder_min)
        window_end = trigger_at + poll_window

        if trigger_at <= now < window_end:
            return "normal"
        if now < trigger_at:
            return None

        catchup_limit = event.end if reminder_min == 0 else event.start
        if now < catchup_limit:
            return "catchup"
        return None

    def _all_day_send_mode(
        self,
        now: datetime,
        event: CalendarEvent,
        trigger_at: datetime,
        poll_window: timedelta,
        reminder_key: int,
    ) -> Optional[ReminderSendMode]:
        if self._state.was_sent(event.id, reminder_key, event.start):
            return None

        window_end = trigger_at + poll_window
        day_end = datetime.combine(
            date.today() + timedelta(days=1),
            dt_time.min,
            tzinfo=now.tzinfo,
        )

        if trigger_at <= now < window_end:
            return "normal"
        if now < trigger_at:
            return None
        if now < day_end:
            return "catchup"
        return None

    def _process_events(self, events: list[CalendarEvent]) -> None:
        now = datetime.now().astimezone()
        poll_window = timedelta(minutes=max(1, self._config.poll_interval_minutes))

        for event in events:
            if event.is_all_day:
                self._process_all_day_event(event, now, poll_window)
                continue

            for reminder_min in self._config.effective_reminder_minutes():
                ident = reminder_identifier(event.id, reminder_min, event.start)
                if ident in self._os_scheduled:
                    continue

                mode = self._reminder_send_mode(now, event, reminder_min, poll_window)
                if mode is None:
                    continue
                self._send_reminder(event, reminder_min, catchup=mode == "catchup")
                self._state.mark_sent(event.id, reminder_min, event.start)

    def _process_all_day_event(
        self,
        event: CalendarEvent,
        now: datetime,
        poll_window: timedelta,
    ) -> None:
        if not self._config.notify_all_day_events:
            return

        try:
            hour, minute = map(int, self._config.all_day_reminder_time.split(":"))
        except ValueError:
            hour, minute = 9, 0

        trigger_at = datetime.combine(
            date.today(),
            dt_time(hour, minute),
            tzinfo=now.tzinfo,
        )
        reminder_key = 0

        ident = reminder_identifier(event.id, reminder_key, event.start)
        if ident in self._os_scheduled:
            return

        mode = self._all_day_send_mode(now, event, trigger_at, poll_window, reminder_key)
        if mode is None:
            return

        self._send_reminder(event, reminder_key, all_day=True, catchup=mode == "catchup")
        self._state.mark_sent(event.id, reminder_key, event.start)

    def _timed_reminder_title(self, event: CalendarEvent, now: datetime) -> str:
        seconds_until_start = (event.start - now).total_seconds()
        if seconds_until_start > 0:
            remaining = max(1, math.ceil(seconds_until_start / 60))
            return f"Tra {remaining} min: {event.subject}"
        return f"Ora: {event.subject}"

    def _send_reminder(
        self,
        event: CalendarEvent,
        reminder_minutes: int,
        *,
        all_day: bool = False,
        catchup: bool = False,
    ) -> None:
        now = datetime.now().astimezone()
        if all_day:
            body = f"{event.display_time}"
            if event.location:
                body += f"\n{event.location}"
            title = f"Oggi: {event.subject}"
        else:
            body = f"Inizia alle {event.start.strftime('%H:%M')}"
            if event.location:
                body += f"\n{event.location}"
            title = self._timed_reminder_title(event, now)

        if catchup:
            logger.info("Reminder recupero: %s — %s", title, body)
        else:
            logger.info("Reminder: %s — %s", title, body)
        self._notifier.notify(title, body, self._config, url=event.web_link or None)

    def _notify_status(self, message: str) -> None:
        if self._on_status_change:
            self._on_status_change(message)
