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
