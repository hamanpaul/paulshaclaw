from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .schema import Card, Combo, ComboEntry


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


@dataclass(frozen=True)
class SliceDoc:
    slice_id: str
    filename: str
    content: str


@dataclass(frozen=True)
class CompileResult:
    task_slug: str
    slices: tuple[SliceDoc, ...]
    checklist: tuple[str, ...]
    verify_commands: tuple[str, ...]
    external: tuple[str, ...]


def _subst(glob: str, slug: str, change: str | None) -> str:
    out = glob.replace("<task-slug>", slug)
    if "<change>" in out:
        if not change:
            raise DeckCompileError("卡片 glob 使用 <change>，需提供 --change <name>")
        out = out.replace("<change>", change)
    return out


def parse_with_spec(spec: str) -> tuple[str, str | None, str | None]:
    if ":" not in spec:
        return spec, None, None
    card_id, _, rest = spec.partition(":")
    kind, _, anchor = rest.partition("=")
    if not card_id or kind not in ("after", "before") or not anchor:
        raise DeckCompileError(f"--with 定位格式錯誤: {spec!r}（card[:after=<id>|:before=<id>]）")
    return card_id, kind, anchor


def _resolve_hand(
    combo: Combo,
    cards: Mapping[str, Card],
    with_cards: Sequence[str],
    only: Sequence[str],
) -> list[ComboEntry]:
    if only:
        combo_refs = {entry.ref for entry in combo.cards}
        unknown = [card_id for card_id in only if card_id not in combo_refs]
        if unknown:
            raise DeckCompileError(f"--only 指定了 combo 外卡片: {unknown}")
        selected = set(only)
        return [entry for entry in combo.cards if entry.ref in selected]

    hand = list(combo.cards)
    for spec in with_cards:
        card_id, kind, anchor = parse_with_spec(spec)
        if card_id not in cards:
            raise DeckCompileError(f"--with 未知卡片: {card_id}")
        refs = [entry.ref for entry in hand]
        if card_id in refs:
            raise DeckCompileError(f"--with 卡片已在骨幹中: {card_id}")

        if kind is None:
            pos: int | None = None
            requires = cards[card_id].requires
            if requires:
                seen: list[str] = []
                for index, entry in enumerate(hand):
                    seen.extend(cards[entry.ref].produces)
                    if all(any(_covered(require, produce) for produce in seen) for require in requires):
                        pos = index + 1
                        break
            if pos is None:
                raise DeckCompileError(
                    f"--with {card_id} 無法推斷插入點，請明示 :after=<id> 或 :before=<id>"
                )
        else:
            if anchor not in refs:
                raise DeckCompileError(f"--with 定位錨點不在手牌中: {anchor}")
            anchor_index = refs.index(anchor)
            pos = anchor_index + (1 if kind == "after" else 0)
        hand.insert(pos, ComboEntry(ref=card_id))
    return hand


def _prefix(glob: str) -> str:
    return glob.split("*", 1)[0]


def _covered(require: str, produce: str) -> bool:
    """保守判斷 produce 是否覆蓋 require 的 pattern 前綴。"""
    require_prefix = _prefix(require)
    produce_prefix = _prefix(produce)
    return require_prefix.startswith(produce_prefix) or produce_prefix.startswith(require_prefix)


def _check_requires_coverage(
    entries: Sequence[ComboEntry],
    cards: Mapping[str, Card],
    allow_external: bool,
) -> tuple[str, ...]:
    upstream: list[str] = []
    external: list[str] = []
    for entry in entries:
        card = cards[entry.ref]
        for require in card.requires:
            if not any(_covered(require, produce) for produce in upstream):
                external.append(f"{card.id}: {require}")
        upstream.extend(card.produces)
    if external and not allow_external:
        raise DeckCompileError(
            "requires 未被上游 produces 覆蓋（external input），"
            "確認後以 --allow-external 放行：\n  " + "\n  ".join(external)
        )
    return tuple(external)


def _group_slices(
    entries: Sequence[ComboEntry],
    cards: Mapping[str, Card],
    slug: str,
) -> list[tuple[str, list[Card]]]:
    groups: list[tuple[str, list[Card]]] = []
    for entry in entries:
        card = cards[entry.ref]
        if card.type != "headless":
            continue
        if card.slice_group:
            slice_id = f"{slug}-{card.slice_group}"
        else:
            slice_id = f"{slug}-{card.id}"
        if groups and groups[-1][0] == slice_id:
            groups[-1][1].append(card)
            continue
        groups.append((slice_id, [card]))
    return groups


def _render_frontmatter(slice_id: str, plan_ref: str, deps: Sequence[str]) -> str:
    lines = [
        "---",
        "dispatch: hold",
        f"slice_id: {slice_id}",
        f"plan: {plan_ref}",
    ]
    if deps:
        lines.append("depends_on:")
        lines.extend(f"  - {dep}" for dep in deps)
    else:
        lines.append("depends_on: []")
    lines.append("---")
    return "\n".join(lines)


def _default_plan_ref(
    entries: Sequence[ComboEntry],
    cards: Mapping[str, Card],
    slug: str,
    change: str | None,
) -> str | None:
    for entry in reversed(entries):
        card = cards[entry.ref]
        if card.type == "interactive" and card.produces:
            return _subst(card.produces[0], slug, change)
    return None


def compile_combo(
    combo: Combo,
    cards: Mapping[str, Card],
    task: str,
    *,
    change: str | None = None,
    with_cards: Sequence[str] = (),
    only: Sequence[str] = (),
    allow_external: bool = False,
    plan_ref: str | None = None,
) -> CompileResult:
    slug = slugify_task(task)
    entries = _resolve_hand(combo, cards, with_cards, only)
    external = _check_requires_coverage(entries, cards, allow_external)

    interactive_cards = [cards[entry.ref] for entry in entries if cards[entry.ref].type == "interactive"]
    checklist = tuple(
        f"[{card.id}] {card.skill_ref} → 產出: "
        + ", ".join(_subst(glob, slug, change) for glob in card.produces)
        for card in interactive_cards
    )
    if plan_ref is None:
        plan_ref = _default_plan_ref(entries, cards, slug, change)
    if plan_ref is None:
        plan_ref = _default_plan_ref(combo.cards, cards, slug, change)
    if not plan_ref:
        raise DeckCompileError("無法決定 plan 參照：無 interactive produces，請給 --plan")

    explicit_deps = {entry.ref: entry.depends_on for entry in entries}
    slices: list[SliceDoc] = []
    verify_commands: list[str] = []
    previous_slice_id: str | None = None

    for slice_id, members in _group_slices(entries, cards, slug):
        deps: list[str] = []
        for member in members:
            for dep_ref in explicit_deps.get(member.id, ()):
                dep_card = cards.get(dep_ref)
                if dep_card is None or dep_card.type != "headless":
                    continue
                if dep_card.slice_group:
                    deps.append(f"{slug}-{dep_card.slice_group}")
                else:
                    deps.append(f"{slug}-{dep_card.id}")
        deps = sorted(set(dep for dep in deps if dep != slice_id))
        if not deps and previous_slice_id:
            deps = [previous_slice_id]

        requires = [_subst(glob, slug, change) for member in members for glob in member.requires]
        produces = [_subst(glob, slug, change) for member in members for glob in member.produces]
        requires_block = "".join(f"\n- {item}" for item in requires) or "\n-（無）"
        produces_block = "".join(f"\n- {item}" for item in produces) or "\n-（無，完成偵測=exit sentinel）"
        content = (
            _render_frontmatter(slice_id, plan_ref, deps)
            + "\n"
            + f"# {slice_id}\n\n"
            + f"任務：{task}\n"
            + f"combo：{combo.id}（cards: {', '.join(member.id for member in members)}）\n\n"
            + f"requires（翻 auto 前人工確認）：{requires_block}\n\n"
            + f"produces（deck verify 驗收）：{produces_block}\n"
        )
        slices.append(SliceDoc(slice_id=slice_id, filename=f"{slice_id}.md", content=content))

        for member in members:
            if member.produces:
                verify_commands.append(f"psc deck verify {member.id} --task-slug {slug}")
        previous_slice_id = slice_id

    return CompileResult(
        task_slug=slug,
        slices=tuple(slices),
        checklist=checklist,
        verify_commands=tuple(dict.fromkeys(verify_commands)),
        external=external,
    )
