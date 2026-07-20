"""CLI entry: fire one macOS notification and unload its launchd job."""

from __future__ import annotations

import argparse
import subprocess
import sys

_OSASCRIPT_NOTIFY = """
on run argv
  display notification (item 2 of argv) with title (item 1 of argv)
end run
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    result = subprocess.run(
        ["osascript", "-e", _OSASCRIPT_NOTIFY, args.title, args.message],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        print(err or f"osascript exit {result.returncode}", file=sys.stderr)

    subprocess.run(
        ["launchctl", "bootout", f"gui/{_gui_uid()}", args.label],
        capture_output=True,
        text=True,
    )
    return result.returncode


def _gui_uid() -> int:
    import os

    try:
        return os.getuid()
    except AttributeError:
        return int(subprocess.check_output(["id", "-u"], text=True).strip())


if __name__ == "__main__":
    raise SystemExit(main())
