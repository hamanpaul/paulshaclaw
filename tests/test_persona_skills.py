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
    with pytest.warns(UserWarning, match="no-such-card"):
        catalog = load_catalog(catalog_path)
    assert "reviewer" in catalog
