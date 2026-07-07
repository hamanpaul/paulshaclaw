from __future__ import annotations

from paulshaclaw.deck.schema import Card
from paulshaclaw.deck.verify import verify_card


def _card(produces):
    return Card(
        id="c",
        kind="skill",
        type="headless",
        card_class="core",
        skill_ref="x",
        produces=tuple(produces),
    )


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
