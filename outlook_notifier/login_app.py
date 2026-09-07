"""Standalone browser login (runs on main thread in its own process)."""

from __future__ import annotations

import logging
import sys

from outlook_notifier.browser_session import BrowserSession
from outlook_notifier.config import AppConfig
from outlook_notifier.notifier import EventNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    config = AppConfig.load()
    browser = BrowserSession(config.outlook_url)
    notifier = EventNotifier(config)
    print("Apertura browser per il login Outlook…")
    print(
        "Il browser parte minimizzato e si chiude da solo se la sessione "
        "risulta già valida. Se serve password/MFA, la finestra "
        "Chromium si aprirà automaticamente (timeout 5 minuti)."
    )
    try:
        notifier.notify(
            "Outlook Notifier",
            "Sto verificando la sessione Outlook. Se serve la password o il "
            "codice MFA, si aprirà automaticamente una finestra del browser.",
            config,
        )
        browser.ensure_token(interactive=True)
        print("Login completato.")
        return 0
    except Exception as exc:
        logger.error("Login fallito: %s", exc)
        print(f"Errore: {exc}", file=sys.stderr)
        notifier.notify("Outlook Notifier", f"Login fallito: {exc}", config)
        return 1
    finally:
        notifier.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
