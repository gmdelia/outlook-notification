"""Explicit Tk styling for reliable macOS rendering."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Optional

BG = "#ffffff"
FG = "#202124"
FG_SUBTLE = "#5f6368"
BORDER = "#c0c4c9"


def frame(parent: tk.Misc, **kw: Any) -> tk.Frame:
    options = {"bg": BG}
    options.update(kw)
    return tk.Frame(parent, **options)


def label(parent: tk.Misc, text: str = "", **kw: Any) -> tk.Label:
    options = {"bg": BG, "fg": FG, "text": text}
    options.update(kw)
    return tk.Label(parent, **options)


def entry(parent: tk.Misc, textvariable: Optional[tk.Variable] = None, **kw: Any) -> tk.Entry:
    options: dict[str, Any] = {
        "bg": BG,
        "fg": FG,
        "insertbackground": FG,
        "highlightbackground": BORDER,
        "highlightcolor": BORDER,
        "relief": tk.SOLID,
        "bd": 1,
    }
    if textvariable is not None:
        options["textvariable"] = textvariable
    options.update(kw)
    return tk.Entry(parent, **options)


def button(parent: tk.Misc, text: str = "", command: Optional[Any] = None, **kw: Any) -> tk.Button:
    options: dict[str, Any] = {
        "bg": BG,
        "fg": FG,
        "activebackground": BG,
        "activeforeground": FG,
        "text": text,
    }
    if command is not None:
        options["command"] = command
    options.update(kw)
    return tk.Button(parent, **options)


def checkbutton(
    parent: tk.Misc,
    text: str = "",
    variable: Optional[tk.Variable] = None,
    **kw: Any,
) -> tk.Checkbutton:
    options: dict[str, Any] = {
        "bg": BG,
        "fg": FG,
        "activebackground": BG,
        "activeforeground": FG,
        "selectcolor": BG,
        "text": text,
    }
    if variable is not None:
        options["variable"] = variable
    options.update(kw)
    return tk.Checkbutton(parent, **options)
