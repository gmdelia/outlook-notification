"""Today's events window with a vertical timeline."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from typing import List, Optional

from outlook_notifier import events_store
from outlook_notifier.gui import theme

WIN_W = 560
WIN_H = 680

AXIS_X = 88
MARGIN_TOP = 24
MARGIN_BOTTOM = 24
DOT_R = 5
DOT_R_NEXT = 8
ROW_MIN_GAP = 34

COLOR_AXIS = "#9aa0a6"
COLOR_TICK = "#c0c4c9"
COLOR_NOW = "#d93025"
COLOR_PAST = "#9aa0a6"
COLOR_EVENT = "#1a73e8"
COLOR_NEXT = "#188038"
COLOR_TEXT = theme.FG
COLOR_SUBTLE = theme.FG_SUBTLE


class EventsWindow:
    def __init__(self, root: tk.Tk, *, auto_refresh: bool = True) -> None:
        self._root = root
        self._auto_refresh = auto_refresh
        self._last_synced_at: Optional[str] = None
        self._last_render_minute: Optional[str] = None
        self._events: List[dict] = []
        self._build()
        self._refresh()
        if auto_refresh:
            self.schedule_render()

    def _build(self) -> None:
        self._root.configure(bg=theme.BG)

        header = theme.frame(self._root)
        header.pack(fill=tk.X, padx=16, pady=(14, 6))

        self._title_label = theme.label(
            header,
            text="Eventi di oggi",
            font=("Helvetica", 16, "bold"),
        )
        self._title_label.pack(anchor=tk.W)

        self._status_label = theme.label(
            header,
            text="Sincronizzazione in corso…",
            font=("Helvetica", 11),
            fg=COLOR_SUBTLE,
        )
        self._status_label.pack(anchor=tk.W)

        self._allday_frame = theme.frame(self._root)
        self._allday_frame.pack(fill=tk.X, padx=16, pady=(0, 4))

        self._canvas = tk.Canvas(
            self._root,
            bg=theme.BG,
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self._canvas.bind("<Configure>", lambda _e: self._render())

    def force_render(self) -> None:
        if not self._root.winfo_exists():
            return
        self._render()

    def schedule_render(self) -> None:
        if not self._root.winfo_exists():
            return
        self._root.after(0, self.force_render)
        self._root.after(200, self.force_render)

    def _refresh(self) -> None:
        data = events_store.load_events()
        changed = False
        if data is None:
            if self._last_synced_at is not None:
                self._events = []
                self._last_synced_at = None
                changed = True
        else:
            synced_at = data.get("synced_at")
            if synced_at != self._last_synced_at:
                self._events = data.get("events", [])
                self._last_synced_at = synced_at
                changed = True

        current_minute = datetime.now().strftime("%H:%M")
        if changed or current_minute != self._last_render_minute:
            self._last_render_minute = current_minute
            self._update_status(data)
            self._render()

        if self._auto_refresh:
            self._root.after(3000, self._refresh)

    def _update_status(self, data: Optional[dict]) -> None:
        today = datetime.now().strftime("%A %d %B %Y")
        self._title_label.config(text=f"Eventi di oggi — {today}")
        if data is None:
            self._status_label.config(text="In attesa della prima sincronizzazione…")
            return
        synced = data.get("synced_at")
        try:
            when = datetime.fromisoformat(synced).strftime("%H:%M:%S")
            suffix = f"Ultima sincronizzazione: {when}"
        except (TypeError, ValueError):
            suffix = "Sincronizzato"
        count = len(self._events)
        self._status_label.config(text=f"{count} eventi · {suffix}")

    def _parse(self, iso: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(iso)
        except (TypeError, ValueError):
            return None

    def _render(self) -> None:
        for child in self._allday_frame.winfo_children():
            child.destroy()
        self._canvas.delete("all")

        all_day = [e for e in self._events if e.get("is_all_day")]
        timed = []
        for e in self._events:
            if e.get("is_all_day"):
                continue
            start = self._parse(e.get("start", ""))
            end = self._parse(e.get("end", ""))
            if start is None:
                continue
            timed.append((start, end, e))
        timed.sort(key=lambda t: t[0])

        if all_day:
            theme.label(
                self._allday_frame,
                text="Tutto il giorno",
                font=("Helvetica", 11, "bold"),
                fg=COLOR_SUBTLE,
            ).pack(anchor=tk.W)
            for e in all_day:
                text = e.get("subject", "(Senza titolo)")
                loc = e.get("location", "")
                if loc:
                    text += f"  ·  {loc}"
                theme.label(
                    self._allday_frame,
                    text=f"•  {text}",
                    font=("Helvetica", 11),
                    anchor=tk.W,
                    justify=tk.LEFT,
                ).pack(anchor=tk.W)

        if not timed:
            message = (
                "In attesa della sincronizzazione…"
                if self._last_synced_at is None
                else "Nessun evento con orario per oggi."
            )
            self._canvas.create_text(
                max(self._canvas.winfo_width(), WIN_W) // 2,
                60,
                text=message,
                fill=COLOR_SUBTLE,
                font=("Helvetica", 12),
                anchor=tk.N,
            )
            return

        self._draw_timeline(timed)

    def _draw_timeline(self, timed: List[tuple]) -> None:
        now = datetime.now().astimezone()
        width = self._canvas.winfo_width() or WIN_W
        height = self._canvas.winfo_height() or (WIN_H - 160)

        first_start = timed[0][0]
        last_end = max((end or start) for start, end, _ in timed)

        t_min = min(first_start, now) - timedelta(minutes=30)
        t_max = max(last_end, now) + timedelta(minutes=30)
        span = (t_max - t_min).total_seconds()
        if span <= 0:
            span = 3600.0

        top = MARGIN_TOP
        bottom = height - MARGIN_BOTTOM
        usable = max(1, bottom - top)

        def y_of(t: datetime) -> float:
            return top + (t - t_min).total_seconds() / span * usable

        self._canvas.create_line(
            AXIS_X, top, AXIS_X, bottom, fill=COLOR_AXIS, width=2
        )

        tick = t_min.replace(minute=0, second=0, microsecond=0)
        if tick < t_min:
            tick += timedelta(hours=1)
        while tick <= t_max:
            y = y_of(tick)
            self._canvas.create_line(AXIS_X - 6, y, AXIS_X, y, fill=COLOR_TICK)
            self._canvas.create_text(
                AXIS_X - 12,
                y,
                text=tick.strftime("%H:%M"),
                anchor=tk.E,
                fill=COLOR_SUBTLE,
                font=("Helvetica", 9),
            )
            tick += timedelta(hours=1)

        next_idx = None
        for i, (start, _end, _e) in enumerate(timed):
            if start >= now:
                next_idx = i
                break

        last_text_y = None
        for i, (start, end, e) in enumerate(timed):
            y = y_of(start)
            is_next = i == next_idx
            is_past = start < now and not is_next
            color = COLOR_NEXT if is_next else (COLOR_PAST if is_past else COLOR_EVENT)
            r = DOT_R_NEXT if is_next else DOT_R

            self._canvas.create_oval(
                AXIS_X - r, y - r, AXIS_X + r, y + r,
                fill=color, outline=color,
            )

            text_y = y
            if last_text_y is not None and text_y < last_text_y + ROW_MIN_GAP:
                text_y = last_text_y + ROW_MIN_GAP
            last_text_y = text_y

            if abs(text_y - y) > 2:
                self._canvas.create_line(
                    AXIS_X + r, y, AXIS_X + 16, text_y, fill=color
                )

            time_str = start.strftime("%H:%M")
            if end is not None:
                time_str += f"–{end.strftime('%H:%M')}"
            subject = e.get("subject", "(Senza titolo)")
            font_style = ("Helvetica", 11, "bold") if is_next else ("Helvetica", 11)

            label = f"{time_str}   {subject}"
            self._canvas.create_text(
                AXIS_X + 22,
                text_y - 7,
                text=label,
                anchor=tk.W,
                fill=COLOR_TEXT if not is_past else COLOR_SUBTLE,
                font=font_style,
                width=width - AXIS_X - 90,
            )

            second_line = e.get("location", "")
            if is_next:
                badge = "► prossimo"
                second_line = f"{badge}   {second_line}".strip()
            if second_line:
                self._canvas.create_text(
                    AXIS_X + 22,
                    text_y + 8,
                    text=second_line,
                    anchor=tk.W,
                    fill=COLOR_NEXT if is_next else COLOR_SUBTLE,
                    font=("Helvetica", 9, "bold") if is_next else ("Helvetica", 9),
                    width=width - AXIS_X - 90,
                )

        if t_min <= now <= t_max:
            yn = y_of(now)
            self._canvas.create_line(
                AXIS_X - 20, yn, width - 12, yn,
                fill=COLOR_NOW, width=1, dash=(4, 3),
            )
            self._canvas.create_text(
                AXIS_X - 20,
                yn - 8,
                text=f"Adesso {now.strftime('%H:%M')}",
                anchor=tk.W,
                fill=COLOR_NOW,
                font=("Helvetica", 9, "bold"),
            )
