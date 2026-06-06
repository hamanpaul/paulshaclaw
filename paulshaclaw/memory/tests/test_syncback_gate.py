import pytest
from paulshaclaw.lifecycle import schema as lifecycle_schema
from paulshaclaw.memory.syncback import gate


def test_check_schema_unextended_returns_conditionresult_and_passes_for_canonical_fields():
    res = gate._check_schema_unextended()
    # shape
    assert hasattr(res, 'id')
    assert res.id == 'schema_unextended'
    assert hasattr(res, 'passed')
    # must pass for canonical lifecycle schema fields
    assert res.passed is True
    canonical = tuple(lifecycle_schema.REQUIRED_FRONTMATTER_FIELDS)
    # implementation may attach checked_fields; fall back to canonical
    assert getattr(res, 'checked_fields', canonical) == canonical


def test_sync_manifest_tuple_of_non_empty_strings():
    assert isinstance(gate.SYNC_MANIFEST, tuple)
    assert len(gate.SYNC_MANIFEST) > 0
    for item in gate.SYNC_MANIFEST:
        assert isinstance(item, str)
        assert item.strip() != ''
