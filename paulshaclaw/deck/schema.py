from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import yaml

SCHEMA_VERSION = 0
# runtime 契約真相源：coordinator/autonomy.py::parse_spec_frontmatter（勿發明多餘欄位）
EMITTED_FRONTMATTER_FIELDS = ("dispatch", "slice_id", "plan", "depends_on")
CARD_KINDS = ("skill",)
CARD_TYPES = ("interactive", "headless")
CARD_CLASSES = ("core", "niche", "emergency")
ALLOWED_PLACEHOLDERS = frozenset({"task-slug", "change"})
_PLACEHOLDER_RE = re.compile(r"<([a-z0-9-]+)>")

DEFAULT_CARDS_PATH = Path(__file__).with_name("data") / "cards.yaml"
DEFAULT_COMBOS_DIR = Path(__file__).with_name("data") / "combos"


class DeckSchemaError(ValueError):
    """deck 資料載入／驗證錯誤（fail-closed：任一錯即整批拒載）。"""


@dataclass(frozen=True)
class Card:
    id: str
    kind: str
    type: str
    card_class: str  # YAML key: class
    skill_ref: str
    requires: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    persona_binding: str | None = None
    provider_binding: str | None = None
    slice_group: str | None = None


@dataclass(frozen=True)
class ComboEntry:
    ref: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateCheck:
    after: str
    exists: tuple[str, ...]


@dataclass(frozen=True)
class Combo:
    id: str
    task_type: str
    cards: tuple[ComboEntry, ...]
    gate_spine: tuple[GateCheck, ...] = ()


def _check_placeholders(card_id: str, globs: tuple[str, ...], errors: list[str]) -> None:
    for g in globs:
        for name in _PLACEHOLDER_RE.findall(g):
            if name not in ALLOWED_PLACEHOLDERS:
                errors.append(f"{card_id}: 非法佔位符 <{name}>（白名單: {sorted(ALLOWED_PLACEHOLDERS)}）")


def _str_tuple(value, card_id: str, field_name: str, errors: list[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        errors.append(f"{card_id}: {field_name} 必須是字串清單")
        return ()
    return tuple(value)


def load_cards(path: str | Path) -> dict[str, Card]:
    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DeckSchemaError(f"cards 載入失敗: {source}: {exc}") from exc
    if not isinstance(raw, Mapping) or not isinstance(raw.get("cards"), list):
        raise DeckSchemaError(f"cards 格式錯誤（缺 cards 清單）: {source}")

    errors: list[str] = []
    cards: dict[str, Card] = {}
    for rec in raw["cards"]:
        if not isinstance(rec, Mapping) or not isinstance(rec.get("id"), str) or not rec["id"]:
            errors.append("卡片缺 id 或格式錯誤")
            continue
        cid = rec["id"]
        if cid in cards:
            errors.append(f"{cid}: 重複的 card id")
            continue
        kind = rec.get("kind")
        ctype = rec.get("type")
        cclass = rec.get("class")
        skill_ref = rec.get("skill_ref")
        if kind not in CARD_KINDS:
            errors.append(f"{cid}: kind 非法值 {kind!r}")
        if ctype not in CARD_TYPES:
            errors.append(f"{cid}: type 非法值 {ctype!r}")
        if cclass not in CARD_CLASSES:
            errors.append(f"{cid}: class 非法值 {cclass!r}")
        if not isinstance(skill_ref, str) or not skill_ref:
            errors.append(f"{cid}: skill_ref 必須為非空字串")
        requires = _str_tuple(rec.get("requires"), cid, "requires", errors)
        produces = _str_tuple(rec.get("produces"), cid, "produces", errors)
        _check_placeholders(cid, requires + produces, errors)
        slice_group = rec.get("slice_group")
        if slice_group is not None and (not isinstance(slice_group, str) or not slice_group):
            errors.append(f"{cid}: slice_group 必須為非空字串")
        if errors:
            continue
        cards[cid] = Card(
            id=cid,
            kind=kind,
            type=ctype,
            card_class=cclass,
            skill_ref=skill_ref,
            requires=requires,
            produces=produces,
            persona_binding=rec.get("persona_binding"),
            provider_binding=rec.get("provider_binding"),
            slice_group=slice_group,
        )
    if errors:
        raise DeckSchemaError(f"cards 驗證失敗: {source}: " + "; ".join(errors))
    return cards


def _detect_combo_cycles(entries: tuple[ComboEntry, ...]) -> None:
    graph = {e.ref: list(e.depends_on) for e in entries}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {ref: WHITE for ref in graph}
    stack: list[str] = []

    def visit(node: str) -> None:
        color[node] = GRAY
        stack.append(node)
        for dep in graph.get(node, []):
            if dep not in graph:
                continue
            if color[dep] == GRAY:
                cycle = stack[stack.index(dep):] + [dep]
                raise DeckSchemaError(f"combo depends_on 循環相依: {' -> '.join(cycle)}")
            if color[dep] == WHITE:
                visit(dep)
        stack.pop()
        color[node] = BLACK

    for ref in graph:
        if color[ref] == WHITE:
            visit(ref)


def load_combo(path: str | Path, cards: Mapping[str, Card]) -> Combo:
    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DeckSchemaError(f"combo 載入失敗: {source}: {exc}") from exc
    if not isinstance(raw, Mapping) or not isinstance(raw.get("combo"), Mapping):
        raise DeckSchemaError(f"combo 格式錯誤（缺 combo 區塊）: {source}")
    rec = raw["combo"]

    errors: list[str] = []
    combo_id = rec.get("id")
    task_type = rec.get("task_type")
    if not isinstance(combo_id, str) or not combo_id:
        errors.append("combo 缺 id")
    if not isinstance(task_type, str) or not task_type:
        errors.append("combo 缺 task_type")

    entries: list[ComboEntry] = []
    raw_cards = rec.get("cards")
    if not isinstance(raw_cards, list) or not raw_cards:
        errors.append("combo.cards 必須為非空清單")
        raw_cards = []
    seen: set[str] = set()
    for item in raw_cards:
        if not isinstance(item, Mapping) or not isinstance(item.get("ref"), str):
            errors.append("combo.cards 項目缺 ref")
            continue
        ref = item["ref"]
        if ref not in cards:
            errors.append(f"未知卡片引用: {ref}")
        if ref in seen:
            errors.append(f"combo 內重複卡片: {ref}")
        seen.add(ref)
        deps = _str_tuple(item.get("depends_on"), ref, "depends_on", errors)
        for d in deps:
            if d not in {c.get("ref") for c in raw_cards if isinstance(c, Mapping)}:
                errors.append(f"{ref}: depends_on 指向 combo 外卡片 {d}")
        entries.append(ComboEntry(ref=ref, depends_on=deps))

    spine: list[GateCheck] = []
    for g in rec.get("gate_spine") or []:
        if not isinstance(g, Mapping) or not isinstance(g.get("after"), str):
            errors.append("gate_spine 項目缺 after")
            continue
        if g["after"] not in seen:
            errors.append(f"gate_spine.after 指向不存在卡片: {g['after']}")
        exists = _str_tuple(g.get("exists"), g["after"], "gate_spine.exists", errors)
        spine.append(GateCheck(after=g["after"], exists=exists))

    if errors:
        raise DeckSchemaError(f"combo 驗證失敗: {source}: " + "; ".join(errors))

    combo = Combo(id=combo_id, task_type=task_type, cards=tuple(entries), gate_spine=tuple(spine))
    _detect_combo_cycles(combo.cards)
    return combo
