"""System tray icon and menu."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

OUTLOOK_BLUE = (0, 120, 212, 255)
TRAY_ICON_SIZE = 64
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"


def _draw_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = size // 8
    radius = size // 5
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=radius,
        fill=OUTLOOK_BLUE,
    )

    cal_left = size * 0.22
    cal_top = size * 0.24
    cal_right = size * 0.78
    cal_bottom = size * 0.78
    cal_radius = max(1, size // 24)

    draw.rounded_rectangle(
        (cal_left, cal_top, cal_right, cal_bottom),
        radius=cal_radius,
        fill=(255, 255, 255, 255),
    )

    header_h = (cal_bottom - cal_top) * 0.22
    draw.rectangle(
        (cal_left, cal_top, cal_right, cal_top + header_h),
        fill=(230, 240, 250, 255),
    )

    ring_r = max(1, size // 28)
    ring_y = cal_top + header_h * 0.45
    for ring_x in (cal_left + (cal_right - cal_left) * 0.32, cal_left + (cal_right - cal_left) * 0.68):
        draw.ellipse(
            (ring_x - ring_r, ring_y - ring_r, ring_x + ring_r, ring_y + ring_r),
            fill=OUTLOOK_BLUE,
        )

    grid_top = cal_top + header_h + (cal_bottom - cal_top - header_h) * 0.12
    grid_left = cal_left + (cal_right - cal_left) * 0.15
    grid_right = cal_right - (cal_right - cal_left) * 0.15
    grid_bottom = cal_bottom - (cal_bottom - cal_top) * 0.12
    cell_w = (grid_right - grid_left) / 2
    cell_h = (grid_bottom - grid_top) / 2
    line_w = max(1, size // 128)

    for i in range(1, 2):
        y = grid_top + cell_h * i
        draw.line((grid_left, y, grid_right, y), fill=OUTLOOK_BLUE, width=line_w)
    for i in range(1, 2):
        x = grid_left + cell_w * i
        draw.line((x, grid_top, x, grid_bottom), fill=OUTLOOK_BLUE, width=line_w)

    dot_r = max(2, size // 14)
    dot_cx = size * 0.76
    dot_cy = size * 0.22
    draw.ellipse(
        (dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r),
        fill=(255, 140, 0, 255),
    )
    inner_r = dot_r * 0.55
    draw.ellipse(
        (dot_cx - inner_r, dot_cy - inner_r, dot_cx + inner_r, dot_cy + inner_r),
        fill=(255, 255, 255, 255),
    )

    return image


def _default_icon(size: int = TRAY_ICON_SIZE) -> Image.Image:
    return _draw_icon(size)


def _load_icon() -> Image.Image:
    icon_path = ASSETS_DIR / "icon.png"
    if icon_path.exists():
        return Image.open(icon_path).convert("RGBA").resize(
            (TRAY_ICON_SIZE, TRAY_ICON_SIZE),
            Image.Resampling.LANCZOS,
        )
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
