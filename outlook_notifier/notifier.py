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


class EventNotifier:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._notifier = DesktopNotifier(app_name="Outlook Notifier")
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
    ) -> None:
        cfg = config or self._config
        if not cfg.notifications_enabled:
            return

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._send_popup(title, message, cfg),
                self._loop,
            )

        if cfg.sound_enabled:
            self._play_sound(cfg)

    async def _send_popup(self, title: str, message: str, config: AppConfig) -> None:
        try:
            await self._notifier.send(
                title=title,
                message=message,
                sound=DEFAULT_SOUND if config.sound_enabled else None,
            )
        except Exception as exc:
            logger.error("Errore notifica desktop: %s", exc)

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
