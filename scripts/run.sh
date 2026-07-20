#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d ".venv" ]; then
  echo "Esegui prima ./scripts/install.sh"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# shellcheck disable=SC1091
source "$ROOT/scripts/ensure_playwright.sh"

export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
python -m outlook_notifier
