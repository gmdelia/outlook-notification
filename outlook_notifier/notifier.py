"""Desktop notifications with popup and sound."""

from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
import threading
from pathlib import Path

from desktop_notifier import DEFAULT_SOUND, DesktopNotifier

from outlook_notifier.config import AppConfig

logger = logging.getLogger(__name__)

DEFAULT_MAC_SOUND = "/System/Library/Sounds/Glass.aiff"

# AppleScript: argv avoids shell/string escaping issues with titles/messages.
_OSASCRIPT_NOTIFY = """
on run argv
  display notification (item 2 of argv) with title (item 1 of argv)
end run
"""


def _macos_is_bundle() -> bool:
    if platform.system() != "Darwin":
        return False
    try:
        from desktop_notifier.backends.macos_support import is_bundle

        return bool(is_bundle())
    except Exception:
        return False


class EventNotifier:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._use_osascript = platform.system() == "Darwin" and not _macos_is_bundle()
        self._notifier: DesktopNotifier | None = None
        if not self._use_osascript:
            self._notifier = DesktopNotifier(app_name="Outlook Notifier")
        else:
            logger.info(
                "macOS: processo non in un .app — uso notifiche native via AppleScript "
                "(abilita banner per Script Editor / osascript in Impostazioni di Sistema → Notifiche)."
            )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._start_loop()

    def _start_loop(self) -> None:
        def run_loop() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=run_loop, daemon=True, name="notifier-loop")
        self._thread.start()
        self._ready.wait(timeout=5)

    def notify(
        self,
        title: str,
        message: str,
        config: AppConfig | None = None,
        *,
        wait: bool = False,
    ) -> None:
        cfg = config or self._config
        if not cfg.notifications_enabled:
            return

        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._send_popup(title, message, cfg),
                self._loop,
            )
            if wait:
                future.result(timeout=20)
        else:
            logger.warning("Loop notifiche non attivo: popup saltato (%s)", title)
            if wait:
                raise RuntimeError("Loop notifiche non attivo")

        if cfg.sound_enabled:
            self._play_sound(cfg)

    def send_test(self) -> None:
        """Send a one-shot native notification (for Settings → Prova notifica)."""
        cfg = AppConfig.load()
        # Force popup even if notifications were disabled, so the user can verify OS permissions.
        cfg.notifications_enabled = True
        self.notify(
            "Outlook Notifier",
            "Notifica di prova. Se vedi questo banner, le notifiche native funzionano.",
            cfg,
            wait=True,
        )

    async def _send_popup(self, title: str, message: str, config: AppConfig) -> None:
        try:
            if self._use_osascript:
                await asyncio.to_thread(self._send_osascript, title, message)
            elif self._notifier is not None:
                await self._notifier.send(
                    title=title,
                    message=message,
                    sound=DEFAULT_SOUND if config.sound_enabled else None,
                )
            else:
                logger.error("Nessun backend notifica disponibile")
        except Exception as exc:
            logger.error("Errore notifica desktop: %s", exc)

    def _send_osascript(self, title: str, message: str) -> None:
        result = subprocess.run(
            ["osascript", "-e", _OSASCRIPT_NOTIFY, title, message],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip() or f"exit {result.returncode}"
            logger.error("osascript display notification fallito: %s", err)
            raise RuntimeError(err)
        logger.info("Notifica native inviata: %s", title)

    def _play_sound(self, config: AppConfig) -> None:
        sound_path = self._resolve_sound_file(config.sound_file)
        system = platform.system()

        try:
            if system == "Darwin":
                subprocess.Popen(
                    ["afplay", str(sound_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif system == "Linux":
                if Path("/usr/bin/paplay").exists():
                    subprocess.Popen(
                        ["paplay", str(sound_path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    subprocess.Popen(
                        ["aplay", str(sound_path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            elif system == "Windows":
                import winsound

                winsound.PlaySound(str(sound_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as exc:
            logger.error("Errore riproduzione suono: %s", exc)

    def _resolve_sound_file(self, configured: str) -> Path:
        if configured:
            path = Path(configured).expanduser()
            if path.exists():
                return path

        if platform.system() == "Darwin" and Path(DEFAULT_MAC_SOUND).exists():
            return Path(DEFAULT_MAC_SOUND)

        bundled = Path(__file__).resolve().parent.parent / "assets" / "default_alert.wav"
        if bundled.exists():
            return bundled

        return Path(DEFAULT_MAC_SOUND)

    def shutdown(self) -> None:
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
