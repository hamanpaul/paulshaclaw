from __future__ import annotations

import os
import re
from pathlib import Path


class DeckCompileError(ValueError):
    """compile 期錯誤（fail-closed：不產任何檔）。"""


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_task(task: str) -> str:
    """將 task 正規化為 branch-safe slug。"""
    slug = _SLUG_RE.sub("-", task.lower()).strip("-")[:60].strip("-")
    if not slug:
        raise DeckCompileError(f"task 無法正規化為 slug: {task!r}")
    return slug


def specs_dir() -> Path:
    """鏡射 manager_daemon.default_specs_dir 的 specs 路徑契約。"""
    override = os.environ.get("PSC_MANAGER_SPECS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".agents" / "specs"
