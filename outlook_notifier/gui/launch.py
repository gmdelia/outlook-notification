"""GUI process launcher with macOS-safe detached mode."""

from __future__ import annotations

import os
import subprocess
import sys
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
    cmd = [sys.executable, "-m", module, *args]

    if sys.platform == "darwin":
        # Detach from pystray/ObjC parent; avoid bash -lc so login profiles
        # (e.g. sdkman on macOS bash 3.2) are not sourced.
        merged_env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
        return subprocess_registry.spawn(
            cmd,
            env=merged_env,
            start_new_session=True,
        )

    return subprocess_registry.spawn(cmd, env=merged_env)
