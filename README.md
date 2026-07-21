# Outlook Calendar Notifier

A desktop app for **macOS, Windows, and Linux** that reads your **Outlook Web** calendar and sends **desktop notifications with sound** before today’s appointments.

No Azure app registration or admin consent is required. The app uses your Outlook Web browser session and keeps all data on your machine.

## Features

- One-time browser login (supports company MFA)
- Automatic sync every few minutes
- Configurable reminders (for example 15 and 5 minutes before), plus always at event start
- Desktop notifications with popup + sound
- System tray icon with menu
- Today’s events window and settings window (native WebView via **pywebview**)

## Requirements

- **Python 3.9+**
- Access to Outlook Web (`https://outlook.office.com`)
- A desktop environment with a system tray / notification area

### GUI backend (pywebview)

| Platform | Backend | Extra system setup |
|----------|---------|--------------------|
| **macOS** | WebKit (built-in) | None |
| **Windows** | Edge WebView2 | [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) (usually already installed on Windows 11) |
| **Linux** | GTK + WebKitGTK | Install distro packages (examples below) |

**Debian / Ubuntu example:**

```bash
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

If `gir1.2-webkit2-4.1` is not available, try `gir1.2-webkit2-4.0`.

## Install

### macOS and Linux

```bash
chmod +x scripts/install.sh scripts/run.sh scripts/verify_gui.sh
./scripts/install.sh
```

The install script creates a virtualenv, installs Python dependencies (including **pywebview**), downloads Chromium for Playwright, and on **macOS** installs `terminal-notifier` via Homebrew when available (for native notifications with click-to-open).

### Windows

Use PowerShell or Command Prompt from the project folder:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
```

Confirm WebView2 is installed (Windows 11 usually has it). If windows fail to open, install the [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).

> The provided `scripts/*.sh` helpers are for macOS/Linux shells. On Windows, use the commands above (or run the scripts under Git Bash / WSL if you prefer).

## Start

### macOS and Linux

```bash
./scripts/run.sh
```

### Windows

```bat
.venv\Scripts\activate
python -m outlook_notifier
```

### First run / login

On first start, Chromium opens so you can sign in to Outlook Web. The session is stored locally:

| Platform | Config directory |
|----------|------------------|
| macOS / Linux | `~/.outlook-notifier/` |
| Windows | `%USERPROFILE%\.outlook-notifier\` |

If the browser does not appear, use **Login Outlook** from the tray menu.

To force a fresh login:

**macOS / Linux**

```bash
rm ~/.outlook-notifier/session.ok
./scripts/run.sh
```

**Windows**

```bat
del %USERPROFILE%\.outlook-notifier\session.ok
.venv\Scripts\activate
python -m outlook_notifier
```

## Using the app

After start, look for the **Outlook Notifier** icon in the system tray (menu bar / notification area).

| Menu item (Italian UI) | Meaning |
|------------------------|---------|
| **Eventi di oggi** | Open today’s events timeline |
| **Impostazioni** | Open settings |
| **Login Outlook** | Open the login browser |
| **Sincronizza ora** | Sync calendar now |
| **Riconnetti** | Clear session and log in again |
| **Esci** | Quit the app |

## Settings

Open **Impostazioni** from the tray menu.

| Option | Default |
|--------|---------|
| Start at login | off (toggle registers OS autostart) |
| Show events on startup | on |
| Sync interval | 5 minutes |
| Reminders | 15, 5 minutes before (+ always at event start) |
| Popup notifications | on |
| Sound | on |
| Custom sound file | optional |
| All-day event reminders | on |
| All-day reminder time | 09:00 |
| Timezone (IANA) | system / configured |
| Outlook URL | `https://outlook.office.com` |

**Reminder behavior:** The app always sends a notification when a timed event starts (in addition to your configured advance reminders). If a sync was late or the PC was asleep, missed advance reminders are sent on the next successful sync (with a dynamic title based on remaining minutes). The at-start reminder is retried until the event ends.

**Start at login** (`Avvia all'accesso del sistema`) enables or removes the OS login item. The checkbox reflects the real OS state (not only `config.json`):

| Platform | Mechanism |
|----------|-----------|
| macOS | LaunchAgent `~/Library/LaunchAgents/com.outlook-notifier.login.plist` |
| Windows | Registry `HKCU\…\Run\OutlookNotifier` |
| Linux | `~/.config/autostart/outlook-notifier.desktop` |

Settings (except that OS registration) are saved in `config.json` inside the config directory above.

## Notifications

### macOS

Popup banners use [`terminal-notifier`](https://github.com/julienXX/terminal-notifier) installed via Homebrew (`brew install terminal-notifier`). The install script tries to install it automatically when Homebrew is available.

Clicking a reminder notification opens the Outlook Web event page when a `web_link` is available.

If `terminal-notifier` is not installed, the app falls back to `osascript` (popup without click-to-open).

Use **Impostazioni → Prova notifica** to test popup, sound, and click behavior with your current settings.

If banners do not appear:

1. Open **System Settings → Notifications**
2. Find **terminal-notifier**, **Script Editor**, **osascript**, or **Python**
3. Allow notifications and banners

The app also plays a system sound (`afplay`) alongside the popup for more reliable audio.

### Windows

Allow notifications for Python / the app in **Settings → System → Notifications**. Clicking a notification opens the Outlook calendar URL when supported.

### Linux

Depends on your desktop environment. Ensure a notification daemon is running (for example GNOME, KDE, or a Freedesktop-compatible notifier). Sound support varies by environment. Click-to-open uses the desktop notification handler when available.

## Local data

```
~/.outlook-notifier/          # or %USERPROFILE%\.outlook-notifier\ on Windows
├── config.json               # settings
├── state.json                # reminders already sent today
├── events_today.json         # cached events for the UI
├── session.ok                # login marker
└── browser_profile/          # Outlook Web browser session
```

This folder is **personal runtime data**. Do not commit it to git.

## Troubleshooting

### `Executable doesn't exist` (Playwright)

Chromium for Playwright is missing or mismatched with the venv:

```bash
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m playwright install chromium
```

Or reinstall:

```bash
./scripts/install.sh               # Windows: recreate venv + pip install + playwright install
```

On macOS/Linux, `run.sh` also tries to ensure the browser is present.

### Calendar `403 Forbidden`

Some tenants block certain APIs. This app reads the calendar by intercepting Outlook Web traffic. Try:

1. Tray → **Riconnetti** and complete login
2. Confirm today’s events are visible in Outlook Web
3. Tray → **Sincronizza ora**

### Settings / events window does not open

Windows use **pywebview**:

```bash
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -c "import importlib.metadata, webview; print(importlib.metadata.version('pywebview'))"
./scripts/verify_gui.sh            # macOS/Linux helper
```

- **Windows:** install/repair [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)
- **Linux:** install GTK + WebKitGTK packages (see Requirements)
- If `import webview` fails, reinstall dependencies with `pip install -r requirements.txt`

## Limitations

- Depends on Outlook Web stability (Microsoft UI/API changes may require updates)
- Requires Chromium (~150 MB) via Playwright
- Personal automation: no calendar data is sent to third-party servers

## Development

```bash
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m outlook_notifier
```

### App icon

The tray and window favicons use [`assets/icon.png`](assets/icon.png) (Outlook blue calendar + notification dot). Regenerate with:

```bash
python scripts/generate_icon.py
```

This also updates [`outlook_notifier/gui/web/static/icon.png`](outlook_notifier/gui/web/static/icon.png) for the Settings and Events windows.

Optional GUI probe (macOS/Linux):

```bash
./scripts/verify_gui.sh
```

## License

This project is released under the [MIT License](LICENSE). Free to use, modify, and share.
