from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from paulshaclaw.deck.compile import (
    DeckCompileError,
    compile_combo,
    emit,
    parse_with_spec,
    slugify_task,
    specs_dir,
)
from paulshaclaw.deck.schema import load_cards, load_combo

CARDS_YAML = """\
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
    produces: []
    persona_binding: builder
  - id: tdd-red
    kind: skill
    type: headless
    class: core
    skill_ref: "superpowers:test-driven-development"
    slice_group: build
    requires: []
    produces: []
    persona_binding: builder
  - id: subagent-build
    kind: skill
    type: headless
    class: core
    skill_ref: "superpowers:subagent-driven-development"
    slice_group: build
    requires: []
    produces: []
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
    produces: []
    persona_binding: manager
  - id: adversarial-review
    kind: skill
    type: headless
    class: core
    skill_ref: "codex:adversarial-review"
    requires: ["reports/review/*<task-slug>*.md"]
    produces: ["reports/review/*<task-slug>*-adversarial.md"]
    persona_binding: reviewer
  - id: mcu-hw-evidence
    kind: skill
    type: interactive
    class: niche
    skill_ref: "mcu-coding-skill"
    requires: []
    produces: ["docs/superpowers/specs/*<task-slug>*-hw-evidence.md"]
    persona_binding: planner
"""

FEATURE_ONESHOT_YAML = """\
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
"""

SOLO_ADV_COMBO = """\
combo:
  id: solo-adv
  task_type: feature
  cards:
    - ref: adversarial-review
"""

SPLIT_BUILD_COMBO = """\
combo:
  id: split-build
  task_type: feature
  cards:
    - ref: brainstorming
    - ref: openspec-propose
    - ref: writing-plans
    - ref: worktree-isolation
    - ref: code-review
    - ref: tdd-red
"""


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _feature_oneshot(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", CARDS_YAML))
    combo = load_combo(_write(tmp_path, "feature-oneshot.yaml", FEATURE_ONESHOT_YAML), cards)
    return cards, combo


def _solo_adv(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", CARDS_YAML))
    combo = load_combo(_write(tmp_path, "solo-adv.yaml", SOLO_ADV_COMBO), cards)
    return cards, combo


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
    from paulshaclaw.coordinator.manager_daemon import default_specs_dir

    monkeypatch.delenv("PSC_MANAGER_SPECS_DIR", raising=False)
    assert str(specs_dir()) == default_specs_dir()


def test_compile_slice_grouping_and_chain(tmp_path):
    cards, combo = _feature_oneshot(tmp_path)
    result = compile_combo(combo, cards, "示例 LED 功能", change="demo", allow_external=True)
    ids = [slice_doc.slice_id for slice_doc in result.slices]
    slug = result.task_slug
    assert ids == [
        f"{slug}-build",
        f"{slug}-code-review",
        f"{slug}-verification",
        f"{slug}-ship",
        f"{slug}-adversarial-review",
    ]
    assert len(result.checklist) == 3


def test_compile_frontmatter_hold_and_chain(tmp_path):
    cards, combo = _feature_oneshot(tmp_path)
    result = compile_combo(combo, cards, "示例 LED 功能", change="demo", allow_external=True)
    first = result.slices[0].content
    assert first.startswith("---\n")
    assert "dispatch: hold" in first
    second = result.slices[1].content
    assert f"- {result.task_slug}-build" in second


def test_compile_missing_change_placeholder_errors(tmp_path):
    cards, combo = _feature_oneshot(tmp_path)
    with pytest.raises(DeckCompileError, match="--change"):
        compile_combo(combo, cards, "示例 LED 功能", allow_external=True)


def test_compile_frontmatter_exact_keyset(tmp_path):
    from paulshaclaw.deck.schema import EMITTED_FRONTMATTER_FIELDS

    cards, combo = _feature_oneshot(tmp_path)
    result = compile_combo(combo, cards, "示例 LED 功能", change="demo", allow_external=True)
    for slice_doc in result.slices:
        block = slice_doc.content.split("---\n")[1]
        assert set(yaml.safe_load(block)) == set(EMITTED_FRONTMATTER_FIELDS)


def test_requires_uncovered_blocks_without_allow_external(tmp_path):
    cards, combo = _solo_adv(tmp_path)
    with pytest.raises(DeckCompileError, match="allow-external"):
        compile_combo(combo, cards, "demo task", change="demo", plan_ref="docs/plan.md")


def test_requires_external_allowed_and_reported(tmp_path):
    cards, combo = _solo_adv(tmp_path)
    result = compile_combo(
        combo,
        cards,
        "demo task",
        change="demo",
        allow_external=True,
        plan_ref="docs/plan.md",
    )
    assert result.external


def test_requires_archive_path_still_counts_as_external(tmp_path):
    cards_yaml = CARDS_YAML.replace(
        'produces: ["reports/review/*<task-slug>*.md"]',
        'produces: ["reports/review/archive/*<task-slug>*.md"]',
    )
    cards = load_cards(_write(tmp_path, "cards.yaml", cards_yaml))
    combo = load_combo(_write(tmp_path, "feature-oneshot.yaml", FEATURE_ONESHOT_YAML), cards)
    with pytest.raises(DeckCompileError, match="allow-external"):
        compile_combo(combo, cards, "demo task", change="demo")


def test_parse_with_spec_forms():
    assert parse_with_spec("mcu-hw-evidence") == ("mcu-hw-evidence", None, None)
    assert parse_with_spec("x:after=code-review") == ("x", "after", "code-review")
    assert parse_with_spec("x:before=tdd-red") == ("x", "before", "tdd-red")


def test_with_explicit_position_inserts_without_replacing(tmp_path):
    cards, combo = _feature_oneshot(tmp_path)
    result = compile_combo(
        combo,
        cards,
        "demo task",
        change="demo",
        with_cards=("mcu-hw-evidence:after=brainstorming",),
        allow_external=True,
    )
    assert len(result.checklist) == 4


def test_with_unresolvable_position_fails_closed(tmp_path):
    cards, combo = _feature_oneshot(tmp_path)
    with pytest.raises(DeckCompileError, match="after=|before="):
        compile_combo(
            combo,
            cards,
            "demo task",
            change="demo",
            with_cards=("mcu-hw-evidence",),
            allow_external=True,
        )


def test_only_exclusive_mode(tmp_path):
    cards, combo = _feature_oneshot(tmp_path)
    result = compile_combo(
        combo,
        cards,
        "demo task",
        change="demo",
        only=("code-review", "verification"),
        allow_external=True,
    )
    assert [slice_doc.slice_id for slice_doc in result.slices] == [
        f"{result.task_slug}-code-review",
        f"{result.task_slug}-verification",
    ]


def test_with_and_only_are_mutually_exclusive(tmp_path):
    cards, combo = _feature_oneshot(tmp_path)
    with pytest.raises(DeckCompileError, match="不可同時"):
        compile_combo(
            combo,
            cards,
            "demo task",
            change="demo",
            with_cards=("mcu-hw-evidence:after=brainstorming",),
            only=("code-review",),
            allow_external=True,
        )


def test_emit_writes_flat_and_refuses_overwrite(tmp_path):
    cards, combo = _feature_oneshot(tmp_path)
    result = compile_combo(combo, cards, "demo task", change="demo", allow_external=True)
    written = emit(result, tmp_path)
    assert all(path.parent == tmp_path for path in written)
    assert {path.name for path in written} == {slice_doc.filename for slice_doc in result.slices}
    with pytest.raises(DeckCompileError, match="已存在"):
        emit(result, tmp_path)


def test_emit_force_overwrites_atomically(tmp_path):
    cards, combo = _feature_oneshot(tmp_path)
    result = compile_combo(combo, cards, "demo task", change="demo", allow_external=True)
    emit(result, tmp_path)
    written = emit(result, tmp_path, force=True)
    assert written
    assert all(path.read_text(encoding="utf-8").startswith("---") for path in written)


def test_emit_force_rolls_back_on_replace_failure(tmp_path, monkeypatch):
    from paulshaclaw.deck import compile as deck_compile

    cards, combo = _feature_oneshot(tmp_path / "deck")
    result = compile_combo(combo, cards, "demo task", change="demo", allow_external=True)
    target = tmp_path / "specs"
    target.mkdir()
    originals = {}
    for index, slice_doc in enumerate(result.slices):
        final_path = target / slice_doc.filename
        text = f"old-{index}"
        final_path.write_text(text, encoding="utf-8")
        originals[final_path] = text

    real_replace = deck_compile.os.replace
    failing_target = target / result.slices[1].filename

    def flaky_replace(src, dst):
        if Path(dst) == failing_target and str(src).endswith(".tmp"):
            raise OSError("boom")
        return real_replace(src, dst)

    monkeypatch.setattr(deck_compile.os, "replace", flaky_replace)
    with pytest.raises(DeckCompileError, match="emit"):
        emit(result, target, force=True)
    for path, text in originals.items():
        assert path.read_text(encoding="utf-8") == text


def test_compile_rejects_duplicate_slice_ids_from_split_group(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", CARDS_YAML))
    combo = load_combo(_write(tmp_path, "split-build.yaml", SPLIT_BUILD_COMBO), cards)
    with pytest.raises(DeckCompileError, match="重複"):
        compile_combo(combo, cards, "demo task", change="demo", allow_external=True)


def test_verify_commands_include_change_when_needed(tmp_path):
    cards, combo = _feature_oneshot(tmp_path)
    result = compile_combo(combo, cards, "demo task", change="demo", allow_external=True)
    assert "psc deck verify openspec-archive --task-slug demo-task --change demo" in result.verify_commands
