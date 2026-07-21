#!/usr/bin/env python3
"""Generate Outlook Notifier app icons (Outlook blue calendar + notification)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS_ICON = ROOT / "assets" / "icon.png"
STATIC_ICON = ROOT / "outlook_notifier" / "gui" / "web" / "static" / "icon.png"

OUTLOOK_BLUE = (0, 120, 212, 255)
WHITE = (255, 255, 255, 255)
NOTIFY_ORANGE = (255, 140, 0, 255)


def draw_icon(size: int = 512) -> Image.Image:
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
    cal_radius = size // 24

    draw.rounded_rectangle(
        (cal_left, cal_top, cal_right, cal_bottom),
        radius=cal_radius,
        fill=WHITE,
    )

    header_h = (cal_bottom - cal_top) * 0.22
    draw.rectangle(
        (cal_left, cal_top, cal_right, cal_top + header_h),
        fill=(230, 240, 250, 255),
    )

    ring_r = size // 28
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
    line_w = max(2, size // 128)

    for i in range(1, 2):
        y = grid_top + cell_h * i
        draw.line((grid_left, y, grid_right, y), fill=OUTLOOK_BLUE, width=line_w)
    for i in range(1, 2):
        x = grid_left + cell_w * i
        draw.line((x, grid_top, x, grid_bottom), fill=OUTLOOK_BLUE, width=line_w)

    dot_r = size // 14
    dot_cx = size * 0.76
    dot_cy = size * 0.22
    draw.ellipse(
        (dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r),
        fill=NOTIFY_ORANGE,
    )
    draw.ellipse(
        (dot_cx - dot_r * 0.55, dot_cy - dot_r * 0.55, dot_cx + dot_r * 0.55, dot_cy + dot_r * 0.55),
        fill=WHITE,
    )

    return image


def main() -> None:
    master = draw_icon(512)
    ASSETS_ICON.parent.mkdir(parents=True, exist_ok=True)
    master.save(ASSETS_ICON, format="PNG")

    STATIC_ICON.parent.mkdir(parents=True, exist_ok=True)
    favicon = master.resize((64, 64), Image.Resampling.LANCZOS)
    favicon.save(STATIC_ICON, format="PNG")

    print(f"Wrote {ASSETS_ICON}")
    print(f"Wrote {STATIC_ICON}")


if __name__ == "__main__":
    main()
