"""Standalone browser login (runs on main thread in its own process)."""

from __future__ import annotations

import logging
import sys

from outlook_notifier.browser_session import BrowserSession
from outlook_notifier.config import AppConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    config = AppConfig.load()
    browser = BrowserSession(config.outlook_url)
    print("Apertura browser per il login Outlook…")
    print("Completa login e MFA, poi attendi che la finestra si chiuda.")
    try:
        browser.ensure_token(interactive=True)
        print("Login completato.")
        return 0
    except Exception as exc:
        logger.error("Login fallito: %s", exc)
        print(f"Errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
