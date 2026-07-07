from __future__ import annotations

from paulshaclaw.deck.schema import DEFAULT_CARDS_PATH, DEFAULT_COMBOS_DIR, load_cards, load_combo

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
    assert interactive == {"brainstorming", "openspec-propose", "writing-plans"}
    assert {c.id for c in cards.values() if c.type == "headless"} == set(PHASE_CARDS) - interactive
    assert cards["worktree-isolation"].slice_group == "build"
    assert cards["tdd-red"].slice_group == "build"
    assert cards["subagent-build"].slice_group == "build"
    assert cards["openspec-archive"].slice_group == "ship"
    assert cards["policy-commit"].slice_group == "ship"


def test_feature_oneshot_combo_loads():
    cards = load_cards(DEFAULT_CARDS_PATH)
    combo = load_combo(DEFAULT_COMBOS_DIR / "feature-oneshot.yaml", cards)
    assert combo.id == "feature-oneshot"
    assert combo.task_type == "feature"
    assert [c.ref for c in combo.cards] == PHASE_CARDS
    assert [(gate.after, gate.exists) for gate in combo.gate_spine] == [
        ("writing-plans", ("docs/superpowers/plans/*<task-slug>*.md",)),
        ("code-review", ("reports/review/*<task-slug>*.md",)),
    ]
