import unittest
from typing import get_type_hints
from unittest.mock import patch
from contextlib import contextmanager
from pathlib import Path
import shutil
import uuid

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


@contextmanager
def _repo_tempdir():
    root = (
        Path(__file__).resolve().parents[3]
        / ".scratch_task2"
        / f"test-syncback-gate-{uuid.uuid4().hex}"
    )
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


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


class FileConditionTest(unittest.TestCase):
    def test_check_evidence_present_passes_when_files_exist_and_nonempty(self):
        with _repo_tempdir() as repo_root:
            evidence_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory" / "evidence"
            evidence_dir.mkdir(parents=True)
            (evidence_dir / "README.md").write_text("evidence")
            (evidence_dir / "stage2-integration-template.md").write_text("template")

            res = gate._check_evidence_present(repo_root)
            self.assertEqual(res.id, 'evidence_present')
            self.assertTrue(res.passed)

    def test_check_evidence_present_fails_when_missing_or_empty(self):
        with _repo_tempdir() as repo_root:
            # missing files
            res = gate._check_evidence_present(repo_root)
            self.assertFalse(res.passed)
            self.assertIn('missing', res.detail)

            # empty file
            evidence_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory" / "evidence"
            evidence_dir.mkdir(parents=True)
            (evidence_dir / "README.md").write_text("")
            (evidence_dir / "stage2-integration-template.md").write_text("\n")
            res2 = gate._check_evidence_present(repo_root)
            self.assertFalse(res2.passed)
            self.assertIn('empty', res2.detail)

    def test_check_review_clear_passes_for_mergeable_conclusion(self):
        for heading in ("### Conclusion", "### 結論"):
            with self.subTest(heading=heading):
                with _repo_tempdir() as repo_root:
                    docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
                    docs_dir.mkdir(parents=True)
                    (docs_dir / "review.md").write_text(
                        f'# review\n\n{heading}\n\n- 結論：可合併。\n'
                    )

                    res = gate._check_review_clear(repo_root)

                    self.assertEqual(res.id, 'review_clear')
                    self.assertTrue(res.passed)

    def test_check_review_clear_fails_on_blocking_or_missing(self):
        with _repo_tempdir() as repo_root:
            docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
            docs_dir.mkdir(parents=True)

            # missing file
            res = gate._check_review_clear(repo_root)
            self.assertFalse(res.passed)
            self.assertIn('missing', res.detail)

            # present but missing conclusion section
            (docs_dir / "review.md").write_text('# review\n\nNo conclusion here\n')
            res2 = gate._check_review_clear(repo_root)
            self.assertFalse(res2.passed)
            self.assertIn('结論', res2.detail or '結論')

            # blocking conclusion
            (docs_dir / "review.md").write_text('# review\n\n## 結論\n\n- 結論：不可合併。\n')
            res3 = gate._check_review_clear(repo_root)
            self.assertFalse(res3.passed)
            self.assertIn('不可', res3.detail)

    def test_check_review_clear_rejects_noncanonical_conclusion_headings(self):
        for heading in (
            "## Conclusion Draft",
            "### Conclusion Draft",
            "## 結論草稿",
            "### 結論草稿",
        ):
            with self.subTest(heading=heading):
                with _repo_tempdir() as repo_root:
                    docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
                    docs_dir.mkdir(parents=True)
                    (docs_dir / "review.md").write_text(
                        f'# review\n\n{heading}\n\n- Conclusion: mergeable.\n'
                    )

                    res = gate._check_review_clear(repo_root)

                    self.assertFalse(res.passed)
                    self.assertIn('missing', res.detail)

    def test_check_review_clear_fails_closed_for_ambiguous_conclusion(self):
        with _repo_tempdir() as repo_root:
            docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
            docs_dir.mkdir(parents=True)
            (docs_dir / "review.md").write_text(
                '# review\n\n## Conclusion\n\n- Conclusion: needs follow-up discussion.\n'
            )

            res = gate._check_review_clear(repo_root)

            self.assertFalse(res.passed)
            self.assertIn('unrecognized', res.detail)

    def test_check_review_clear_fails_closed_for_invalid_utf8_review(self):
        with _repo_tempdir() as repo_root:
            docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
            docs_dir.mkdir(parents=True)
            (docs_dir / "review.md").write_bytes(b"## \xe7\xb5\x90\xe8\xab\x96\n\n- \xff\xfe\xfa\n")

            res = gate._check_review_clear(repo_root)

            self.assertFalse(res.passed)
            self.assertIn('unreadable', res.detail)

    def test_check_review_clear_fails_closed_for_unreadable_review(self):
        with _repo_tempdir() as repo_root:
            docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
            docs_dir.mkdir(parents=True)
            review_path = docs_dir / "review.md"
            review_path.write_text('# review\n\n## 結論\n\n- 結論：可合併。\n')
            review_path.chmod(0)
            try:
                res = gate._check_review_clear(repo_root)
            finally:
                review_path.chmod(0o644)

            self.assertFalse(res.passed)
            self.assertIn('unreadable', res.detail)

    def test_check_review_clear_fails_for_english_negated_merge_phrases(self):
        phrases = (
            'do not merge',
            'not ready to merge',
            'not approved for merge',
        )

        for phrase in phrases:
            with self.subTest(phrase=phrase):
                with _repo_tempdir() as repo_root:
                    docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
                    docs_dir.mkdir(parents=True)
                    (docs_dir / "review.md").write_text(
                        f'# review\n\n## Conclusion\n\n- Conclusion: {phrase}.\n'
                    )

                    res = gate._check_review_clear(repo_root)

                    self.assertFalse(res.passed)
    def test_check_review_clear_passes_for_mergeable_conclusion_with_no_blocking_issues(self):
        with _repo_tempdir() as repo_root:
            docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
            docs_dir.mkdir(parents=True)
            (docs_dir / "review.md").write_text(
                '# review\n\n## Notes\n\n- Reviewer note: do not merge until conclusion is updated.\n\n'
                '## Conclusion\n\n- Conclusion: mergeable. No blocking issues.\n'
            )

            res = gate._check_review_clear(repo_root)

            self.assertTrue(res.passed)

    def test_check_review_clear_passes_when_failing_word_is_non_blocking_context(self):
        with _repo_tempdir() as repo_root:
            docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
            docs_dir.mkdir(parents=True)
            (docs_dir / "review.md").write_text(
                '# review\n\n## Conclusion\n\n- Conclusion: mergeable. No failing tests in reviewed scope.\n'
            )

            res = gate._check_review_clear(repo_root)

            self.assertTrue(res.passed)

    def test_check_review_clear_passes_for_zh_tw_canonical_pass_wording(self):
        with _repo_tempdir() as repo_root:
            docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
            docs_dir.mkdir(parents=True)
            (docs_dir / "review.md").write_text(
                '# review\n\n## 結論\n\n- 結論：可合併，無阻斷性問題。\n'
            )

            res = gate._check_review_clear(repo_root)

            self.assertTrue(res.passed)

    def test_check_review_clear_fails_for_mixed_mergeable_and_blocking_markers(self):
        for marker in ("BLOCKING", "BLOCKER"):
            with self.subTest(marker=marker):
                with _repo_tempdir() as repo_root:
                    docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
                    docs_dir.mkdir(parents=True)
                    (docs_dir / "review.md").write_text(
                        f'# review\n\n## Conclusion\n\n- Conclusion: mergeable.\n- {marker}\n'
                    )

                    res = gate._check_review_clear(repo_root)

                    self.assertFalse(res.passed)
                    self.assertIn(marker, res.detail)

    def test_check_review_clear_fails_for_lowercase_blocking_markers(self):
        for marker in ("blocking", "blocker", "blockers"):
            with self.subTest(marker=marker):
                with _repo_tempdir() as repo_root:
                    docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
                    docs_dir.mkdir(parents=True)
                    (docs_dir / "review.md").write_text(
                        f'# review\n\n## Conclusion\n\n- Conclusion: mergeable.\n- {marker} issue remains.\n'
                    )

                    res = gate._check_review_clear(repo_root)

                    self.assertFalse(res.passed)
                    self.assertIn(marker, res.detail)

    def test_check_review_clear_passes_for_negated_blocked_wording(self):
        with _repo_tempdir() as repo_root:
            docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
            docs_dir.mkdir(parents=True)
            (docs_dir / "review.md").write_text(
                '# review\n\n## Conclusion\n\n- Conclusion: No blocked items. Mergeable.\n'
            )

            res = gate._check_review_clear(repo_root)

            self.assertTrue(res.passed)

    def test_check_review_clear_fails_for_positive_blocked_wording(self):
        with _repo_tempdir() as repo_root:
            docs_dir = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory"
            docs_dir.mkdir(parents=True)
            (docs_dir / "review.md").write_text(
                '# review\n\n## Conclusion\n\n- Conclusion: Blocked on issue #123.\n'
            )

            res = gate._check_review_clear(repo_root)

            self.assertFalse(res.passed)
            self.assertIn('Blocked', res.detail)


if __name__ == '__main__':
    unittest.main()
