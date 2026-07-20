#!/usr/bin/env bash
# Ensure Playwright Chromium is installed for the current venv.
set -euo pipefail

if ! python - <<'PY'
import os
import sys

from playwright.sync_api import sync_playwright

playwright = sync_playwright().start()
try:
    path = playwright.chromium.executable_path
    if not os.path.exists(path):
        sys.exit(1)
finally:
    playwright.stop()
PY
then
  echo "Download browser Playwright (circa 150 MB)..."
  python -m playwright install chromium
fi
