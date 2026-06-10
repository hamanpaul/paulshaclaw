from __future__ import annotations
from pathlib import Path
import subprocess
from typing import Optional

_DEFAULT_TIMEOUT = 2


def _run_git(args: list[str], cwd: str | Path | None = None, timeout: int = _DEFAULT_TIMEOUT) -> Optional[str]:
    try:
        proc = subprocess.run(["git", *args], cwd=(None if cwd is None else str(cwd)), capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0:
            return proc.stdout.strip()
        return None
    except Exception:
        return None


def git_toplevel(cwd: str | Path) -> Optional[str]:
    """Return repository top-level path for cwd, or None on failure.

    Best-effort, bounded by a short timeout and never raises.
    """
    try:
        return _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    except Exception:
        return None


def git_remote(toplevel: str | Path) -> Optional[str]:
    """Return origin remote URL for the given repository top-level, or None."""
    try:
        return _run_git(["remote", "get-url", "origin"], cwd=toplevel)
    except Exception:
        return None


def sibling_repo_count(toplevel: str | Path) -> int:
    """Count immediate sibling directories of the given toplevel that are git repos.

    Returns 0 on any failure.
    """
    try:
        p = Path(toplevel)
        parent = p.parent
        count = 0
        if not parent.exists():
            return 0
        for child in parent.iterdir():
            if not child.is_dir():
                continue
            # quick check: try to get the repo top-level from the child dir
            top = _run_git(["rev-parse", "--show-toplevel"], cwd=child)
            if top:
                count += 1
        return count
    except Exception:
        return 0
