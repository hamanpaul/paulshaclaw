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


def test_load_cards_wrong_version_rejected(tmp_path):
    bad = VALID_CARDS.replace("version: 0", "version: 99")
    with pytest.raises(DeckSchemaError, match="version"):
        load_cards(_write(tmp_path, "cards.yaml", bad))


def test_load_cards_unknown_placeholder_rejected(tmp_path):
    bad = VALID_CARDS.replace("<task-slug>", "<feature-name>")
    with pytest.raises(DeckSchemaError, match="feature-name"):
        load_cards(_write(tmp_path, "cards.yaml", bad))


def test_load_cards_malformed_placeholder_rejected(tmp_path):
    bad = VALID_CARDS.replace("<task-slug>", "<task_slug>")
    with pytest.raises(DeckSchemaError, match="task_slug"):
        load_cards(_write(tmp_path, "cards.yaml", bad))


def test_load_cards_unknown_field_rejected(tmp_path):
    bad = VALID_CARDS.replace("slice_group: build", "slcie_group: build")
    with pytest.raises(DeckSchemaError, match="slcie_group"):
        load_cards(_write(tmp_path, "cards.yaml", bad))


def test_load_cards_non_string_persona_binding_rejected(tmp_path):
    bad = VALID_CARDS.replace("persona_binding: planner", "persona_binding: 123")
    with pytest.raises(DeckSchemaError, match="persona_binding"):
        load_cards(_write(tmp_path, "cards.yaml", bad))


def test_load_cards_non_string_provider_binding_rejected(tmp_path):
    bad = VALID_CARDS.replace("produces: []", "produces: []\n    provider_binding: 123")
    with pytest.raises(DeckSchemaError, match="provider_binding"):
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


def test_load_combo_unknown_field_rejected(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    bad = VALID_COMBO.replace("gate_spine:", "gate_spien:")
    with pytest.raises(DeckSchemaError, match="gate_spien"):
        load_combo(_write(tmp_path, "demo.yaml", bad), cards)


def test_load_combo_unknown_card_entry_field_rejected(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    bad = VALID_COMBO.replace("depends_on: [writing-plans]", "depends_om: [writing-plans]")
    with pytest.raises(DeckSchemaError, match="depends_om"):
        load_combo(_write(tmp_path, "demo.yaml", bad), cards)


def test_load_combo_cycle_rejected(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    bad = VALID_COMBO.replace(
        "    - ref: writing-plans\n",
        "    - ref: writing-plans\n      depends_on: [build-a]\n",
    )
    with pytest.raises(DeckSchemaError, match="循環"):
        load_combo(_write(tmp_path, "demo.yaml", bad), cards)


def test_load_combo_unknown_placeholder_rejected(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    bad = VALID_COMBO.replace("<task-slug>", "<feature-name>")
    with pytest.raises(DeckSchemaError, match="feature-name"):
        load_combo(_write(tmp_path, "demo.yaml", bad), cards)


def test_load_combo_malformed_placeholder_rejected(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    bad = VALID_COMBO.replace("<task-slug>", "<Task-Slug>")
    with pytest.raises(DeckSchemaError, match="Task-Slug"):
        load_combo(_write(tmp_path, "demo.yaml", bad), cards)


def test_load_combo_unknown_gate_field_rejected(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    bad = VALID_COMBO.replace("exists:", "exsts:")
    with pytest.raises(DeckSchemaError, match="exsts"):
        load_combo(_write(tmp_path, "demo.yaml", bad), cards)


def test_load_combo_empty_gate_exists_rejected(tmp_path):
    cards = load_cards(_write(tmp_path, "cards.yaml", VALID_CARDS))
    bad = VALID_COMBO.replace(
        'exists: ["docs/superpowers/plans/*<task-slug>*.md"]',
        "exists: []",
    )
    with pytest.raises(DeckSchemaError, match="exists"):
        load_combo(_write(tmp_path, "demo.yaml", bad), cards)
