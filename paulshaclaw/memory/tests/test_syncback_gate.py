import unittest
from typing import get_type_hints
from unittest.mock import patch

from paulshaclaw.lifecycle import schema as lifecycle_schema
from paulshaclaw.memory.syncback import gate


CANONICAL_STAGE3_REQUIRED_FIELDS = {
    "phase",
    "project",
    "slice_id",
    "artifact_kind",
    "version",
    "created_at",
    "created_by",
    "source_session",
    "gate_required",
    "supersedes",
    "checksum",
}


class SchemaConditionTest(unittest.TestCase):
    def test_check_schema_unextended_returns_conditionresult_and_passes_for_canonical_fields(self):
        res = gate._check_schema_unextended()
        self.assertTrue(hasattr(res, 'id'))
        self.assertEqual(res.id, 'schema_unextended')
        self.assertTrue(hasattr(res, 'passed'))
        self.assertIsInstance(res.passed, bool)
        self.assertEqual(set(lifecycle_schema.REQUIRED_FRONTMATTER_FIELDS), CANONICAL_STAGE3_REQUIRED_FIELDS)
        self.assertTrue(res.passed)
        self.assertEqual(res.detail, "")

    def test_check_schema_unextended_fails_when_required_fields_include_extra(self):
        extra_required = tuple(lifecycle_schema.REQUIRED_FRONTMATTER_FIELDS) + ("unexpected_required",)

        with patch.object(lifecycle_schema, "REQUIRED_FRONTMATTER_FIELDS", extra_required):
            res = gate._check_schema_unextended()

        self.assertFalse(res.passed)
        self.assertIn("extra", res.detail)
        self.assertIn("unexpected_required", res.detail)

    def test_check_schema_unextended_fails_when_required_fields_are_missing(self):
        missing_required = tuple(
            field
            for field in lifecycle_schema.REQUIRED_FRONTMATTER_FIELDS
            if field != "checksum"
        )

        with patch.object(lifecycle_schema, "REQUIRED_FRONTMATTER_FIELDS", missing_required):
            res = gate._check_schema_unextended()

        self.assertFalse(res.passed)
        self.assertIn("missing", res.detail)
        self.assertIn("checksum", res.detail)

    def test_sync_manifest_contains_expected_paths(self):
        expected = (
            "paulshaclaw/memory/",
            "paulshaclaw/memory/hooks/",
            "paulshaclaw/memory/hooks/install.sh",
            "paulshaclaw/memory/hooks/uninstall.sh",
        )
        self.assertIsInstance(gate.SYNC_MANIFEST, tuple)
        self.assertEqual(tuple(expected), tuple(gate.SYNC_MANIFEST))

    def test_contract_types_match_task1_plan(self):
        self.assertTrue(gate.ConditionResult.__dataclass_params__.frozen)
        self.assertTrue(gate.GateVerdict.__dataclass_params__.frozen)
        self.assertIs(get_type_hints(gate.GateVerdict)["ts"], str)


if __name__ == '__main__':
    unittest.main()
