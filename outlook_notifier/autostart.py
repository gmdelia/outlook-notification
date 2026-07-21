"""Enable/disable login autostart on macOS, Windows, and Linux."""

from __future__ import annotations

import logging
import os
import platform
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

from outlook_notifier.config import CONFIG_DIR

logger = logging.getLogger(__name__)

_LABEL = "com.outlook-notifier.login"
_MAC_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"
_LINUX_DESKTOP = Path.home() / ".config" / "autostart" / "outlook-notifier.desktop"
_WIN_RUN_NAME = "OutlookNotifier"
_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _python() -> str:
    return sys.executable


def _command() -> list[str]:
    return [_python(), "-m", "outlook_notifier"]


def _windows_command_string() -> str:
    """Run key has no WorkingDirectory; cd into the project first."""
    root = _project_root()
    python = _python()
    return f'cmd.exe /c "cd /d "{root}" && "{python}" -m outlook_notifier"'


def is_enabled() -> bool:
    system = platform.system()
    try:
        if system == "Darwin":
            return _mac_is_enabled()
        if system == "Windows":
            return _win_is_enabled()
        if system == "Linux":
            return _linux_is_enabled()
    except Exception as exc:
        logger.warning("Lettura stato autostart fallita: %s", exc)
    return False


def enable() -> None:
    system = platform.system()
    if system == "Darwin":
        _mac_enable()
    elif system == "Windows":
        _win_enable()
    elif system == "Linux":
        _linux_enable()
    else:
        raise OSError(f"Autostart non supportato su {system}.")


def disable() -> None:
    system = platform.system()
    if system == "Darwin":
        _mac_disable()
    elif system == "Windows":
        _win_disable()
    elif system == "Linux":
        _linux_disable()
    else:
        raise OSError(f"Autostart non supportato su {system}.")


def set_enabled(want: bool) -> None:
    if want:
        enable()
    else:
        disable()


# --- macOS -----------------------------------------------------------------


def _mac_is_enabled() -> bool:
    return _MAC_PLIST.is_file()


def _mac_enable() -> None:
    """Write LaunchAgent for next login; do not bootstrap (would start a 2nd instance now)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _MAC_PLIST.parent.mkdir(parents=True, exist_ok=True)
    log_path = str(CONFIG_DIR / "autostart.log")
    plist = {
        "Label": _LABEL,
        "ProgramArguments": _command(),
        "WorkingDirectory": str(_project_root()),
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
        "EnvironmentVariables": {
            "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        },
    }
    # Unload any previous registration, then write plist for the next login session.
    _mac_unload_quiet()
    _MAC_PLIST.write_bytes(plistlib.dumps(plist))


def _mac_disable() -> None:
    _mac_unload_quiet()
    if _MAC_PLIST.exists():
        _MAC_PLIST.unlink()


def _mac_unload_quiet() -> None:
    uid = os.getuid()
    for cmd in (
        ["launchctl", "bootout", f"gui/{uid}", str(_MAC_PLIST)],
        ["launchctl", "unload", str(_MAC_PLIST)],
    ):
        try:
            subprocess.run(cmd, check=False, capture_output=True, text=True)
        except FileNotFoundError:
            pass


# --- Windows ---------------------------------------------------------------


def _win_is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
            winreg.QueryValueEx(key, _WIN_RUN_NAME)
        return True
    except OSError:
        return False


def _win_enable() -> None:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        _WIN_RUN_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, _WIN_RUN_NAME, 0, winreg.REG_SZ, _windows_command_string())


def _win_disable() -> None:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _WIN_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, _WIN_RUN_NAME)
    except FileNotFoundError:
        pass
    except OSError as exc:
        # ERROR_FILE_NOT_FOUND when value missing
        if getattr(exc, "winerror", None) != 2:
            raise


# --- Linux -----------------------------------------------------------------


def _linux_is_enabled() -> bool:
    return _LINUX_DESKTOP.is_file()


def _linux_enable() -> None:
    _LINUX_DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    cmd = " ".join(shlex.quote(part) for part in _command())
    root = _project_root()
    content = "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            "Name=Outlook Notifier",
            "Comment=Outlook Calendar desktop reminders",
            f"Exec={cmd}",
            f"Path={root}",
            "Terminal=false",
            "X-GNOME-Autostart-enabled=true",
            "",
        ]
    )
    _LINUX_DESKTOP.write_text(content, encoding="utf-8")


def _linux_disable() -> None:
    if _LINUX_DESKTOP.exists():
        _LINUX_DESKTOP.unlink()
