"""System tray icon and menu."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def _default_icon(size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 120, 212, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, size - 8, size - 8), fill=(255, 255, 255, 255))
    draw.rectangle((size // 2 - 4, 18, size // 2 + 4, size - 18), fill=(0, 120, 212, 255))
    draw.rectangle((18, size // 2 - 4, size - 18, size // 2 + 4), fill=(0, 120, 212, 255))
    return image


def _load_icon() -> Image.Image:
    icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png"
    if icon_path.exists():
        return Image.open(icon_path).convert("RGBA")
    return _default_icon()


class TrayIcon:
    def __init__(
        self,
        on_open_events: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_sync_now: Callable[[], None],
        on_reconnect: Callable[[], None],
        on_login: Callable[[], None],
        on_quit: Callable[[], None],
        get_status: Callable[[], str],
    ) -> None:
        self._on_open_events = on_open_events
        self._on_open_settings = on_open_settings
        self._on_sync_now = on_sync_now
        self._on_reconnect = on_reconnect
        self._on_login = on_login
        self._on_quit = on_quit
        self._get_status = get_status
        self._icon: Optional[pystray.Icon] = None

    def run(self, setup: Optional[Callable[[pystray.Icon], None]] = None) -> None:
        menu = pystray.Menu(
            pystray.MenuItem(
                "Eventi di oggi",
                lambda: self._on_open_events(),
                default=True,
            ),
            pystray.MenuItem("Impostazioni", lambda: self._on_open_settings()),
            pystray.MenuItem("Login Outlook", lambda: self._on_login()),
            pystray.MenuItem("Sincronizza ora", lambda: self._on_sync_now()),
            pystray.MenuItem("Riconnetti", lambda: self._on_reconnect()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Esci", lambda: self._stop()),
        )
        self._icon = pystray.Icon(
            "outlook-notifier",
            _load_icon(),
            "Outlook Notifier",
            menu,
        )

        def _setup(icon: pystray.Icon) -> None:
            icon.visible = True
            if setup:
                setup(icon)

        self._icon.run(_setup)

    def _stop(self) -> None:
        self._on_quit()
        if self._icon:
            self._icon.stop()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def update_tooltip(self, message: str) -> None:
        if self._icon:
            self._icon.title = f"Outlook Notifier — {message}"
