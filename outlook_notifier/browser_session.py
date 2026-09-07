"""Playwright session for Outlook Web with token and calendar extraction."""

from __future__ import annotations

import fcntl
import logging
import re
import shutil
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from outlook_notifier.calendar_client import CalendarClient
from outlook_notifier.cleanup import kill_browser_profile_processes
from outlook_notifier.config import BROWSER_PROFILE_DIR, CONFIG_DIR, AppConfig
from outlook_notifier.event import CalendarEvent

logger = logging.getLogger(__name__)

GRAPH_HOST = "graph.microsoft.com"
# Hostnames Microsoft uses for the Outlook Web front-end. Microsoft has been
# rolling out outlook.cloud.microsoft as the consolidated replacement for
# outlook.office.com/outlook.office365.com — recognize it too, otherwise a
# logged-in session on that host is misdetected as "not logged in".
OWA_HOST_MARKERS = ("outlook.office", "outlook.live", "office365.com", "office.com", "outlook.cloud.microsoft")
CALENDAR_PATH = "/calendar/view/day"
LOGIN_TIMEOUT_SECONDS = 300
TOKEN_REFRESH_WAIT_SECONDS = 30
CALENDAR_RESPONSE_TIMEOUT = 12
BROWSER_LOCK_TIMEOUT = 150
LOGIN_WINDOW_WIDTH = 900
LOGIN_WINDOW_HEIGHT = 700
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


class LoginRequiredError(RuntimeError):
    """Raised when a headless attempt confirms interactive login is required
    (Microsoft login page, or a stale/unauthenticated Outlook session) — as
    opposed to a generic/transient failure that shouldn't pop up a window."""


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
        self._last_headed_failure_at: Optional[float] = None
        self._headed_session = False

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
        self._calendar_response = None
        self._clear_session_marker()
        self.clear_browser_profile()

    def invalidate_session(self) -> None:
        """Force a fresh (silent, cookie-reusing) attempt without wiping the
        browser profile. Use for suspected-but-unconfirmed auth failures
        (e.g. a single REST 401) — NOT for a confirmed credential change,
        which should go through request_reconnect() instead."""
        self._token = None
        self._owa_token = None
        self._calendar_response = None
        self._clear_session_marker()

    def has_valid_session(self) -> bool:
        return SESSION_MARKER.exists()

    def seconds_since_headed_failure(self) -> Optional[float]:
        """Seconds since the last failed interactive (headed) login attempt,
        or None if there hasn't been one (or it was cleared by a success)."""
        if self._last_headed_failure_at is None:
            return None
        return time.time() - self._last_headed_failure_at

    def _mark_session_valid(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_MARKER.write_text("ok", encoding="utf-8")

    def _clear_session_marker(self) -> None:
        SESSION_MARKER.unlink(missing_ok=True)

    def clear_browser_profile(self) -> None:
        """Wipe persistent Chromium profile so Microsoft shows a fresh login form."""
        kill_browser_profile_processes(self._profile_dir)
        time.sleep(0.5)
        if self._profile_dir.exists():
            try:
                shutil.rmtree(self._profile_dir)
                logger.info("Profilo browser cancellato: %s", self._profile_dir)
            except OSError as exc:
                logger.warning("Impossibile cancellare il profilo browser: %s", exc)

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

            try:
                self._ensure_session(interactive=interactive, wait_for_calendar=True)
                cfg = AppConfig.load()
                client = CalendarClient(self._outlook_url, tz_name=cfg.effective_timezone())

                if self._calendar_response is not None:
                    events = client.parse_events_from_response(self._calendar_response)
                    self._mark_session_valid()
                    return events

                last_permission_error: Optional[PermissionError] = None

                # Prefer the Microsoft Graph token/endpoint — the legacy
                # Outlook REST API v2.0 was fully decommissioned by
                # Microsoft in March 2024 and now fails for every request.
                if self._token:
                    try:
                        events = client.fetch_via_graph_api(self._token)
                        self._mark_session_valid()
                        return events
                    except PermissionError as exc:
                        last_permission_error = exc
                    except Exception as exc:
                        logger.warning("Fallback Graph API fallito: %s", exc)

                if self._owa_token:
                    try:
                        events = client.fetch_via_rest_api(self._owa_token)
                        self._mark_session_valid()
                        return events
                    except PermissionError as exc:
                        last_permission_error = exc
                    except Exception as exc:
                        logger.warning("Fallback REST API v2.0 fallito: %s", exc)

                if last_permission_error is not None:
                    raise last_permission_error

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

            try:
                self._ensure_session(interactive=interactive, wait_for_calendar=True)
                token = self._owa_token or self._token
                if not token and self._calendar_response is None:
                    raise RuntimeError(
                        "Login Microsoft non completato. "
                        "Usa Riconnetti e inserisci la nuova password/MFA nel browser."
                    )
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

    def _ensure_session(self, interactive: bool, wait_for_calendar: bool) -> None:
        """Try a silent, invisible (headless) attempt first, reusing saved
        cookies. Only escalate to a visible window when that attempt
        confirms interactive login is truly required — so the browser
        window never appears when the saved session is still valid."""
        force_headed = interactive or self._force_interactive
        self._force_interactive = False

        if not force_headed:
            try:
                self._open_session(headed=False, wait_for_calendar=wait_for_calendar)
                return
            except LoginRequiredError:
                logger.info("Sessione non valida: apro finestra di login visibile.")
                self._close_session()
            # Other exceptions (network/timeout issues) propagate as-is —
            # there's no point popping up a visible window for a transient
            # failure that isn't actually about needing credentials.

        self._open_session(headed=True, wait_for_calendar=wait_for_calendar)

    def _open_session(self, headed: bool, wait_for_calendar: bool) -> None:
        self._playwright = sync_playwright().start()
        self._headed_session = headed
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        # Never reuse a token captured in a previous tick — a stale (likely
        # expired) token would make _is_ready() short-circuit immediately and
        # get used for the REST fallback, causing spurious 401s.
        self._token = None
        self._owa_token = None
        self._calendar_response = None

        args = ["--disable-blink-features=AutomationControlled"]
        viewport = {"width": 1280, "height": 800}
        if headed:
            # Window size only — no fixed --window-position, which can land
            # off-screen depending on display resolution/arrangement and make
            # the login window appear to "not open" even though it's running.
            args.append(f"--window-size={LOGIN_WINDOW_WIDTH},{LOGIN_WINDOW_HEIGHT}")
            viewport = {"width": LOGIN_WINDOW_WIDTH, "height": LOGIN_WINDOW_HEIGHT}

        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self._profile_dir),
                headless=not headed,
                args=args,
                viewport=viewport,
                locale="it-IT",
            )
        except Exception as exc:
            raise _wrap_browser_error(exc) from exc

        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._context.on("page", self._on_new_page)
        self._attach_page_listeners(self._page)

        calendar_url = f"{self._outlook_url}{CALENDAR_PATH}"
        logger.info("Apertura calendario: %s (headed=%s)", calendar_url, headed)
        self._page.goto(calendar_url, wait_until="domcontentloaded", timeout=60000)
        if headed:
            # Start minimized — only reveal the window once we actually
            # confirm the user must type something (login form/MFA).
            self._set_window_state(self._page, "minimized")

        try:
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
                if headed:
                    raise RuntimeError(
                        "Login Microsoft non completato. "
                        "Usa Riconnetti e inserisci la nuova password/MFA nel browser."
                    )
                if self._credentials_required():
                    raise LoginRequiredError(
                        "Login Microsoft richiesto: sessione scaduta o non autenticata."
                    )
                raise RuntimeError(
                    "Login non completato o calendario non accessibile. "
                    "Verifica le credenziali in Outlook Web."
                )
        except RuntimeError:
            if headed:
                # Record so the automatic scheduler loop can back off instead
                # of immediately popping up another 5-minute headed window.
                self._last_headed_failure_at = time.time()
            raise

        if headed:
            self._last_headed_failure_at = None
        self._extract_user_email()

    def _try_fetch_via_js(self) -> Any:
        """Fetch calendar data via in-page fetch(), reusing session cookies.

        Returns None on success (or if already have calendar data), otherwise the
        error payload from the page (status code or message).
        """
        if self._calendar_response is not None or not self._page:
            return None

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
                return None
            if isinstance(result, dict) and "__error" in result:
                return result["__error"]
        except Exception as exc:
            return str(exc)
        return "unknown"

    def _bring_to_front(self, page: Page) -> None:
        try:
            page.bring_to_front()
        except Exception as exc:
            logger.debug("bring_to_front fallito: %s", exc)

    def _set_window_state(self, page: Page, state: str) -> None:
        """state: 'minimized' or 'normal'. Uses the Chrome DevTools Protocol
        (Browser.setWindowBounds) to reliably minimize/restore the real OS
        window — more reliable cross-platform than launch flags like
        --start-minimized, which Chromium ignores on macOS.

        If a state change is requested right after a previous one (e.g.
        minimize immediately followed by restore), Chromium/macOS can drop
        the second call because the OS-level transition hasn't finished yet.
        Verify the resulting state and retry a couple of times if needed."""
        if not self._context:
            return
        try:
            cdp = self._context.new_cdp_session(page)
            window_id = cdp.send("Browser.getWindowForTarget")["windowId"]
            for attempt in range(3):
                cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": state}})
                current = cdp.send("Browser.getWindowForTarget")["bounds"].get("windowState")
                if current == state:
                    return
                time.sleep(0.2)
            logger.debug("Stato finestra (%s) non confermato dopo i tentativi (attuale: %s)", state, current)
        except Exception as exc:
            logger.debug("Impostazione stato finestra (%s) fallita: %s", state, exc)

    def _on_new_page(self, page: Page) -> None:
        self._attach_page_listeners(page)
        if self._headed_session:
            # A new tab/popup during an interactive login is almost always
            # something the user needs to see (e.g. an MFA approval prompt).
            self._set_window_state(page, "normal")
            self._bring_to_front(page)

    def _attach_page_listeners(self, page: Page) -> None:
        page.on("request", self._capture_token_from_request)
        page.on("response", self._capture_calendar_from_response)

    def _adopt_page(self, page: Page) -> None:
        if page is self._page:
            return
        self._page = page
        self._attach_page_listeners(page)
        self._bring_to_front(page)
        try:
            url = page.url
        except Exception:
            url = "?"
        logger.info(
            "Sessione Outlook rilevata su tab (%s) — chiusura dopo sync calendario",
            url,
        )

    def _find_outlook_page(self) -> Page | None:
        if not self._context:
            return None
        for page in list(self._context.pages):
            try:
                if self._page_looks_logged_in(page):
                    return page
            except Exception:
                continue
        return None

    def _capture_token_from_request(self, request) -> None:
        url = request.url
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return

        token = auth.split(" ", 1)[1].strip()
        host = urlparse(url).netloc.lower()
        if GRAPH_HOST in url:
            self._token = token
        elif any(marker in host for marker in OWA_HOST_MARKERS) or (
            "/api/" in url and "outlook" in url.lower()
        ):
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
        navigated_to_calendar = False
        reloaded = False
        credentials_logged = False
        came_from_login_page = False
        window_visible = False
        last_js_fetch_at = 0.0
        last_url_log_at = 0.0
        last_bring_to_front_at = 0.0
        outlook_since: float | None = None
        calendar_url = f"{self._outlook_url}{CALENDAR_PATH}"

        while time.time() < deadline:
            if self._is_ready(wait_for_calendar):
                logger.info("Login riuscito — chiusura browser")
                time.sleep(1)
                return

            # Microsoft MFA often finishes on another tab — follow it.
            outlook_page = self._find_outlook_page()
            if outlook_page is not None and outlook_page is not self._page:
                self._adopt_page(outlook_page)
                navigated_to_calendar = False
                reloaded = False
                outlook_since = None
                came_from_login_page = True

            now = time.time()
            if now - last_url_log_at >= 10:
                try:
                    current_url = self._page.url if self._page else "?"
                except Exception:
                    current_url = "?"
                logger.info("In attesa login — URL: %s", current_url)
                last_url_log_at = now

            # Re-raise the window periodically in case it got buried behind
            # other apps — keeps the login form reachable for the user. Only
            # once it's actually been made visible; otherwise this would
            # fight with the deliberate minimize-until-needed behavior.
            if window_visible and now - last_bring_to_front_at >= 15:
                self._bring_to_front(self._page)
                last_bring_to_front_at = now

            if self._looks_like_login_page():
                outlook_since = None
                navigated_to_calendar = False
                reloaded = False
                came_from_login_page = True
                if not window_visible:
                    self._set_window_state(self._page, "normal")
                    self._bring_to_front(self._page)
                    window_visible = True
                if not credentials_logged:
                    logger.info(
                        "Credenziali richieste — completa password/MFA nel browser"
                    )
                    credentials_logged = True
                time.sleep(1)
                continue

            if self._looks_logged_in():
                if outlook_since is None:
                    outlook_since = time.time()

                # Only force a navigation + reload cycle after actually
                # leaving a Microsoft login page — needed there to pick up
                # the freshly-issued session, but pointless (and slow) when
                # the session was already valid from the start.
                if came_from_login_page and not navigated_to_calendar:
                    try:
                        self._page.goto(
                            calendar_url,
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                    except Exception as exc:
                        logger.debug("Goto calendario post-login fallito: %s", exc)
                    navigated_to_calendar = True
                    time.sleep(2)
                    continue

                if came_from_login_page and not reloaded:
                    try:
                        self._page.reload(
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                    except Exception as exc:
                        logger.debug("Reload post-login fallito: %s", exc)
                    reloaded = True
                    time.sleep(2)
                    continue

                if now - last_js_fetch_at >= 2.5:
                    js_error = self._try_fetch_via_js()
                    last_js_fetch_at = now
                    if js_error is not None:
                        logger.info("JS fetch calendario non riuscito: %s", js_error)
                    if self._is_ready(wait_for_calendar):
                        logger.info("Login riuscito — chiusura browser")
                        time.sleep(1)
                        return
                    if (
                        outlook_since is not None
                        and now - outlook_since >= 15
                        and str(js_error) in ("401", "403")
                    ):
                        raise RuntimeError(
                            "Sessione non autorizzata dopo il login. "
                            "Usa Riconnetti e inserisci di nuovo password/MFA."
                        )

            elif self._credentials_required() and not credentials_logged:
                logger.info(
                    "Credenziali richieste — completa password/MFA nel browser"
                )
                credentials_logged = True

            time.sleep(1)

        # Timed out — reveal the window (if not already) so the user can see
        # the state it's stuck in, whether or not it was ever restored.
        self._set_window_state(self._page, "normal")
        self._bring_to_front(self._page)

        if self._looks_like_login_page() or self._credentials_required():
            raise RuntimeError(
                "Timeout: login Microsoft non completato. "
                "Usa Riconnetti e inserisci la nuova password."
            )
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
        return self._page_looks_logged_in(self._page)

    def _page_looks_logged_in(self, page: Page) -> bool:
        if self._page_looks_like_login(page):
            return False
        try:
            host = urlparse(page.url).netloc.lower()
        except Exception:
            return False
        return any(marker in host for marker in OWA_HOST_MARKERS)

    def _looks_like_login_page(self) -> bool:
        assert self._page is not None
        return self._page_looks_like_login(self._page)

    def _page_looks_like_login(self, page: Page) -> bool:
        try:
            host = urlparse(page.url).netloc.lower()
        except Exception:
            return False
        return "login.microsoftonline.com" in host or "login.live.com" in host

    def _credentials_required(self) -> bool:
        """True when Microsoft is asking for password/MFA or session is unauthenticated."""
        if self._page is None:
            return False
        if self._is_ready(wait_for_calendar=True):
            return False
        if self._looks_like_login_page():
            return True
        # Outlook shell URL without token/calendar = stale/unauthenticated session
        return self._looks_logged_in()

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
