"""Track and terminate child processes spawned by the app."""

from __future__ import annotations

import logging
import subprocess
import threading
from typing import IO, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_children: List[subprocess.Popen] = []


def _prune_exited() -> None:
    global _children
    _children = [proc for proc in _children if proc.poll() is None]


def spawn(
    args: Sequence[str],
    *,
    env: Optional[Mapping[str, str]] = None,
    stdout: Optional[int | IO] = None,
    stderr: Optional[int | IO] = None,
    start_new_session: bool = False,
) -> subprocess.Popen:
    with _lock:
        _prune_exited()
        proc = subprocess.Popen(
            list(args),
            env=env,
            stdout=stdout,
            stderr=stderr,
            start_new_session=start_new_session,
        )
        _children.append(proc)
        return proc


def run(args: Sequence[str], *, env: Optional[Mapping[str, str]] = None) -> int:
    proc = spawn(args, env=env)
    return proc.wait()


def terminate_all(timeout: float = 5.0) -> None:
    with _lock:
        _prune_exited()
        active = list(_children)

    for proc in active:
        if proc.poll() is not None:
            continue
        logger.info("Terminazione processo figlio pid=%s", proc.pid)
        try:
            proc.terminate()
        except OSError as exc:
            logger.debug("terminate pid=%s: %s", proc.pid, exc)

    for proc in active:
        if proc.poll() is not None:
            continue
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("Kill forzato processo figlio pid=%s", proc.pid)
            try:
                proc.kill()
                proc.wait(timeout=2)
            except OSError as exc:
                logger.debug("kill pid=%s: %s", proc.pid, exc)

    with _lock:
        _prune_exited()
