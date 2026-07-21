"""Desktop notifications with popup and sound."""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path

from desktop_notifier import DEFAULT_SOUND, DesktopNotifier

from outlook_notifier.config import AppConfig

logger = logging.getLogger(__name__)

DEFAULT_MAC_SOUND = "/System/Library/Sounds/Glass.aiff"
NOTIFICATION_GROUP = "outlook-notifier"


def mac_terminal_notifier_path() -> Path | None:
    path = shutil.which("terminal-notifier")
    if path:
        return Path(path)
    return None

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
        url: str | None = None,
    ) -> None:
        cfg = config or self._config
        if not cfg.notifications_enabled:
            return

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._send_popup(title, message, cfg, url),
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

    async def _send_popup(
        self,
        title: str,
        message: str,
        config: AppConfig,
        url: str | None = None,
    ) -> None:
        try:
            if platform.system() == "Darwin":
                from desktop_notifier.backends.macos_support import is_bundle

                if not is_bundle():
                    self._send_macos_popup(title, message, url)
                    return

            on_clicked = None
            if url:
                on_clicked = lambda: webbrowser.open(url)

            await self._notifier.send(
                title=title,
                message=message,
                sound=DEFAULT_SOUND if config.sound_enabled else None,
                on_clicked=on_clicked,
            )
        except Exception as exc:
            logger.error("Errore notifica desktop: %s", exc)

    def _send_macos_popup(self, title: str, message: str, url: str | None = None) -> None:
        notifier_path = mac_terminal_notifier_path()
        if notifier_path:
            cmd = [
                str(notifier_path),
                "-title",
                title,
                "-message",
                message,
                "-group",
                NOTIFICATION_GROUP,
            ]
            if url:
                cmd.extend(["-open", url])
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        script = (
            f"display notification {json.dumps(message)} "
            f"with title {json.dumps(title)}"
        )
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

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
