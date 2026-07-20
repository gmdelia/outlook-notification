"""Playwright session for Outlook Web with token and calendar extraction."""

from __future__ import annotations

import fcntl
import logging
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from outlook_notifier.calendar_client import CalendarClient
from outlook_notifier.config import BROWSER_PROFILE_DIR, CONFIG_DIR, AppConfig
from outlook_notifier.event import CalendarEvent

logger = logging.getLogger(__name__)

GRAPH_HOST = "graph.microsoft.com"
CALENDAR_PATH = "/calendar/view/day"
LOGIN_TIMEOUT_SECONDS = 300
TOKEN_REFRESH_WAIT_SECONDS = 30
CALENDAR_RESPONSE_TIMEOUT = 12
BROWSER_LOCK_TIMEOUT = 150
SESSION_MARKER = CONFIG_DIR / "session.ok"
BROWSER_LOCK_FILE = CONFIG_DIR / "browser.lock"
BROWSER_INSTALL_HINT = (
    "Browser Playwright non installato. Esegui:\n"
    "  source .venv/bin/activate && python -m playwright install chromium\n"
    "Oppure: ./scripts/install.sh"
)


def _is_missing_browser_error(exc: Exception) -> bool:
    message = str(exc)
    return "Executable doesn't exist" in message or "Please run the following command" in message


def _wrap_browser_error(exc: Exception) -> RuntimeError:
    if _is_missing_browser_error(exc):
        return RuntimeError(BROWSER_INSTALL_HINT)
    return RuntimeError(str(exc))


def _is_calendar_api_url(url: str) -> bool:
    lower = url.lower()
    return (
        "calendarview" in lower
        or "findcalendaritems" in lower
        or ("calendar" in lower and "/events" in lower)
        or "calendar/api/" in lower
    )


@dataclass
class SessionStatus:
    connected: bool
    message: str
    user_email: str = ""


class BrowserSession:
    def __init__(self, outlook_url: str = "https://outlook.office.com") -> None:
        self._outlook_url = outlook_url.rstrip("/")
        self._profile_dir = BROWSER_PROFILE_DIR
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._token: Optional[str] = None
        self._owa_token: Optional[str] = None
        self._user_email: str = ""
        self._lock = threading.Lock()
        self._force_interactive = False
        self._calendar_response: Optional[dict[str, Any]] = None

    @property
    def token(self) -> Optional[str]:
        return self._token or self._owa_token

    @property
    def user_email(self) -> str:
        return self._user_email

    def request_reconnect(self) -> None:
        self._force_interactive = True
        self._token = None
        self._owa_token = None
        self._clear_session_marker()

    def has_valid_session(self) -> bool:
        return SESSION_MARKER.exists()

    def _mark_session_valid(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_MARKER.write_text("ok", encoding="utf-8")

    def _clear_session_marker(self) -> None:
        SESSION_MARKER.unlink(missing_ok=True)

    def status(self) -> SessionStatus:
        if self._token or self._owa_token:
            return SessionStatus(
                connected=True,
                message="Connesso",
                user_email=self._user_email,
            )
        if self.has_valid_session():
            return SessionStatus(
                connected=False,
                message="Sessione salvata — sincronizzazione in corso",
                user_email=self._user_email,
            )
        if self._profile_dir.exists() and any(self._profile_dir.iterdir()):
            return SessionStatus(
                connected=False,
                message="Login richiesto — si aprirà il browser",
                user_email=self._user_email,
            )
        return SessionStatus(
            connected=False,
            message="Login richiesto al primo avvio",
            user_email="",
        )

    def fetch_today_events(self, interactive: bool = False) -> List[CalendarEvent]:
        with self._browser_lock():
            self._calendar_response = None
            needs_login = interactive or self._force_interactive or not self.has_valid_session()
            headed = needs_login
            self._force_interactive = False

            try:
                self._open_session(headed=headed, wait_for_calendar=True)
                cfg = AppConfig.load()
                client = CalendarClient(self._outlook_url, tz_name=cfg.effective_timezone())

                if self._calendar_response is not None:
                    events = client.parse_events_from_response(self._calendar_response)
                    self._mark_session_valid()
                    return events

                token = self._owa_token or self._token
                if token:
                    try:
                        events = client.fetch_via_rest_api(token)
                        self._mark_session_valid()
                        return events
                    except PermissionError:
                        raise
                    except Exception as exc:
                        logger.warning("Fallback REST API fallito: %s", exc)

                raise RuntimeError(
                    "Calendario non accessibile. Completa il login in Outlook Web "
                    "e verifica di vedere gli eventi nel browser."
                )
            except Exception:
                self._clear_session_marker()
                raise
            finally:
                self._close_session()

    def ensure_token(self, interactive: bool = False) -> str:
        with self._browser_lock():
            if (self._token or self._owa_token) and not self._force_interactive and not interactive:
                return self._token or self._owa_token or ""

            needs_login = interactive or self._force_interactive or not self.has_valid_session()
            headed = needs_login
            self._force_interactive = False

            try:
                self._open_session(headed=headed, wait_for_calendar=True)
                token = self._owa_token or self._token
                if not token and self._calendar_response is None:
                    raise RuntimeError("Impossibile stabilire la sessione con Outlook Web.")
                self._mark_session_valid()
                return token or ""
            except Exception:
                self._clear_session_marker()
                raise
            finally:
                self._close_session()

    @contextmanager
    def _browser_lock(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        lock_path = BROWSER_LOCK_FILE
        with open(lock_path, "w", encoding="utf-8") as lock_file:
            deadline = time.time() + BROWSER_LOCK_TIMEOUT
            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.time() >= deadline:
                        raise RuntimeError(
                            "Browser già in uso. Attendi che il login o la sincronizzazione finisca."
                        )
                    time.sleep(0.5)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _open_session(self, headed: bool, wait_for_calendar: bool) -> None:
        self._playwright = sync_playwright().start()
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        self._calendar_response = None

        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self._profile_dir),
                headless=not headed,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 800},
                locale="it-IT",
            )
        except Exception as exc:
            raise _wrap_browser_error(exc) from exc

        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.on("request", self._capture_token_from_request)
        self._page.on("response", self._capture_calendar_from_response)

        calendar_url = f"{self._outlook_url}{CALENDAR_PATH}"
        logger.info("Apertura calendario: %s (headed=%s)", calendar_url, headed)
        self._page.goto(calendar_url, wait_until="domcontentloaded", timeout=60000)

        if headed:
            self._wait_for_login(wait_for_calendar=wait_for_calendar)
        else:
            self._wait_for_ready(wait_for_calendar=wait_for_calendar)

        if wait_for_calendar and self._calendar_response is None and not self._looks_like_login_page():
            self._try_fetch_via_js()

        if (
            not self._token
            and not self._owa_token
            and self._calendar_response is None
        ):
            raise RuntimeError(
                "Login non completato o calendario non accessibile. "
                "Verifica le credenziali in Outlook Web."
            )

        self._extract_user_email()

    def _try_fetch_via_js(self) -> None:
        """Fetch calendar data via in-page fetch(), reusing session cookies."""
        if self._calendar_response is not None or not self._page:
            return

        today = date.today()
        start = datetime.combine(today, dt_time.min).isoformat()
        end = datetime.combine(today + timedelta(days=1), dt_time.min).isoformat()
        select = "Id,Subject,Start,End,Location,IsAllDay,WebLink"
        endpoint = (
            f"/api/v2.0/me/calendarview?startDateTime={start}"
            f"&endDateTime={end}&$top=100&$select={select}"
        )
        js = """
        async (url) => {
            try {
                const r = await fetch(url, {
                    credentials: 'include',
                    headers: { 'Accept': 'application/json' }
                });
                if (!r.ok) return { __error: r.status };
                return await r.json();
            } catch (e) {
                return { __error: String(e) };
            }
        }
        """
        try:
            result = self._page.evaluate(js, endpoint)
            if isinstance(result, dict) and "value" in result:
                self._calendar_response = result
                logger.info(
                    "Calendario via JS fetch: %d eventi",
                    len(result.get("value", [])),
                )
            elif isinstance(result, dict) and "__error" in result:
                logger.debug("JS fetch calendario non riuscito: %s", result["__error"])
        except Exception as exc:
            logger.debug("JS fetch calendario fallito: %s", exc)

    def _capture_token_from_request(self, request) -> None:
        url = request.url
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return

        token = auth.split(" ", 1)[1].strip()
        if GRAPH_HOST in url:
            self._token = token
        elif "/api/" in url and "outlook" in url:
            self._owa_token = token

    def _capture_calendar_from_response(self, response) -> None:
        if self._calendar_response is not None:
            return
        if response.status != 200:
            return
        if not _is_calendar_api_url(response.url):
            return
        try:
            data = response.json()
            if isinstance(data, dict) and "value" in data:
                self._calendar_response = data
                logger.info("Calendario intercettato da %s", response.url)
        except Exception as exc:
            logger.debug("Risposta calendario non parsabile: %s", exc)

    def _wait_for_login(self, wait_for_calendar: bool) -> None:
        assert self._page is not None
        deadline = time.time() + LOGIN_TIMEOUT_SECONDS
        reloaded = False
        while time.time() < deadline:
            if self._is_ready(wait_for_calendar):
                time.sleep(1)
                return
            if self._looks_logged_in():
                if not reloaded:
                    self._page.reload(wait_until="domcontentloaded", timeout=60000)
                    reloaded = True
                    time.sleep(2)
                else:
                    return
            time.sleep(1)
        raise RuntimeError("Timeout login: completa l'accesso entro 5 minuti.")

    def _wait_for_ready(self, wait_for_calendar: bool) -> None:
        deadline = time.time() + CALENDAR_RESPONSE_TIMEOUT
        while time.time() < deadline:
            if self._is_ready(wait_for_calendar):
                return
            if self._looks_like_login_page():
                return
            time.sleep(0.5)
        # Second chance: force a reload to bypass service-worker cache
        if self._page and not self._is_ready(wait_for_calendar):
            logger.info("Nessuna risposta calendario: reload forzato per svuotare cache.")
            try:
                self._page.reload(wait_until="networkidle", timeout=20000)
            except Exception as exc:
                logger.debug("Reload fallito: %s", exc)
            deadline2 = time.time() + 15
            while time.time() < deadline2:
                if self._is_ready(wait_for_calendar):
                    return
                time.sleep(0.5)

    def _is_ready(self, wait_for_calendar: bool) -> bool:
        has_token = bool(self._token or self._owa_token)
        if wait_for_calendar:
            return self._calendar_response is not None or has_token
        return has_token

    def _looks_logged_in(self) -> bool:
        assert self._page is not None
        url = self._page.url
        host = urlparse(url).netloc
        return "outlook" in host and ("/mail" in url or "/calendar" in url)

    def _looks_like_login_page(self) -> bool:
        assert self._page is not None
        url = self._page.url.lower()
        return any(
            marker in url
            for marker in ("login.microsoftonline.com", "login.live.com", "/oauth2/")
        )

    def _extract_user_email(self) -> None:
        assert self._page is not None
        try:
            content = self._page.content()
            match = re.search(
                r'"UserPrincipalName"\s*:\s*"([^"]+@[^"]+)"',
                content,
            )
            if match:
                self._user_email = match.group(1)
        except Exception:
            logger.debug("Impossibile estrarre email utente dalla pagina.")

    def _close_session(self) -> None:
        try:
            if self._context:
                self._context.close()
        except Exception as exc:
            logger.debug("Chiusura browser: %s", exc)
        finally:
            self._context = None
            self._page = None
            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception as exc:
                    logger.debug("Stop playwright: %s", exc)
            self._playwright = None
