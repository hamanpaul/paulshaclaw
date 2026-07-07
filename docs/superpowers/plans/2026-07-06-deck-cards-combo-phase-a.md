# deck-cards-combo-phase-a 實作計劃

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `paulshaclaw/deck/` 宣告層——Card/Combo schema、combo 編譯器、produces 驗收器——把 `feature-delivery-pipeline`／`mcu-coding-skill` 卡片化，`psc deck compile` 一鍵產出 manager 可代管的 hold specs。manager runtime 零改動。

**Architecture:** 薄宣告層 + 編譯器。cards.yaml/combos/*.yaml 為資料 artifact，fail-closed 載入；compile 把 interactive 卡編為前置 checklist、headless 卡（依 slice_group 合併）編為 slice specs（frontmatter 僅 dispatch/slice_id/plan/depends_on 四欄位）。接點是檔案，coordinator 不 import deck。

**Tech Stack:** Python ≥3.10、PyYAML、dataclasses、fnmatch/pathlib、argparse、pytest。

**真相源：** `docs/superpowers/specs/2026-07-06-deck-cards-combo-design.md` 與 `openspec/changes/deck-cards-combo-phase-a/`（proposal/design/specs/tasks）。

## Global Constraints

- **零 import 鐵律**：`paulshaclaw/deck/**` 禁止 import `paulshaclaw.lifecycle`、`paulshaclaw.memory`（import-lint 測試強制；hippo §4.5 清零相容）。
- **manager runtime 零改動**：不得修改 `coordinator/**`（W7 測試唯讀 import 除外）。
- **emit 安全**：預設 dry-run；`--emit` 一律 `dispatch: hold`；flat 檔名 `<slice_id>.md`；同名拒絕、`--force` 才原子覆蓋。
- **frontmatter 契約**：僅 `dispatch`/`slice_id`/`plan`/`depends_on` 四欄位（`parse_spec_frontmatter` 真相源）。
- **佔位符白名單**：僅 `<task-slug>`、`<change>`。task-slug 限 `[a-z0-9-]`、≤60、branch-safe。
- **TDD**：每個 code 任務 RED 先行，看到預期失敗才寫實作。
- **commit 規範**：conventional commits、zh-tw、只 commit 不 push；lane 各自 worktree/branch（`superpowers:using-git-worktrees`），W0 完成合入後 W1–W5 才 fan-out。
- **W3 路徑**：specs 目錄解析鏡射 `PSC_MANAGER_SPECS_DIR` → `~/.agents/specs`（不散落 `Path.home()` 於多處——集中單一 helper；#213 facade 落地後切換）。

**Lane 佈局**：Task 1–2＝W0（barrier，先行合入 main 或共用 base branch）→ Task 3–4（W1）、Task 5（W2）、Task 6–11（W3）、Task 12（W4）、Task 13（W5）五條 lane 平行 → Task 14（W7 整合）→ Task 15（收尾）。

---

### Task 1: W0 — deck schema 與 fail-closed 載入

**Files:**
- Create: `paulshaclaw/deck/__init__.py`（空檔）
- Create: `paulshaclaw/deck/schema.py`
- Test: `tests/test_deck_schema.py`

**Interfaces:**
- Produces: `Card`（欄位見下）、`ComboEntry(ref, depends_on)`、`GateCheck(after, exists)`、`Combo(id, task_type, cards, gate_spine)`、`DeckSchemaError`、`load_cards(path) -> dict[str, Card]`、`load_combo(path, cards) -> Combo`、常數 `DEFAULT_CARDS_PATH`、`DEFAULT_COMBOS_DIR`、`ALLOWED_PLACEHOLDERS`
- Consumes: 無（自足；僅 PyYAML）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_deck_schema.py
from __future__ import annotations

import pytest

from paulshaclaw.deck.schema import (
    Card,
    Combo,
    DeckSchemaError,
    load_cards,
    load_combo,
)

VALID_CARDS = """\
version: 0
cards:
  - id: writing-plans
    kind: skill
    type: interactive
    class: core
    skill_ref: "superpowers:writing-plans"
    requires: ["openspec/changes/<change>/proposal.md"]
    produces: ["docs/superpowers/plans/*<task-slug>*.md"]
    persona_binding: planner
  - id: build-a
    kind: skill
    type: headless
    class: core
    skill_ref: "superpowers:subagent-driven-development"
    slice_group: build
    requires: []
    produces: []
"""

VALID_COMBO = """\
combo:
  id: demo
  task_type: feature
  cards:
    - ref: writing-plans
    - ref: build-a
      depends_on: [writing-plans]
  gate_spine:
    - after: writing-plans
      exists: ["docs/superpowers/plans/*<task-slug>*.md"]
"""


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_load_cards_valid(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    assert set(cards) == {"writing-plans", "build-a"}
    assert cards["writing-plans"].type == "interactive"
    assert cards["build-a"].slice_group == "build"


def test_load_cards_bad_enum_rejects_whole_file(tmp_path):
    bad = VALID_CARDS.replace("type: headless", "type: batch")
    with pytest.raises(DeckSchemaError, match="build-a.*type"):
        load_cards(_write(tmp_path, "cards.yaml", bad))


def test_load_cards_unknown_placeholder_rejected(tmp_path):
    bad = VALID_CARDS.replace("<task-slug>", "<feature-name>")
    with pytest.raises(DeckSchemaError, match="feature-name"):
        load_cards(_write(tmp_path, "cards.yaml", bad))


def test_load_cards_duplicate_id_rejected(tmp_path):
    dup = VALID_CARDS + VALID_CARDS.split("cards:\n")[1]
    with pytest.raises(DeckSchemaError, match="重複"):
        load_cards(_write(tmp_path, "cards.yaml", dup))


def test_load_combo_valid(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    combo = load_combo(_write(tmp_path, "demo.yaml", VALID_COMBO), cards)
    assert combo.id == "demo"
    assert [c.ref for c in combo.cards] == ["writing-plans", "build-a"]


def test_load_combo_unknown_ref_rejected(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    bad = VALID_COMBO.replace("ref: build-a", "ref: no-such-card")
    with pytest.raises(DeckSchemaError, match="no-such-card"):
        load_combo(_write(tmp_path, "demo.yaml", bad), cards)


def test_load_combo_cycle_rejected(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    bad = VALID_COMBO.replace(
        "    - ref: writing-plans\n",
        "    - ref: writing-plans\n      depends_on: [build-a]\n",
    )
    with pytest.raises(DeckSchemaError, match="循環"):
        load_combo(_write(tmp_path, "demo.yaml", bad), cards)
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_schema.py -v 2>&1 | tail -5`（無 uv 則 `python3 -m pytest`）
Expected: FAIL — `ModuleNotFoundError: No module named 'paulshaclaw.deck'`

- [ ] **Step 3: 實作 schema.py**

```python
# paulshaclaw/deck/schema.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import yaml

SCHEMA_VERSION = 0
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
```

`paulshaclaw/deck/__init__.py` 內容為空檔（僅使其成為 package）。

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_schema.py -v 2>&1 | tail -3`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/ tests/test_deck_schema.py
git commit -m "feat(deck): W0 Card/Combo schema 與 fail-closed 載入（#186）"
```

---

### Task 2: W0 — frontmatter 契約對齊測試與 import-lint

**Files:**
- Test: `tests/test_deck_contract_alignment.py`

**Interfaces:**
- Consumes: Task 1 的 schema；`coordinator.autonomy.parse_spec_frontmatter`（唯讀）
- Produces: `EMITTED_FRONTMATTER_FIELDS = ("dispatch", "slice_id", "plan", "depends_on")` 常數（定義於 `deck/schema.py`，供 Task 7 compile 使用）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_deck_contract_alignment.py
from __future__ import annotations

import re
from pathlib import Path

DECK_DIR = Path("paulshaclaw/deck")
FORBIDDEN = re.compile(r"paulshaclaw\.(lifecycle|memory)")


def test_frontmatter_fields_match_runtime_contract():
    from paulshaclaw.deck.schema import EMITTED_FRONTMATTER_FIELDS

    # 真相源：parse_spec_frontmatter 回傳的 meta keys（扣除自身加註的 path）
    from paulshaclaw.coordinator.autonomy import parse_spec_frontmatter
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write("---\ndispatch: hold\nslice_id: x\nplan: p\ndepends_on: []\n---\n")
        path = f.name
    meta = parse_spec_frontmatter(path)
    runtime_fields = set(meta) - {"path"}
    assert set(EMITTED_FRONTMATTER_FIELDS) == runtime_fields


def test_deck_package_zero_import_of_lifecycle_and_memory():
    offenders = []
    for py in DECK_DIR.rglob("*.py"):
        if FORBIDDEN.search(py.read_text(encoding="utf-8")):
            offenders.append(str(py))
    assert offenders == [], f"deck 包違反零 import 鐵律: {offenders}"


def test_deck_tests_no_literal_forbidden_imports():
    offenders = []
    for py in Path("tests").glob("test_deck_*.py"):
        text = py.read_text(encoding="utf-8")
        if FORBIDDEN.search(text):
            offenders.append(str(py))
    assert offenders == [], f"deck 測試含禁用字面 import: {offenders}"
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_contract_alignment.py -v 2>&1 | tail -4`
Expected: FAIL — `ImportError: cannot import name 'EMITTED_FRONTMATTER_FIELDS'`

- [ ] **Step 3: 在 schema.py 加常數**

```python
# 加在 paulshaclaw/deck/schema.py 常數區（SCHEMA_VERSION 之後）
# runtime 契約真相源：coordinator/autonomy.py::parse_spec_frontmatter（勿發明多餘欄位）
EMITTED_FRONTMATTER_FIELDS = ("dispatch", "slice_id", "plan", "depends_on")
```

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_contract_alignment.py -v 2>&1 | tail -3`
Expected: 3 PASS

- [ ] **Step 5: Commit（W0 完成點——此後 W1–W5 可 fan-out）**

```bash
git add paulshaclaw/deck/schema.py tests/test_deck_contract_alignment.py
git commit -m "feat(deck): W0 frontmatter 契約對齊 + 零 import lint（#186）"
```

---

### Task 3: W1 — cards.yaml（feature-delivery-pipeline 11 phase 轉錄）

**Files:**
- Create: `paulshaclaw/deck/data/cards.yaml`
- Test: `tests/test_deck_data.py`

**Interfaces:**
- Consumes: Task 1 `load_cards`、`DEFAULT_CARDS_PATH`
- Produces: 11 張 phase 卡 + card id 集合（W1/W2 combo 與 W5 personas 引用這些 id）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_deck_data.py
from __future__ import annotations

from paulshaclaw.deck.schema import DEFAULT_CARDS_PATH, load_cards

# feature-delivery-pipeline SKILL.md 的 11 個 phase → card id（1:1）
PHASE_CARDS = [
    "brainstorming",        # 1 scope/brainstorm
    "openspec-propose",     # 2 propose
    "writing-plans",        # 3 plan
    "worktree-isolation",   # 4 worktree（slice_group: build）
    "tdd-red",              # 5 TDD（slice_group: build）
    "subagent-build",       # 6 subagent execution（slice_group: build）
    "code-review",          # 7 review
    "verification",         # 8 verify
    "openspec-archive",     # 9 archive（slice_group: ship）
    "policy-commit",        # 10 policy gate + commit（slice_group: ship）
    "adversarial-review",   # 11 codex adversarial
]


def test_cards_yaml_loads_and_covers_11_phases():
    cards = load_cards(DEFAULT_CARDS_PATH)
    for cid in PHASE_CARDS:
        assert cid in cards, f"缺 phase 卡: {cid}"


def test_interactive_headless_typing():
    cards = load_cards(DEFAULT_CARDS_PATH)
    interactive = {c.id for c in cards.values() if c.type == "interactive"}
    assert {"brainstorming", "openspec-propose", "writing-plans"} <= interactive
    assert cards["subagent-build"].slice_group == "build"
    assert cards["policy-commit"].slice_group == "ship"
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_data.py -v 2>&1 | tail -3`
Expected: FAIL — cards.yaml 不存在（DeckSchemaError）

- [ ] **Step 3: 寫 cards.yaml**

```yaml
# paulshaclaw/deck/data/cards.yaml
# 轉錄真相源：custom-skills/feature-delivery-pipeline SKILL.md（11 phases）
# produces 僅寫可機械驗證 glob；佔位符白名單：<task-slug>、<change>
version: 0
cards:
  - id: brainstorming
    kind: skill
    type: interactive
    class: core
    skill_ref: "superpowers:brainstorming"
    requires: []
    produces: ["docs/superpowers/specs/*<task-slug>*-design.md"]
    persona_binding: planner

  - id: openspec-propose
    kind: skill
    type: interactive
    class: core
    skill_ref: "openspec-propose"
    requires: ["docs/superpowers/specs/*<task-slug>*-design.md"]
    produces:
      - "openspec/changes/<change>/proposal.md"
      - "openspec/changes/<change>/tasks.md"
    persona_binding: planner

  - id: writing-plans
    kind: skill
    type: interactive
    class: core
    skill_ref: "superpowers:writing-plans"
    requires: ["openspec/changes/<change>/proposal.md"]
    produces: ["docs/superpowers/plans/*<task-slug>*.md"]
    persona_binding: planner

  - id: worktree-isolation
    kind: skill
    type: headless
    class: core
    skill_ref: "superpowers:using-git-worktrees"
    slice_group: build
    requires: ["docs/superpowers/plans/*<task-slug>*.md"]
    produces: []          # worktree 由 coordinator 派工時自建（feature/<slice_id>）
    persona_binding: builder

  - id: tdd-red
    kind: skill
    type: headless
    class: core
    skill_ref: "superpowers:test-driven-development"
    slice_group: build
    requires: []
    produces: []          # RED 證據在 build session log／commits，Phase A 不機驗
    persona_binding: builder

  - id: subagent-build
    kind: skill
    type: headless
    class: core
    skill_ref: "superpowers:subagent-driven-development"
    slice_group: build
    requires: []
    produces: []          # 完成偵測 = manager exit sentinel + branch commits
    persona_binding: builder

  - id: code-review
    kind: skill
    type: headless
    class: core
    skill_ref: "superpowers:requesting-code-review"
    requires: []
    produces: ["reports/review/*<task-slug>*.md"]
    persona_binding: reviewer

  - id: verification
    kind: skill
    type: headless
    class: core
    skill_ref: "superpowers:verification-before-completion"
    requires: []
    produces: ["reports/verify/*<task-slug>*.md"]
    persona_binding: reviewer

  - id: openspec-archive
    kind: skill
    type: headless
    class: core
    skill_ref: "openspec-archive-change"
    slice_group: ship
    requires: ["openspec/changes/<change>/tasks.md"]
    produces: ["openspec/changes/archive/*<change>*"]
    persona_binding: manager

  - id: policy-commit
    kind: skill
    type: headless
    class: core
    skill_ref: "conventional-commit"
    slice_group: ship
    requires: []
    produces: []          # 證據 = conventional commit 本身（不機驗檔案）
    persona_binding: manager

  - id: adversarial-review
    kind: skill
    type: headless
    class: core
    skill_ref: "codex:adversarial-review"
    requires: ["reports/review/*<task-slug>*.md"]
    produces: ["reports/review/*<task-slug>*-adversarial.md"]
    persona_binding: reviewer
```

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_data.py tests/test_deck_contract_alignment.py -v 2>&1 | tail -3`
Expected: 全 PASS（含零 import lint 仍綠）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/data/cards.yaml tests/test_deck_data.py
git commit -m "feat(deck): W1 轉錄 feature-delivery-pipeline 11 phase 卡片（#186）"
```

---

### Task 4: W1 — feature-oneshot combo

**Files:**
- Create: `paulshaclaw/deck/data/combos/feature-oneshot.yaml`
- Modify: `tests/test_deck_data.py`（追加測試）

**Interfaces:**
- Consumes: Task 1 `load_combo`、`DEFAULT_COMBOS_DIR`；Task 3 卡片
- Produces: `feature-oneshot` combo（task_type=feature；W7 整合測試的輸入）

- [ ] **Step 1: 追加失敗測試**

```python
# 追加到 tests/test_deck_data.py
from paulshaclaw.deck.schema import DEFAULT_COMBOS_DIR, load_combo


def test_feature_oneshot_combo_loads():
    cards = load_cards(DEFAULT_CARDS_PATH)
    combo = load_combo(DEFAULT_COMBOS_DIR / "feature-oneshot.yaml", cards)
    assert combo.task_type == "feature"
    assert [c.ref for c in combo.cards] == PHASE_CARDS  # 11 phase 全序
    assert combo.gate_spine[0].after == "writing-plans"
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_data.py::test_feature_oneshot_combo_loads -v 2>&1 | tail -3`
Expected: FAIL — combo 檔不存在

- [ ] **Step 3: 寫 combo YAML**

```yaml
# paulshaclaw/deck/data/combos/feature-oneshot.yaml
combo:
  id: feature-oneshot
  task_type: feature
  cards:
    - ref: brainstorming
    - ref: openspec-propose
    - ref: writing-plans
    - ref: worktree-isolation
    - ref: tdd-red
    - ref: subagent-build
    - ref: code-review
    - ref: verification
    - ref: openspec-archive
    - ref: policy-commit
    - ref: adversarial-review
  gate_spine:
    - after: writing-plans
      exists: ["docs/superpowers/plans/*<task-slug>*.md"]
    - after: code-review
      exists: ["reports/review/*<task-slug>*.md"]
```

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_data.py -v 2>&1 | tail -3`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/data/combos/feature-oneshot.yaml tests/test_deck_data.py
git commit -m "feat(deck): W1 feature-oneshot combo（11 phase 骨幹）（#186）"
```

---

### Task 5: W2 — mcu-feature combo（schema 泛化壓力測試）

**Files:**
- Create: `paulshaclaw/deck/data/combos/mcu-feature.yaml`
- Modify: `paulshaclaw/deck/data/cards.yaml`（追加 MCU 卡）
- Modify: `tests/test_deck_data.py`（追加測試）

**Interfaces:**
- Consumes: Task 3 既有卡（writing-plans、worktree-isolation、tdd-red、subagent-build、code-review、verification 共用）
- Produces: `mcu-hw-evidence` 卡、`mcu-feature` combo（task_type=mcu-feature）

轉錄真相源：`~/.agents/skills/mcu-coding-skill/SKILL.md`（TDD/subagent/review/verification 為 REQUIRED SUB-SKILL；硬體證據規則 → 獨立 interactive 卡）。若轉錄中發現 schema 表達不了的結構，回饋 Task 1 修 schema（勿硬塞）。

- [ ] **Step 1: 追加失敗測試**

```python
# 追加到 tests/test_deck_data.py
def test_mcu_feature_combo_loads():
    cards = load_cards(DEFAULT_CARDS_PATH)
    combo = load_combo(DEFAULT_COMBOS_DIR / "mcu-feature.yaml", cards)
    assert combo.task_type == "mcu-feature"
    assert cards["mcu-hw-evidence"].card_class == "niche"
    assert "subagent-build" in [c.ref for c in combo.cards]  # 共用既有卡
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_data.py::test_mcu_feature_combo_loads -v 2>&1 | tail -3`
Expected: FAIL

- [ ] **Step 3: 追加 MCU 卡與 combo**

```yaml
# 追加到 paulshaclaw/deck/data/cards.yaml 的 cards: 清單尾端
  - id: mcu-hw-evidence
    kind: skill
    type: interactive
    class: niche
    skill_ref: "mcu-coding-skill"
    requires: []
    produces: ["docs/superpowers/specs/*<task-slug>*-hw-evidence.md"]
    persona_binding: planner
```

```yaml
# paulshaclaw/deck/data/combos/mcu-feature.yaml
combo:
  id: mcu-feature
  task_type: mcu-feature
  cards:
    - ref: mcu-hw-evidence      # SysConfig/schematic 證據先行（SKILL.md 硬體證據規則）
    - ref: writing-plans
    - ref: worktree-isolation
    - ref: tdd-red              # 嵌入式 RED 選項見 mcu SKILL.md（source/static/link 不變量）
    - ref: subagent-build
    - ref: code-review
    - ref: verification
  gate_spine:
    - after: mcu-hw-evidence
      exists: ["docs/superpowers/specs/*<task-slug>*-hw-evidence.md"]
```

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_data.py -v 2>&1 | tail -3`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/data/ tests/test_deck_data.py
git commit -m "feat(deck): W2 mcu-feature combo + MCU 特有卡（schema 泛化驗證）（#186）"
```

---

### Task 6: W3 — slugify 與 specs 目錄 helper

**Files:**
- Create: `paulshaclaw/deck/compile.py`（先立 helper 段）
- Test: `tests/test_deck_compile.py`

**Interfaces:**
- Produces: `slugify_task(task) -> str`、`specs_dir() -> Path`、`DeckCompileError`
- Consumes: 環境變數 `PSC_MANAGER_SPECS_DIR`（鏡射 `manager_daemon.default_specs_dir` 契約）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_deck_compile.py
from __future__ import annotations

from pathlib import Path

import pytest

from paulshaclaw.deck.compile import DeckCompileError, slugify_task, specs_dir


def test_slugify_basic():
    assert slugify_task("Add LED Blink Mode!") == "add-led-blink-mode"


def test_slugify_length_cap_60():
    assert len(slugify_task("x" * 200)) <= 60


def test_slugify_empty_rejected():
    with pytest.raises(DeckCompileError):
        slugify_task("！！！")


def test_specs_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_MANAGER_SPECS_DIR", str(tmp_path))
    assert specs_dir() == tmp_path


def test_specs_dir_equals_manager_default(monkeypatch):
    # 相等性回歸：deck 鏡射 manager 契約（tests 層允許 import coordinator）
    from paulshaclaw.coordinator.manager_daemon import default_specs_dir

    monkeypatch.delenv("PSC_MANAGER_SPECS_DIR", raising=False)
    assert str(specs_dir()) == default_specs_dir()
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_compile.py -v 2>&1 | tail -3`
Expected: FAIL — `No module named 'paulshaclaw.deck.compile'`

- [ ] **Step 3: 實作 helper 段**

```python
# paulshaclaw/deck/compile.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .schema import Card, Combo, ComboEntry, EMITTED_FRONTMATTER_FIELDS


class DeckCompileError(ValueError):
    """compile 期錯誤（fail-closed：不產任何檔）。"""


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_task(task: str) -> str:
    """--task → branch-safe slug：[a-z0-9-]、≤60、頭尾無 '-'。空結果 → 報錯。"""
    slug = _SLUG_RE.sub("-", task.lower()).strip("-")[:60].strip("-")
    if not slug:
        raise DeckCompileError(f"task 無法正規化為 slug: {task!r}")
    return slug


def specs_dir() -> Path:
    """活佇列位置。鏡射 manager 契約（manager_daemon.default_specs_dir）：
    PSC_MANAGER_SPECS_DIR → ~/.agents/specs。#213 facade 落地後改走 facade specs_dir()。
    """
    override = os.environ.get("PSC_MANAGER_SPECS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".agents" / "specs"
```

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_compile.py -v 2>&1 | tail -3`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/compile.py tests/test_deck_compile.py
git commit -m "feat(deck): W3 slugify + specs 目錄 helper（鏡射 manager 契約）（#186）"
```

---

### Task 7: W3 — compile 核心（checklist／slice_group 合併／隱式串鏈）

**Files:**
- Modify: `paulshaclaw/deck/compile.py`
- Modify: `tests/test_deck_compile.py`（追加）

**Interfaces:**
- Produces: `SliceDoc(slice_id, filename, content)`、`CompileResult(task_slug, slices, checklist, verify_commands, external)`、`compile_combo(combo, cards, task, *, change=None, with_cards=(), only=(), allow_external=False, plan_ref=None) -> CompileResult`
- Consumes: Task 1 schema、Task 6 helpers

規則（設計 §5）：interactive 卡 → checklist；headless 卡依 `slice_group` 合併（連續同組 → 一 slice，`slice_id=<task-slug>-<group>`；無組 → `<task-slug>-<card-id>`）；slice 無顯式 depends → 隱式依賴前一 headless slice；`plan` = plan_ref 參數，預設取最後一張 interactive 卡的第一個 produces（代入佔位符），皆無 → 報錯。

- [ ] **Step 1: 追加失敗測試**

```python
# 追加到 tests/test_deck_compile.py
from paulshaclaw.deck.compile import compile_combo
from paulshaclaw.deck.schema import DEFAULT_CARDS_PATH, DEFAULT_COMBOS_DIR, load_cards, load_combo


def _feature_oneshot():
    cards = load_cards(DEFAULT_CARDS_PATH)
    combo = load_combo(DEFAULT_COMBOS_DIR / "feature-oneshot.yaml", cards)
    return cards, combo


def test_compile_slice_grouping_and_chain():
    cards, combo = _feature_oneshot()
    result = compile_combo(combo, cards, "示例 LED 功能", change="demo", allow_external=True)
    ids = [s.slice_id for s in result.slices]
    slug = result.task_slug
    # build 三卡合併、ship 兩卡合併 → 5 slices
    assert ids == [f"{slug}-build", f"{slug}-code-review", f"{slug}-verification",
                   f"{slug}-ship", f"{slug}-adversarial-review"]
    assert len(result.checklist) == 3  # 3 張 interactive 卡


def test_compile_frontmatter_hold_and_chain():
    cards, combo = _feature_oneshot()
    result = compile_combo(combo, cards, "示例 LED 功能", change="demo", allow_external=True)
    first = result.slices[0].content
    assert first.startswith("---\n")
    assert "dispatch: hold" in first
    second = result.slices[1].content
    assert f"- {result.task_slug}-build" in second  # 隱式串鏈


def test_compile_missing_change_placeholder_errors():
    cards, combo = _feature_oneshot()
    with pytest.raises(DeckCompileError, match="--change"):
        compile_combo(combo, cards, "示例 LED 功能", allow_external=True)


def test_compile_frontmatter_exact_keyset():
    # W0 對抗審查修正交棒：parse_spec_frontmatter 會忽略未知欄位，
    # 所以必須直接解析 compiler 原始輸出的 YAML frontmatter key set 精確比對
    import yaml
    from paulshaclaw.deck.schema import EMITTED_FRONTMATTER_FIELDS

    cards, combo = _feature_oneshot()
    result = compile_combo(combo, cards, "示例 LED 功能", change="demo", allow_external=True)
    for s in result.slices:
        block = s.content.split("---\n")[1]
        assert set(yaml.safe_load(block)) == set(EMITTED_FRONTMATTER_FIELDS)
```

（第一個測試中以精確清單斷言為準，移除示意行。）

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_compile.py -v 2>&1 | tail -4`
Expected: FAIL — `cannot import name 'compile_combo'`

- [ ] **Step 3: 實作 compile 核心**

```python
# 追加到 paulshaclaw/deck/compile.py
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


def _group_slices(entries: Sequence[ComboEntry], cards: Mapping[str, Card], slug: str):
    """headless 卡 → (slice_id, member cards) 清單；連續同 slice_group 合併。"""
    groups: list[tuple[str, list[Card]]] = []
    for e in entries:
        card = cards[e.ref]
        if card.type != "headless":
            continue
        gid = card.slice_group
        if gid and groups and groups[-1][0] == f"{slug}-{gid}":
            groups[-1][1].append(card)
        else:
            sid = f"{slug}-{gid}" if gid else f"{slug}-{card.id}"
            groups.append((sid, [card]))
    return groups


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
    entries = _resolve_hand(combo, cards, with_cards, only)          # Task 9
    _check_requires_coverage(entries, cards, allow_external)          # Task 8（先以 stub 過渡）

    interactive = [cards[e.ref] for e in entries if cards[e.ref].type == "interactive"]
    checklist = tuple(
        f"[{c.id}] {c.skill_ref} → 產出: " + ", ".join(_subst(g, slug, change) for g in c.produces)
        for c in interactive
    )
    if plan_ref is None:
        for c in reversed(interactive):
            if c.produces:
                plan_ref = _subst(c.produces[0], slug, change)
                break
    if not plan_ref:
        raise DeckCompileError("無法決定 plan 參照：無 interactive produces，請給 --plan")

    slices: list[SliceDoc] = []
    verify_cmds: list[str] = []
    prev_sid: str | None = None
    explicit: dict[str, tuple[str, ...]] = {e.ref: e.depends_on for e in entries}
    for sid, members in _group_slices(entries, cards, slug):
        deps: list[str] = []
        for m in members:
            for d in explicit.get(m.id, ()):
                dcard = cards.get(d)
                if dcard is not None and dcard.type == "headless":
                    dgid = dcard.slice_group
                    deps.append(f"{slug}-{dgid}" if dgid else f"{slug}-{d}")
        deps = sorted(set(d for d in deps if d != sid))
        if not deps and prev_sid:
            deps = [prev_sid]  # 隱式串鏈（保序）
        produces = [
            _subst(g, slug, change) for m in members for g in m.produces
        ]
        requires = [
            _subst(g, slug, change) for m in members for g in m.requires
        ]
        dep_lines = "".join(f"\n  - {d}" for d in deps)
        body_req = "".join(f"\n- {r}" for r in requires) or "\n-（無）"
        body_prod = "".join(f"\n- {p}" for p in produces) or "\n-（無，完成偵測=exit sentinel）"
        content = (
            "---\n"
            "dispatch: hold\n"
            f"slice_id: {sid}\n"
            f"plan: {plan_ref}\n"
            f"depends_on:{dep_lines if deps else ' []'}\n"
            "---\n"
            f"# {sid}\n\n"
            f"任務：{task}\n"
            f"combo：{combo.id}（cards: {', '.join(m.id for m in members)}）\n\n"
            f"requires（翻 auto 前人工確認）：{body_req}\n\n"
            f"produces（deck verify 驗收）：{body_prod}\n"
        )
        slices.append(SliceDoc(slice_id=sid, filename=f"{sid}.md", content=content))
        for m in members:
            if m.produces:
                verify_cmds.append(f"psc deck verify {m.id} --task-slug {slug}")
        prev_sid = sid

    return CompileResult(
        task_slug=slug,
        slices=tuple(slices),
        checklist=checklist,
        verify_commands=tuple(dict.fromkeys(verify_cmds)),
        external=(),
    )
```

過渡 stub（Task 8/9 會替換為真實作，先讓本任務綠）：

```python
def _resolve_hand(combo, cards, with_cards, only):
    if with_cards or only:
        raise DeckCompileError("additive/--only 於 Task 9 實作")
    return list(combo.cards)


def _check_requires_coverage(entries, cards, allow_external):
    return None  # Task 8 實作 pattern-level 檢查
```

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_compile.py -v 2>&1 | tail -3`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/compile.py tests/test_deck_compile.py
git commit -m "feat(deck): W3 compile 核心——checklist/slice_group 合併/隱式串鏈/hold frontmatter（#186）"
```

---

### Task 8: W3 — requires pattern-level 覆蓋檢查

**Files:**
- Modify: `paulshaclaw/deck/compile.py`（替換 `_check_requires_coverage` stub）
- Modify: `tests/test_deck_compile.py`（追加）

**Interfaces:**
- Produces: 真實 `_check_requires_coverage(entries, cards, allow_external)`；`CompileResult.external` 填入放行清單
- Consumes: Task 7 的 compile_combo 呼叫點（簽名不變）

- [ ] **Step 1: 追加失敗測試**

```python
# 追加到 tests/test_deck_compile.py
# 不依賴 --only（Task 9 才實作）：以只含 adversarial-review 的最小 combo 觸發未覆蓋——
# 其 requires reports/review/*<task-slug>*.md 無任何上游 produces。
SOLO_ADV_COMBO = """\
combo:
  id: solo-adv
  task_type: feature
  cards:
    - ref: adversarial-review
"""


def _solo_adv(tmp_path):
    from paulshaclaw.deck.schema import load_combo
    cards = load_cards(DEFAULT_CARDS_PATH)
    p = tmp_path / "solo-adv.yaml"
    p.write_text(SOLO_ADV_COMBO, encoding="utf-8")
    return cards, load_combo(p, cards)


def test_requires_uncovered_blocks_without_allow_external(tmp_path):
    cards, combo = _solo_adv(tmp_path)
    with pytest.raises(DeckCompileError, match="allow-external"):
        compile_combo(combo, cards, "示例", change="demo", plan_ref="docs/plan.md")


def test_requires_external_allowed_and_reported(tmp_path):
    cards, combo = _solo_adv(tmp_path)
    result = compile_combo(combo, cards, "示例", change="demo",
                           allow_external=True, plan_ref="docs/plan.md")
    assert result.external  # requires 無上游 → 列為 external
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_compile.py -k external -v 2>&1 | tail -3`
Expected: FAIL（stub 直接 return，未 raise / external 恆空）

- [ ] **Step 3: 實作覆蓋檢查（並讓 compile_combo 把 external 傳入 CompileResult）**

```python
def _prefix(glob: str) -> str:
    return glob.split("*", 1)[0]


def _covered(require: str, produce: str) -> bool:
    """保守 pattern 覆蓋：字面前綴一致至首個 wildcard（互為前綴即視為覆蓋）。"""
    r, p = _prefix(require), _prefix(produce)
    return r.startswith(p) or p.startswith(r)


def _check_requires_coverage(entries, cards, allow_external) -> tuple[str, ...]:
    upstream: list[str] = []
    external: list[str] = []
    for e in entries:
        card = cards[e.ref]
        for req in card.requires:
            if not any(_covered(req, prod) for prod in upstream):
                external.append(f"{card.id}: {req}")
        upstream.extend(card.produces)
    if external and not allow_external:
        raise DeckCompileError(
            "requires 未被上游 produces 覆蓋（external input），"
            "確認後以 --allow-external 放行：\n  " + "\n  ".join(external)
        )
    return tuple(external)
```

`compile_combo` 中改為：`external = _check_requires_coverage(entries, cards, allow_external)`，並在 `CompileResult(..., external=external)` 傳入。注意：覆蓋檢查在佔位符**代入前**以原始 pattern 比對（同一佔位符字面相等即前綴一致）。

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_compile.py -v 2>&1 | tail -3`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/compile.py tests/test_deck_compile.py
git commit -m "feat(deck): W3 requires pattern 覆蓋檢查 + --allow-external（#186）"
```

---

### Task 9: W3 — additive（--with 定位）與 --only

**Files:**
- Modify: `paulshaclaw/deck/compile.py`（替換 `_resolve_hand` stub）
- Modify: `tests/test_deck_compile.py`（追加）

**Interfaces:**
- Produces: `parse_with_spec("card[:after=id|:before=id]") -> tuple[str, str | None, str | None]`；真實 `_resolve_hand(combo, cards, with_cards, only) -> list[ComboEntry]`
- Consumes: Task 7/8 呼叫點（簽名不變）

- [ ] **Step 1: 追加失敗測試**

```python
# 追加到 tests/test_deck_compile.py
from paulshaclaw.deck.compile import parse_with_spec


def test_parse_with_spec_forms():
    assert parse_with_spec("mcu-hw-evidence") == ("mcu-hw-evidence", None, None)
    assert parse_with_spec("x:after=code-review") == ("x", "after", "code-review")
    assert parse_with_spec("x:before=tdd-red") == ("x", "before", "tdd-red")


def test_with_explicit_position_inserts_without_replacing():
    cards, combo = _feature_oneshot()
    result = compile_combo(combo, cards, "示例", change="demo",
                           with_cards=("mcu-hw-evidence:after=brainstorming",),
                           allow_external=True)
    # 骨幹卡全數保留 + checklist 多一張 interactive 卡
    assert len(result.checklist) == 4


def test_with_unresolvable_position_fails_closed():
    cards, combo = _feature_oneshot()
    # policy-commit requires=[] → 無法以覆蓋推斷插入點 → 必須明示位置
    with pytest.raises(DeckCompileError, match="after=|before="):
        compile_combo(combo, cards, "示例", change="demo",
                      with_cards=("policy-commit",), allow_external=True)


def test_only_exclusive_mode():
    cards, combo = _feature_oneshot()
    result = compile_combo(combo, cards, "示例", change="demo",
                           only=("code-review", "verification"), allow_external=True)
    assert [s.slice_id for s in result.slices] == [
        f"{result.task_slug}-code-review", f"{result.task_slug}-verification"]
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_compile.py -k "with_ or only" -v 2>&1 | tail -4`
Expected: FAIL（stub raise「Task 9 實作」）

- [ ] **Step 3: 實作**

```python
def parse_with_spec(spec: str) -> tuple[str, str | None, str | None]:
    if ":" not in spec:
        return spec, None, None
    card_id, _, rest = spec.partition(":")
    kind, _, anchor = rest.partition("=")
    if kind not in ("after", "before") or not anchor:
        raise DeckCompileError(f"--with 定位格式錯誤: {spec!r}（card[:after=<id>|:before=<id>]）")
    return card_id, kind, anchor


def _resolve_hand(combo: Combo, cards: Mapping[str, Card],
                  with_cards: Sequence[str], only: Sequence[str]) -> list[ComboEntry]:
    if only:
        unknown = [o for o in only if o not in {e.ref for e in combo.cards}]
        if unknown:
            raise DeckCompileError(f"--only 指定了 combo 外卡片: {unknown}")
        return [e for e in combo.cards if e.ref in set(only)]

    hand = list(combo.cards)
    for spec in with_cards:
        card_id, kind, anchor = parse_with_spec(spec)
        if card_id not in cards:
            raise DeckCompileError(f"--with 未知卡片: {card_id}")
        if card_id in {e.ref for e in hand}:
            raise DeckCompileError(f"--with 卡片已在骨幹中: {card_id}")
        if kind is None:
            # 覆蓋推斷：插在「produces 覆蓋其全部 requires 的最早上游」之後
            reqs = cards[card_id].requires
            pos = None
            if reqs:
                seen: list[str] = []
                for i, e in enumerate(hand):
                    seen.extend(cards[e.ref].produces)
                    if all(any(_covered(r, p) for p in seen) for r in reqs):
                        pos = i + 1
                        break
            if pos is None:
                raise DeckCompileError(
                    f"--with {card_id} 無法推斷插入點，請明示 :after=<id> 或 :before=<id>")
        else:
            refs = [e.ref for e in hand]
            if anchor not in refs:
                raise DeckCompileError(f"--with 定位錨點不在手牌中: {anchor}")
            pos = refs.index(anchor) + (1 if kind == "after" else 0)
        hand.insert(pos, ComboEntry(ref=card_id))
    return hand
```

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_compile.py -v 2>&1 | tail -3`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/compile.py tests/test_deck_compile.py
git commit -m "feat(deck): W3 additive --with 定位（推斷 fail-closed）+ --only 排他（#186）"
```

---

### Task 10: W3 — emit（同名拒絕／--force 原子覆蓋）

**Files:**
- Modify: `paulshaclaw/deck/compile.py`
- Modify: `tests/test_deck_compile.py`（追加）

**Interfaces:**
- Produces: `emit(result, target_dir, *, force=False) -> list[Path]`
- Consumes: Task 7 `CompileResult`

- [ ] **Step 1: 追加失敗測試**

```python
# 追加到 tests/test_deck_compile.py
from paulshaclaw.deck.compile import emit


def test_emit_writes_flat_and_refuses_overwrite(tmp_path):
    cards, combo = _feature_oneshot()
    result = compile_combo(combo, cards, "示例", change="demo", allow_external=True)
    written = emit(result, tmp_path)
    assert all(p.parent == tmp_path for p in written)  # flat，不建子目錄
    assert {p.name for p in written} == {s.filename for s in result.slices}
    with pytest.raises(DeckCompileError, match="已存在"):
        emit(result, tmp_path)  # 同名拒絕


def test_emit_force_overwrites_atomically(tmp_path):
    cards, combo = _feature_oneshot()
    result = compile_combo(combo, cards, "示例", change="demo", allow_external=True)
    emit(result, tmp_path)
    written = emit(result, tmp_path, force=True)
    assert written and all(p.read_text(encoding="utf-8").startswith("---") for p in written)
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_compile.py -k emit -v 2>&1 | tail -3`
Expected: FAIL — `cannot import name 'emit'`

- [ ] **Step 3: 實作 emit**

```python
def emit(result: CompileResult, target_dir: str | Path, *, force: bool = False) -> list[Path]:
    """把 slices 寫入 target_dir（flat）。同名檔存在 → 預設整批拒絕（防覆蓋 in-flight
    slice）；force 時以 temp+os.replace 原子覆蓋。任何寫入前先做完整衝突檢查。"""
    d = Path(target_dir)
    d.mkdir(parents=True, exist_ok=True)
    conflicts = [s.filename for s in result.slices if (d / s.filename).exists()]
    if conflicts and not force:
        raise DeckCompileError(
            "emit 目標已存在同名 spec（--force 才覆蓋）：" + ", ".join(conflicts))
    written: list[Path] = []
    for s in result.slices:
        final = d / s.filename
        tmp = d / (s.filename + ".tmp")
        tmp.write_text(s.content, encoding="utf-8")
        os.replace(tmp, final)
        written.append(final)
    return written
```

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_compile.py -v 2>&1 | tail -3`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/compile.py tests/test_deck_compile.py
git commit -m "feat(deck): W3 emit——flat 檔名/同名拒絕/--force 原子覆蓋（#186）"
```

---

### Task 11: W3 — deck CLI 與 psc route

**Files:**
- Create: `paulshaclaw/deck/cli.py`
- Modify: `paulshaclaw/cli.py`
- Modify: `tests/test_psc_cli.py`（追加）
- Test: `tests/test_deck_cli.py`

**Interfaces:**
- Produces: `paulshaclaw.deck.cli.main(argv) -> int`（子命令 `list`/`compile`/`verify`）；`psc deck ...` 路由
- Consumes: Task 6–10 compile API、Task 12 verify API（verify 子命令於 Task 12 接上，本任務先掛 `list`/`compile`）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_deck_cli.py
from __future__ import annotations

from paulshaclaw.deck import cli as deck_cli


def test_list_shows_combos(capsys):
    assert deck_cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "feature-oneshot" in out and "mcu-feature" in out


def test_compile_dry_run_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PSC_MANAGER_SPECS_DIR", str(tmp_path))
    rc = deck_cli.main(["compile", "feature-oneshot", "--task", "示例功能",
                        "--change", "demo", "--allow-external"])
    assert rc == 0
    assert list(tmp_path.iterdir()) == []  # 預設 dry-run 不落地
    assert "dispatch: hold" in capsys.readouterr().out


def test_compile_emit_writes_hold_specs(tmp_path, monkeypatch):
    monkeypatch.setenv("PSC_MANAGER_SPECS_DIR", str(tmp_path))
    rc = deck_cli.main(["compile", "feature-oneshot", "--task", "示例功能",
                        "--change", "demo", "--allow-external", "--emit"])
    assert rc == 0
    files = sorted(tmp_path.glob("*.md"))
    assert files and all("dispatch: hold" in f.read_text(encoding="utf-8") for f in files)
```

```python
# 追加到 tests/test_psc_cli.py
def test_route_deck(monkeypatch) -> None:
    monkeypatch.setattr("paulshaclaw.deck.cli.main", lambda argv: 0)

    assert cli.main(["deck", "list"]) == 0
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_cli.py tests/test_psc_cli.py -v 2>&1 | tail -4`
Expected: FAIL — deck.cli 不存在；psc route 回 2

- [ ] **Step 3: 實作 deck/cli.py 與 psc route**

```python
# paulshaclaw/deck/cli.py
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .compile import DeckCompileError, compile_combo, emit, specs_dir
from .schema import (
    DEFAULT_CARDS_PATH,
    DEFAULT_COMBOS_DIR,
    DeckSchemaError,
    load_cards,
    load_combo,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="psc deck")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出卡片與 combos")

    c = sub.add_parser("compile", help="combo+task → slice specs（預設 dry-run）")
    c.add_argument("combo")
    c.add_argument("--task", required=True)
    c.add_argument("--change")
    c.add_argument("--with", dest="with_cards", action="append", default=[],
                   metavar="CARD[:after=ID|:before=ID]")
    c.add_argument("--only", nargs="+", default=[])
    c.add_argument("--allow-external", action="store_true")
    c.add_argument("--plan", dest="plan_ref")
    g = c.add_mutually_exclusive_group()
    g.add_argument("--out")
    g.add_argument("--emit", action="store_true")
    c.add_argument("--force", action="store_true")

    v = sub.add_parser("verify", help="卡片 produces 存在性驗收")
    v.add_argument("card_id")
    v.add_argument("--task-slug", required=True)
    v.add_argument("--change")
    v.add_argument("--root", default=".")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        cards = load_cards(DEFAULT_CARDS_PATH)
        if args.command == "list":
            for combo_file in sorted(DEFAULT_COMBOS_DIR.glob("*.yaml")):
                combo = load_combo(combo_file, cards)
                print(f"{combo.id}\t(task_type={combo.task_type}, cards={len(combo.cards)})")
            for card in cards.values():
                print(f"  card: {card.id}\t[{card.type}/{card.card_class}]")
            return 0
        if args.command == "compile":
            combo = load_combo(DEFAULT_COMBOS_DIR / f"{args.combo}.yaml", cards)
            result = compile_combo(
                combo, cards, args.task, change=args.change,
                with_cards=tuple(args.with_cards), only=tuple(args.only),
                allow_external=args.allow_external, plan_ref=args.plan_ref,
            )
            print(f"task-slug: {result.task_slug}")
            print("前置 checklist（interactive）：")
            for line in result.checklist:
                print(f"  - {line}")
            if result.external:
                print("external inputs（已放行）：")
                for e in result.external:
                    print(f"  - {e}")
            if args.emit or args.out:
                target = specs_dir() if args.emit else args.out
                written = emit(result, target, force=args.force)
                print(f"已寫入 {len(written)} 份 spec → {target}（dispatch: hold）")
                print("翻 auto 前先跑：")
                for cmd in result.verify_commands:
                    print(f"  - {cmd}")
            else:
                for s in result.slices:
                    print(f"--- {s.filename} ---")
                    print(s.content)
            return 0
        if args.command == "verify":
            from .verify import verify_card  # Task 12

            card = cards.get(args.card_id)
            if card is None:
                print(f"未知卡片: {args.card_id}", file=sys.stderr)
                return 2
            result = verify_card(card, args.task_slug, root=args.root, change=args.change)
            for m in result.missing:
                print(f"MISSING {m}")
            print("PASS" if result.ok else "FAIL")
            return 0 if result.ok else 1
        return 2
    except (DeckSchemaError, DeckCompileError) as exc:
        print(f"deck: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

`paulshaclaw/cli.py` 修改（usage 行與新分支）：

```python
_USAGE = "usage: psc {memory|coordinator|deck} <args...>\n"
```

```python
    if head == "deck":
        from paulshaclaw.deck.cli import main as deck_main

        return int(deck_main(rest) or 0)
```

（插在 `coordinator` 分支之後、fallback 之前，風格與既有分支一致。）

Task 12 前 `verify` 子命令會 ImportError——本任務測試不碰 verify，允許。

- [ ] **Step 4: 跑測試確認 PASS**

Run: `uv run pytest tests/test_deck_cli.py tests/test_psc_cli.py -v 2>&1 | tail -4`
Expected: 全 PASS（含既有 psc 測試回歸）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/cli.py paulshaclaw/cli.py tests/test_deck_cli.py tests/test_psc_cli.py
git commit -m "feat(deck): W3 deck CLI + psc route（list/compile；dry-run 預設）（#186）"
```

---

### Task 12: W4 — verify 驗收器

**Files:**
- Create: `paulshaclaw/deck/verify.py`
- Test: `tests/test_deck_verify.py`

**Interfaces:**
- Produces: `VerifyResult(card_id, ok, missing, matched)`、`verify_card(card, task_slug, *, root=".", change=None) -> VerifyResult`
- Consumes: Task 1 `Card`；Task 11 CLI `verify` 子命令（已預掛）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_deck_verify.py
from __future__ import annotations

from paulshaclaw.deck.schema import Card
from paulshaclaw.deck.verify import verify_card


def _card(produces):
    return Card(id="c", kind="skill", type="headless", card_class="core",
                skill_ref="x", produces=tuple(produces))


def test_verify_pass_when_all_globs_match(tmp_path):
    (tmp_path / "reports" / "review").mkdir(parents=True)
    (tmp_path / "reports" / "review" / "2026-demo-x.md").write_text("r", encoding="utf-8")
    result = verify_card(_card(["reports/review/*demo*.md"]), "demo", root=tmp_path)
    assert result.ok and result.missing == ()


def test_verify_fail_lists_missing(tmp_path):
    result = verify_card(_card(["reports/review/*demo*.md"]), "demo", root=tmp_path)
    assert not result.ok
    assert result.missing == ("reports/review/*demo*.md",)


def test_verify_empty_produces_trivially_pass(tmp_path):
    assert verify_card(_card([]), "demo", root=tmp_path).ok
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_deck_verify.py -v 2>&1 | tail -3`
Expected: FAIL — verify 模組不存在

- [ ] **Step 3: 實作 verify.py**

```python
# paulshaclaw/deck/verify.py
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


def verify_card(card: Card, task_slug: str, *, root: str | Path = ".",
                change: str | None = None) -> VerifyResult:
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
    return VerifyResult(card_id=card.id, ok=not missing,
                        missing=tuple(missing), matched=tuple(matched))
```

- [ ] **Step 4: 跑測試確認 PASS（含 CLI verify 子命令端到端）**

Run: `uv run pytest tests/test_deck_verify.py tests/test_deck_cli.py -v 2>&1 | tail -3`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deck/verify.py tests/test_deck_verify.py
git commit -m "feat(deck): W4 produces 存在性驗收器 + CLI verify（#186）"
```

---

### Task 13: W5 — personas skills 欄位（shadow）

**Files:**
- Modify: `paulshaclaw/persona/contract.py:15-22`（PersonaContract 加欄位）
- Modify: `paulshaclaw/persona/loader.py:53-63`（讀取保留 + shadow 警告）
- Modify: `paulshaclaw/persona/personas.yaml`（三 role 加 `skills:`）
- Test: `tests/test_persona_skills.py`

**Interfaces:**
- Produces: `PersonaContract.skills: tuple[str, ...] = ()`；loader 對未知 card id 發 `warnings.warn`
- Consumes: Task 3 `cards.yaml`（lazy import，deck 缺席時 fail-open）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_persona_skills.py
from __future__ import annotations

import warnings

import pytest

from paulshaclaw.persona.loader import load_catalog

MINI = """\
version: 1
enforcement: shadow
roles:
  manager:
    role: manager
    version: "0.1"
    summary: s
    allowed_phases: [plan]
    write_paths: ["docs/plan.md"]
    allowed_tools: [git]
    skills: [writing-plans]
  builder:
    role: builder
    version: "0.1"
    summary: s
    allowed_phases: [build]
    write_paths: ["src/**"]
    allowed_tools: [git]
  reviewer:
    role: reviewer
    version: "0.1"
    summary: s
    allowed_phases: [review]
    write_paths: ["reports/review/**"]
    allowed_tools: [git]
    skills: [no-such-card]
"""


@pytest.fixture()
def catalog_path(tmp_path):
    p = tmp_path / "personas.yaml"
    p.write_text(MINI, encoding="utf-8")
    return p


def test_skills_field_survives_to_contract(catalog_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        catalog = load_catalog(catalog_path)
    assert catalog["manager"].skills == ("writing-plans",)
    assert catalog["builder"].skills == ()  # 欄位可選


def test_unknown_card_id_warns_but_loads(catalog_path):
    with pytest.warns(UserWarning, match="no-such-card"):
        catalog = load_catalog(catalog_path)
    assert "reviewer" in catalog  # shadow：不失敗
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `uv run pytest tests/test_persona_skills.py -v 2>&1 | tail -3`
Expected: FAIL — `PersonaContract` 無 skills 屬性

- [ ] **Step 3: 實作**

`contract.py` PersonaContract 加最後一個欄位（frozen dataclass，含預設值故不影響既有建構）：

```python
@dataclass(frozen=True)
class PersonaContract:
    role: str
    version: str
    summary: str
    allowed_phases: tuple[str, ...]
    write_paths: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    skills: tuple[str, ...] = ()  # deck card id 引用（shadow，#186 W5）
```

`loader.py` 檔頭加 `import warnings`；`load_catalog` 迴圈內改為：

```python
    catalog: dict[str, PersonaContract] = {}
    for role, rec in records.items():
        raw_skills = rec.get("skills") or []
        if not isinstance(raw_skills, list) or any(not isinstance(s, str) for s in raw_skills):
            raise ValueError(f"persona catalog schema 不合法: {role}: skills 必須是字串清單")
        catalog[role] = PersonaContract(
            role=rec["role"],
            version=rec["version"],
            summary=rec["summary"],
            allowed_phases=tuple(rec["allowed_phases"]),
            write_paths=tuple(rec["write_paths"]),
            allowed_tools=tuple(rec["allowed_tools"]),
            skills=tuple(raw_skills),
        )
    _warn_unknown_skills(catalog)
    return catalog
```

檔尾新增（lazy import deck；deck 缺席／壞檔不影響 persona 載入——shadow 精神）：

```python
def _warn_unknown_skills(catalog: dict[str, PersonaContract]) -> None:
    try:
        from paulshaclaw.deck.schema import DEFAULT_CARDS_PATH, load_cards

        cards = load_cards(DEFAULT_CARDS_PATH)
    except Exception:
        return  # shadow：deck 不可用時不擋 persona 載入
    for role, contract in catalog.items():
        for sid in contract.skills:
            if sid not in cards:
                warnings.warn(f"persona {role} 引用未知 deck card: {sid}", stacklevel=2)
```

`personas.yaml` 三 role 各加 `skills:`（依 role 職掌對應卡片；實際 diff 對照現檔內容）：

```yaml
# manager 段追加
    skills: [openspec-archive, policy-commit]
# builder 段追加
    skills: [worktree-isolation, tdd-red, subagent-build]
# reviewer 段追加
    skills: [code-review, verification, adversarial-review]
```

- [ ] **Step 4: 跑測試確認 PASS（含 persona 既有測試回歸）**

Run: `uv run pytest tests/test_persona_skills.py tests/ -k persona -v 2>&1 | tail -4`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/persona/ tests/test_persona_skills.py
git commit -m "feat(persona): W5 skills 欄位接線 deck 卡片（shadow 驗證）（#186）"
```

---

### Task 14: W7 — parse-level 整合驗證

**Files:**
- Test: `tests/test_deck_integration.py`

**Interfaces:**
- Consumes: W1 資料、W3 compile/emit、`coordinator.autonomy` 的 `scan_specs`/`detect_cycles`/`ready_units`（唯讀；此 import 經 coordinator `__init__` 鏈間接觸及 memory——tests 層豁免，見設計 §8）

- [ ] **Step 1: 寫失敗測試（W1+W3 未合流前為 RED）**

```python
# tests/test_deck_integration.py
from __future__ import annotations

from paulshaclaw.coordinator.autonomy import detect_cycles, ready_units, scan_specs
from paulshaclaw.deck.compile import compile_combo, emit
from paulshaclaw.deck.schema import DEFAULT_CARDS_PATH, DEFAULT_COMBOS_DIR, load_cards, load_combo


def _emit_combo(tmp_path, combo_name, task):
    cards = load_cards(DEFAULT_CARDS_PATH)
    combo = load_combo(DEFAULT_COMBOS_DIR / f"{combo_name}.yaml", cards)
    result = compile_combo(combo, cards, task, change="demo-change", allow_external=True)
    emit(result, tmp_path)
    return result


def test_feature_oneshot_parse_level(tmp_path):
    result = _emit_combo(tmp_path, "feature-oneshot", "整合示例任務")
    metas = scan_specs(tmp_path)
    assert len(metas) == len(result.slices)          # scan 解析綠
    detect_cycles(metas)                              # 無環、無重複 slice_id
    assert ready_units(metas, lambda sid: True) == []  # 全 hold → 即使依賴全滿足也不就緒


def test_mcu_feature_parse_level(tmp_path):
    result = _emit_combo(tmp_path, "mcu-feature", "mcu 整合示例")
    metas = scan_specs(tmp_path)
    detect_cycles(metas)
    assert ready_units(metas, lambda sid: True) == []
    assert len(metas) == len(result.slices)
```

- [ ] **Step 2: 跑測試（依 lane 合流狀態 RED 或直接 PASS）**

Run: `uv run pytest tests/test_deck_integration.py -v 2>&1 | tail -3`
Expected: W1+W3 合流後 PASS；未合流則 FAIL（缺 data 或 API）——這就是整合節點的意義

- [ ] **Step 3: 全 repo 測試 + policy gate**

Run: `uv run pytest -q 2>&1 | tail -3`
Expected: 全綠（integration_test_gate）

Run: `python3 -m policy_check --repo . 2>&1 | tail -3`（若模組存在；不存在則跳過並記錄）
Expected: 零 fail

- [ ] **Step 4: Commit**

```bash
git add tests/test_deck_integration.py
git commit -m "test(deck): W7 parse-level 整合驗證——scan/cycles/hold 不就緒（#186）"
```

---

### Task 15: 收尾 — DoD 實走與 docs 對齊

**Files:**
- Modify: `README.md`（deck 章節）
- Modify: `openspec/changes/deck-cards-combo-phase-a/tasks.md`（勾稽）

- [ ] **Step 1: DoD 實走（乾淨 shell）**

```bash
export PSC_MANAGER_SPECS_DIR=$(mktemp -d)
psc deck list
psc deck compile feature-oneshot --task "DoD 實走示例" --change demo --allow-external --emit
ls "$PSC_MANAGER_SPECS_DIR"           # 期望：5 份 <slug>-*.md，全 hold
grep -l "dispatch: hold" "$PSC_MANAGER_SPECS_DIR"/*.md | wc -l   # 期望 = 5
psc deck verify code-review --task-slug dod
```
Expected: compile/emit 成功、5 份 hold specs、verify 對未產出卡回 FAIL（exit 1）——行為皆符合設計 §5/§6。

- [ ] **Step 2: README/docs 對齊（R-18 同 PR）**

README 增 deck 小節（定位：#186 Phase A 宣告層；指向設計 spec 與 `psc deck --help`）；`openspec/changes/deck-cards-combo-phase-a/tasks.md` 全部勾選。

- [ ] **Step 3: 最終驗證與 commit**

Run: `uv run pytest -q 2>&1 | tail -2`
Expected: 全綠

```bash
git add README.md openspec/changes/deck-cards-combo-phase-a/tasks.md
git commit -m "docs(deck): Phase A 收尾——README deck 章節 + change 勾稽（#186）"
```

後續（不在本計劃）：PR body 寫 `Closes` 不適用（#186 尚有 Phase B/C，用一般引用 `#186`）；facade `specs_dir()` 提案（設計 Open Question）；archive change 於 review 通過後走 `opsx:archive`。

---

## Self-Review 紀錄

- **Spec 覆蓋**：deck-schema（Task 1/2）、deck-compile（Task 6–11、14）、deck-verify（Task 12）、deck-data（Task 3–5）、persona-skills-binding（Task 13）——五 capability 全對應。slice_group 已回灌 change specs。
- **佔位符**：無 TBD/TODO；每個 code step 含完整程式碼與預期輸出。
- **型別一致性**：`compile_combo` 簽名在 Task 7 定義、Task 8/9 只替換內部函式；`Card.card_class`（YAML key `class`）在 Task 1/3/12 一致；`EMITTED_FRONTMATTER_FIELDS` 於 Task 2 定義、Task 7 的 frontmatter 產生對齊四欄位。
