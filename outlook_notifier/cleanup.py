"""Cleanup browser and related OS processes on shutdown."""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path

from outlook_notifier.config import BROWSER_PROFILE_DIR, CONFIG_DIR

logger = logging.getLogger(__name__)

BROWSER_LOCK_FILE = CONFIG_DIR / "browser.lock"
_cleaned = False
_cleanup_lock = threading.Lock()


def kill_browser_profile_processes(profile_dir: Path = BROWSER_PROFILE_DIR) -> None:
    profile = str(profile_dir.resolve())
    patterns = [
        f"user-data-dir={profile}",
        f"user-data-dir={profile_dir}",
    ]
    for pattern in patterns:
        try:
            result = subprocess.run(
                ["pkill", "-f", pattern],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info("Processi browser terminati (%s)", pattern)
        except FileNotFoundError:
            logger.debug("pkill non disponibile")
            break
        except Exception as exc:
            logger.debug("pkill %s: %s", pattern, exc)


def release_browser_lock() -> None:
    BROWSER_LOCK_FILE.unlink(missing_ok=True)


def cleanup_all() -> None:
    global _cleaned
    with _cleanup_lock:
        if _cleaned:
            return
        _cleaned = True

    from outlook_notifier.subprocess_registry import terminate_all

    terminate_all()
    kill_browser_profile_processes()
    release_browser_lock()
