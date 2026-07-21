#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON=""
for candidate in /usr/bin/python3 python3; do
  if [ -x "$candidate" ]; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Errore: nessun Python trovato."
  echo "Su macOS installa Python da https://www.python.org/downloads/"
  exit 1
fi

if [ ! -d ".venv" ]; then
  "$PYTHON" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Verifica pywebview..."
python - <<'PY'
import importlib.metadata
import webview

version = importlib.metadata.version("pywebview")
assert hasattr(webview, "create_window")
print(f"pywebview OK ({version})")
PY

echo ""
echo "Installazione browser Playwright..."
python -m playwright install chromium

# shellcheck disable=SC1091
source "$ROOT/scripts/ensure_playwright.sh"

python - <<'PY'
import os
from playwright.sync_api import sync_playwright

playwright = sync_playwright().start()
try:
    path = playwright.chromium.executable_path
    if os.path.exists(path):
        print(f"Browser installato: {path}")
    else:
        raise SystemExit("Errore: browser Playwright non trovato dopo l'installazione.")
finally:
    playwright.stop()
PY

if [ "$(uname -s)" = "Darwin" ]; then
  echo ""
  echo "Notifiche macOS (terminal-notifier)..."
  if command -v brew >/dev/null 2>&1; then
    if brew list terminal-notifier >/dev/null 2>&1; then
      echo "terminal-notifier già installato."
    else
      brew install terminal-notifier
    fi
  else
    echo "Attenzione: Homebrew non trovato."
    echo "  Le notifiche popup funzioneranno (fallback osascript), ma il click per aprire Outlook no."
    echo "  Installa Homebrew e poi: brew install terminal-notifier"
  fi
fi

echo ""
echo "Installazione completata."
echo "Avvia con: ./scripts/run.sh"
