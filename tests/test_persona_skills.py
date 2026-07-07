from __future__ import annotations

import warnings

import pytest

from paulshaclaw.persona.contract import validate_persona_schema
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

CARDS = """\
version: 0
cards:
  - id: writing-plans
    kind: skill
    type: interactive
    class: core
    skill_ref: "superpowers:writing-plans"
    requires: []
    produces: []
"""


@pytest.fixture()
def catalog_path(tmp_path):
    p = tmp_path / "personas.yaml"
    p.write_text(MINI, encoding="utf-8")
    return p


@pytest.fixture()
def cards_path(tmp_path):
    p = tmp_path / "cards.yaml"
    p.write_text(CARDS, encoding="utf-8")
    return p


def test_skills_field_survives_to_contract(catalog_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        catalog = load_catalog(catalog_path)
    assert catalog["manager"].skills == ("writing-plans",)
    assert catalog["builder"].skills == ()


def test_unknown_card_id_warns_but_loads(catalog_path, cards_path, monkeypatch):
    from paulshaclaw.deck import schema as deck_schema

    monkeypatch.setattr(deck_schema, "DEFAULT_CARDS_PATH", cards_path)
    with pytest.warns(UserWarning, match=r"reviewer.*no-such-card"):
        catalog = load_catalog(catalog_path)
    assert "reviewer" in catalog


def test_invalid_skills_scalar_fails_closed(tmp_path):
    bad = tmp_path / "personas.yaml"
    bad.write_text(MINI.replace("skills: [writing-plans]", 'skills: ""'), encoding="utf-8")

    with pytest.raises(ValueError, match="manager: skills 必須是字串清單"):
        load_catalog(bad)


def test_null_skills_treated_as_empty(tmp_path):
    catalog_file = tmp_path / "personas.yaml"
    catalog_file.write_text(MINI.replace("skills: [writing-plans]", "skills: null"), encoding="utf-8")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        catalog = load_catalog(catalog_file)
    assert catalog["manager"].skills == ()


def test_validator_rejects_scalar_skills_on_raw_mapping():
    result = validate_persona_schema(
        {
            "manager": {
                "role": "manager",
                "version": "0.1",
                "summary": "s",
                "allowed_phases": ["plan"],
                "write_paths": ["docs/plan.md"],
                "allowed_tools": ["git"],
                "skills": "",
            },
            "builder": {
                "role": "builder",
                "version": "0.1",
                "summary": "s",
                "allowed_phases": ["build"],
                "write_paths": ["src/**"],
                "allowed_tools": ["git"],
            },
            "reviewer": {
                "role": "reviewer",
                "version": "0.1",
                "summary": "s",
                "allowed_phases": ["review"],
                "write_paths": ["reports/review/**"],
                "allowed_tools": ["git"],
            },
        }
    )

    assert not result.ok
    assert "manager: skills 必須是字串清單" in result.errors



def test_default_catalog_skills_all_resolve():
    # 對抗審查修正：真實 personas.yaml × 真實 deck 卡片目錄——全部 skills 引用必須可解析（無 warning）
    import warnings as _warnings

    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        catalog = load_catalog()
    unknown = [str(w.message) for w in caught if "未知 deck card" in str(w.message)]
    assert unknown == []
    assert all(len(c.skills) > 0 for c in catalog.values())  # 三 role 都有綁定


def test_broken_deck_catalog_warns_skipped(tmp_path, monkeypatch):
    # 對抗審查修正：deck 目錄壞損 → 明示「驗證跳過」warning，而非靜默 fail-open
    import paulshaclaw.deck.schema as deck_schema

    bad = tmp_path / "cards.yaml"
    bad.write_text("cards: {broken", encoding="utf-8")
    monkeypatch.setattr(deck_schema, "DEFAULT_CARDS_PATH", bad)
    with pytest.warns(UserWarning, match="shadow 驗證跳過"):
        load_catalog()
