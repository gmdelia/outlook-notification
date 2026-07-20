"""GUI process launcher with macOS-safe detached mode."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Optional, Sequence

from outlook_notifier import subprocess_registry


def _build_env(env: Optional[Mapping[str, str]]) -> dict[str, str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return merged


def spawn_gui_module(
    module: str,
    *,
    env: Optional[Mapping[str, str]] = None,
    module_args: Optional[Sequence[str]] = None,
) -> subprocess.Popen:
    merged_env = _build_env(env)
    args = list(module_args or [])
    if sys.platform != "darwin":
        return subprocess_registry.spawn(
            [sys.executable, "-m", module, *args],
            env=merged_env,
        )

    merged_env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    repo_root = str(Path(__file__).resolve().parents[2])
    cmd = (
        f'cd "{repo_root}" && '
        f'source ".venv/bin/activate" && '
        f"exec python -m {shlex.quote(module)}"
    )
    if args:
        cmd += " " + " ".join(shlex.quote(part) for part in args)
    return subprocess_registry.spawn(
        ["/bin/bash", "-lc", cmd],
        env=merged_env,
        start_new_session=True,
    )
