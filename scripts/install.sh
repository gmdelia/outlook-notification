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
import webview
print(f"pywebview OK ({webview.__version__})")
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

echo ""
echo "Installazione completata."
echo "Avvia con: ./scripts/run.sh"
