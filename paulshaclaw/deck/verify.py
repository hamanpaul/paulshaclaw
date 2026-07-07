from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import Card


@dataclass(frozen=True)
class VerifyResult:
    card_id: str
    ok: bool
    missing: tuple[str, ...]
    matched: tuple[str, ...]


def _subst(glob: str, task_slug: str, change: str | None) -> str:
    out = glob.replace("<task-slug>", task_slug)
    if change:
        out = out.replace("<change>", change)
    return out


def verify_card(
    card: Card,
    task_slug: str,
    *,
    root: str | Path = ".",
    change: str | None = None,
) -> VerifyResult:
    """produces glob 存在性驗收（Phase A：只驗存在，不驗內容）。"""
    base = Path(root)
    missing: list[str] = []
    matched: list[str] = []
    for raw in card.produces:
        pattern = _subst(raw, task_slug, change)
        hits = list(base.glob(pattern))
        if hits:
            matched.append(pattern)
        else:
            missing.append(raw if pattern == raw else pattern)
    return VerifyResult(
        card_id=card.id,
        ok=not missing,
        missing=tuple(missing),
        matched=tuple(matched),
    )
