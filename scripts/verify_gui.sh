#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

source ".venv/bin/activate"

python - <<'PY'
import json

from outlook_notifier.config import CONFIG_DIR, EVENTS_FILE
from outlook_notifier.gui.launch import spawn_gui_module

probe_file = CONFIG_DIR / "gui_probe.json"


def run_probe(module: str) -> dict:
    if probe_file.exists():
        probe_file.unlink()
    proc = spawn_gui_module(module, module_args=["--probe"])
    proc.wait(timeout=30)
    if proc.returncode != 0:
        raise SystemExit(f"{module} probe failed with exit code {proc.returncode}")
    if not probe_file.exists():
        raise SystemExit(f"{module} probe did not create {probe_file}")
    return json.loads(probe_file.read_text(encoding="utf-8"))


events = run_probe("outlook_notifier.gui.events_app")
if events.get("engine") != "pywebview":
    raise SystemExit("events_app probe failed: expected engine pywebview")
if not events.get("html_exists"):
    raise SystemExit("events_app probe failed: events.html missing")
if not events.get("status_nonempty"):
    raise SystemExit("events_app probe failed: empty status text")
if events.get("events", 0) < 0:
    raise SystemExit("events_app probe failed: invalid events count")
if EVENTS_FILE.exists() and events.get("events", 0) < 1:
    raise SystemExit("events_app probe failed: cache has events but probe reported none")

settings = run_probe("outlook_notifier.gui.settings_app")
if settings.get("engine") != "pywebview":
    raise SystemExit("settings_app probe failed: expected engine pywebview")
if not settings.get("html_exists"):
    raise SystemExit("settings_app probe failed: settings.html missing")
if settings.get("fields", 0) < 6:
    raise SystemExit("settings_app probe failed: expected at least 6 config fields")

print("GUI probe passed")
print(json.dumps({"events": events, "settings": settings}, ensure_ascii=False, indent=2))
PY
