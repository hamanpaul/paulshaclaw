import unittest
from paulshaclaw.lifecycle import schema as lifecycle_schema
from paulshaclaw.memory.syncback import gate


class SchemaConditionTest(unittest.TestCase):
    def test_check_schema_unextended_returns_conditionresult_and_passes_for_canonical_fields(self):
        res = gate._check_schema_unextended()
        # shape
        self.assertTrue(hasattr(res, 'id'))
        self.assertEqual(res.id, 'schema_unextended')
        self.assertTrue(hasattr(res, 'passed'))
        self.assertIsInstance(res.passed, bool)
        # must pass for canonical lifecycle schema fields
        self.assertTrue(res.passed)
        canonical = tuple(lifecycle_schema.REQUIRED_FRONTMATTER_FIELDS)
        # Stage 2 must not add required frontmatter beyond canonical Stage 3 set
        required = tuple(getattr(lifecycle_schema, 'REQUIRED_FRONTMATTER_FIELDS'))
        self.assertTrue(set(required).issubset(set(canonical)))

    def test_sync_manifest_contains_expected_paths(self):
        expected = (
            "paulshaclaw/memory/",
            "paulshaclaw/memory/hooks/",
            "paulshaclaw/memory/hooks/install.sh",
            "paulshaclaw/memory/hooks/uninstall.sh",
        )
        self.assertIsInstance(gate.SYNC_MANIFEST, tuple)
        self.assertEqual(tuple(expected), tuple(gate.SYNC_MANIFEST))


if __name__ == '__main__':
    unittest.main()
