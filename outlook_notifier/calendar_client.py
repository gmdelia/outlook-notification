"""Fetch and parse calendar events from OWA / Outlook REST."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, List
from zoneinfo import ZoneInfo

import requests
from dateutil import parser as date_parser

from outlook_notifier.config import detect_local_timezone
from outlook_notifier.event import CalendarEvent

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


class CalendarClient:
    def __init__(self, outlook_url: str = "https://outlook.office.com", tz_name: str | None = None) -> None:
        self._outlook_url = outlook_url.rstrip("/")
        tz_key = tz_name or detect_local_timezone()
        try:
            self._tz = ZoneInfo(tz_key)
        except Exception:
            self._tz = ZoneInfo("UTC")

    def parse_events_from_response(self, data: dict) -> List[CalendarEvent]:
        items = data.get("value", [])
        events: List[CalendarEvent] = []
        for item in items:
            event = self._parse_event(item)
            if event:
                events.append(event)
        return events

    def fetch_via_graph_api(self, token: str) -> List[CalendarEvent]:
        """Preferred REST fallback — Microsoft Graph is the only supported
        endpoint for calendar data (the legacy Outlook REST API v2.0 used by
        fetch_via_rest_api was fully decommissioned by Microsoft in March
        2024 and now fails for every request)."""
        today = date.today()
        start = datetime.combine(today, time.min, tzinfo=self._tz)
        end = start + timedelta(days=1)

        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$top": "100",
            "$select": "id,subject,start,end,location,isAllDay,webLink",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Prefer": f'outlook.timezone="{self._tz.key}"',
        }

        response = requests.get(
            f"{GRAPH_API_BASE}/me/calendarView",
            params=params,
            headers=headers,
            timeout=30,
        )
        return self._handle_calendar_response(response)

    def fetch_via_rest_api(self, token: str) -> List[CalendarEvent]:
        """Legacy Outlook REST API v2.0 — decommissioned by Microsoft since
        March 2024 (requests now fail for every tenant). Kept only as a
        last-resort fallback in case fetch_via_graph_api can't be used
        (e.g. no Graph-scoped token was captured)."""
        today = date.today()
        start = datetime.combine(today, time.min, tzinfo=self._tz)
        end = start + timedelta(days=1)

        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$top": "100",
            "$select": "Id,Subject,Start,End,Location,IsAllDay,WebLink",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Prefer": f'outlook.timezone="{self._tz.key}"',
        }

        response = requests.get(
            f"{self._outlook_url}/api/v2.0/me/calendarview",
            params=params,
            headers=headers,
            timeout=30,
        )
        return self._handle_calendar_response(response)

    def _handle_calendar_response(self, response) -> List[CalendarEvent]:
        if response.status_code == 401:
            raise PermissionError("Token scaduto — riconnessione necessaria.")
        if response.status_code == 403:
            raise PermissionError(
                "Accesso calendario negato dal tenant. "
                "Verifica di poter vedere il calendario in Outlook Web."
            )
        if response.status_code == 410:
            # Endpoint gone (e.g. the decommissioned Outlook REST API v2.0)
            # — not a credentials problem, retrying login won't fix this.
            raise RuntimeError("Endpoint calendario non più disponibile (410 Gone).")
        response.raise_for_status()
        return self.parse_events_from_response(response.json())

    def _parse_event(self, item: dict[str, Any]) -> CalendarEvent | None:
        try:
            subject = (
                item.get("subject")
                or item.get("Subject")
                or "(Senza titolo)"
            )
            subject = str(subject).strip()

            is_all_day = bool(item.get("isAllDay") or item.get("IsAllDay"))
            start_raw = item.get("start") or item.get("Start") or {}
            end_raw = item.get("end") or item.get("End") or {}

            start = self._parse_datetime(start_raw, is_all_day, is_start=True)
            end = self._parse_datetime(end_raw, is_all_day, is_start=False)

            location = ""
            loc = item.get("location") or item.get("Location") or {}
            if isinstance(loc, dict):
                location = (
                    loc.get("displayName")
                    or loc.get("DisplayName")
                    or ""
                ).strip()
            elif isinstance(loc, str):
                location = loc.strip()

            event_id = item.get("id") or item.get("Id") or subject
            web_link = item.get("webLink") or item.get("WebLink") or ""

            return CalendarEvent(
                id=str(event_id),
                subject=subject,
                start=start,
                end=end,
                location=location,
                is_all_day=is_all_day,
                web_link=str(web_link),
            )
        except Exception as exc:
            logger.warning("Evento ignorato: %s", exc)
            return None

    def _parse_datetime(
        self,
        payload: dict[str, Any] | str,
        is_all_day: bool,
        is_start: bool,
    ) -> datetime:
        if isinstance(payload, str):
            raw = payload
            tz_name = self._tz.key
        else:
            raw = (
                payload.get("dateTime")
                or payload.get("DateTime")
                or ""
            )
            tz_name = (
                payload.get("timeZone")
                or payload.get("TimeZone")
                or self._tz.key
            )

        if is_all_day:
            parsed = date_parser.isoparse(raw)
            local_date = parsed.date()
            if is_start:
                return datetime.combine(local_date, time.min, tzinfo=self._tz)
            return datetime.combine(local_date, time.max.replace(microsecond=0), tzinfo=self._tz)

        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = self._tz

        parsed = date_parser.isoparse(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        return parsed.astimezone(self._tz)
