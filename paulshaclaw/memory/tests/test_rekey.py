from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from paulshaclaw.memory import rekey
from paulshaclaw.memory.moc import frontmatter_io as fio

OLD_KEY = "github.com/hamanpaul/testpilot"
OLD_DIR = "github.com__hamanpaul__testpilot"


def _slice(
    root: Path,
    dirname: str,
    project: str,
    name: str,
    body: str,
    *,
    title: str = "uart-fix",
) -> Path:
    path = root / "knowledge" / dirname / name
    path.parent.mkdir(parents=True, exist_ok=True)
    slice_id = name.split("--")[-1].removesuffix(".md")
    path.write_text(
        f"---\nslice_id: {slice_id}\nmemory_layer: knowledge\n"
        f"project: {project}\nartifact_kind: report\ntitle: {title}\n---\n{body}\n",
        encoding="utf-8",
    )
    return path


class RekeyProjectTests(unittest.TestCase):
    def test_dry_run_writes_manifest_and_touches_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "真實筆記內容一。")

            summary = rekey.rekey_project(
                root,
                old_key=OLD_KEY,
                new_slug="testpilot",
                now="2026-07-02T00:00:00Z",
                apply=False,
            )

            self.assertTrue(path.exists())
            fm, _body = fio.read(path.read_text(encoding="utf-8"))
            self.assertEqual(fm["project"], OLD_KEY)
            self.assertEqual(summary["planned"], 1)
            self.assertEqual(summary["rekeyed"], 0)
            manifests = list((root / "runtime" / "ledger").glob("rekey-*.jsonl"))
            self.assertEqual(len(manifests), 1)
            rows = [json.loads(line) for line in manifests[0].read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(rows[0]["status"], "dry-run")
            self.assertEqual(rows[0]["from"], OLD_KEY)
            self.assertEqual(rows[0]["to"], "testpilot")

    def test_apply_moves_file_updates_frontmatter_and_rebuilds_moc(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "真實筆記內容：UART2 pinmux 設錯時靜默失效。"
            path = _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", body)

            summary = rekey.rekey_project(
                root,
                old_key=OLD_KEY,
                new_slug="testpilot",
                now="2026-07-02T00:00:00Z",
                apply=True,
            )

            self.assertFalse(path.exists())
            target = root / "knowledge" / "testpilot" / "uart-fix--sl-a1.md"
            self.assertTrue(target.exists())
            fm, new_body = fio.read(target.read_text(encoding="utf-8"))
            self.assertEqual(fm["project"], "testpilot")
            self.assertEqual(fm["slice_id"], "sl-a1")
            self.assertEqual(new_body.strip(), body)
            self.assertEqual(summary["rekeyed"], 1)
            self.assertTrue((root / "knowledge" / "testpilot-moc.md").exists())

    def test_apply_removes_emptied_source_dir_and_orphan_moc(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "內容")
            orphan = root / "knowledge" / f"{OLD_DIR}-moc.md"
            orphan.write_text("---\nmemory_layer: moc\n---\nstale\n", encoding="utf-8")

            summary = rekey.rekey_project(
                root,
                old_key=OLD_KEY,
                new_slug="testpilot",
                now="2026-07-02T00:00:00Z",
                apply=True,
            )

            self.assertFalse((root / "knowledge" / OLD_DIR).exists())
            self.assertFalse(orphan.exists())
            self.assertTrue(summary["removed_source_dir"])
            self.assertTrue(summary["removed_orphan_moc"])

    def test_conflict_target_is_skipped_and_source_not_stamped(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "舊 key 內容")
            _slice(root, "testpilot", "testpilot", "uart-fix--sl-a1.md", "同名既有檔")

            summary = rekey.rekey_project(
                root,
                old_key=OLD_KEY,
                new_slug="testpilot",
                now="2026-07-02T00:00:00Z",
                apply=True,
            )

            self.assertTrue(src.exists())
            fm, _body = fio.read(src.read_text(encoding="utf-8"))
            self.assertEqual(fm["project"], OLD_KEY)
            self.assertEqual(summary["conflicts"], 1)
            self.assertEqual(summary["rekeyed"], 0)

    def test_other_projects_untouched(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = _slice(
                root,
                "airoha",
                "airoha",
                "note--sl-b1.md",
                "airoha 真筆記",
                title="note",
            )
            _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "內容")

            rekey.rekey_project(
                root,
                old_key=OLD_KEY,
                new_slug="testpilot",
                now="2026-07-02T00:00:00Z",
                apply=True,
            )

            self.assertTrue(other.exists())
            fm, _body = fio.read(other.read_text(encoding="utf-8"))
            self.assertEqual(fm["project"], "airoha")

    def test_unsafe_new_slug_raises(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(rekey.RekeyError):
                rekey.rekey_project(
                    root,
                    old_key=OLD_KEY,
                    new_slug="a/b",
                    now="2026-07-02T00:00:00Z",
                    apply=False,
                )

    def test_apply_rename_failure_preserves_source_and_has_manifest_first(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "內容")
            ledger = root / "runtime" / "ledger"
            manifest_present_at_rename: list[bool] = []

            def failing_rename(path_obj: Path, target: Path):
                manifest_present_at_rename.append(bool(list(ledger.glob("rekey-*.jsonl"))) if ledger.exists() else False)
                raise OSError("rename blocked")

            with mock.patch.object(Path, "rename", failing_rename):
                summary = rekey.rekey_project(
                    root,
                    old_key=OLD_KEY,
                    new_slug="testpilot",
                    now="2026-07-02T00:00:00Z",
                    apply=True,
                )

            self.assertTrue(manifest_present_at_rename and manifest_present_at_rename[0])
            self.assertTrue(source.exists())
            fm, _body = fio.read(source.read_text(encoding="utf-8"))
            self.assertEqual(fm["project"], OLD_KEY)
            self.assertEqual(summary["errors"], 1)
            manifests = list(ledger.glob("rekey-*.jsonl"))
            rows = [json.loads(line) for line in manifests[0].read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(rows[0]["status"], "error")

    def test_apply_surfaces_moc_rebuild_result(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "內容")

            with mock.patch(
                "paulshaclaw.memory.rekey.run_moc",
                return_value={"indexed": False, "warnings": ["search index skipped: boom"]},
            ):
                summary = rekey.rekey_project(
                    root,
                    old_key=OLD_KEY,
                    new_slug="testpilot",
                    now="2026-07-02T00:00:00Z",
                    apply=True,
                )

            self.assertFalse(summary["indexed"])
            self.assertEqual(summary["warnings"], ["search index skipped: boom"])


class RekeyCliTests(unittest.TestCase):
    def test_cli_apply_moves_file(self):
        from paulshaclaw.memory.cli import main

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "內容")

            rc = main(
                [
                    "memory",
                    "knowledge",
                    "rekey",
                    "--memory-root",
                    str(root),
                    "--from",
                    OLD_KEY,
                    "--to",
                    "testpilot",
                    "--now",
                    "2026-07-02T00:00:00Z",
                    "--apply",
                ]
            )

            self.assertEqual(rc, 0)
            self.assertTrue((root / "knowledge" / "testpilot" / "uart-fix--sl-a1.md").exists())

    def test_cli_rejects_slash_in_to(self):
        from paulshaclaw.memory.cli import main

        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            rc = main(
                [
                    "memory",
                    "knowledge",
                    "rekey",
                    "--memory-root",
                    str(root),
                    "--from",
                    OLD_KEY,
                    "--to",
                    "a/b",
                    "--now",
                    "2026-07-02T00:00:00Z",
                    "--dry-run",
                ]
            )

            self.assertEqual(rc, 2)
            ledger = root / "runtime" / "ledger"
            manifests = list(ledger.glob("rekey-*.jsonl")) if ledger.exists() else []
            self.assertEqual(manifests, [])

    def test_cli_surfaces_moc_rebuild_warnings(self):
        from paulshaclaw.memory.cli import main

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "內容")
            stderr = io.StringIO()

            with mock.patch(
                "paulshaclaw.memory.rekey.run_moc",
                return_value={"indexed": False, "warnings": ["search index skipped: boom"]},
            ):
                with redirect_stderr(stderr):
                    rc = main(
                        [
                            "memory",
                            "knowledge",
                            "rekey",
                            "--memory-root",
                            str(root),
                            "--from",
                            OLD_KEY,
                            "--to",
                            "testpilot",
                            "--now",
                            "2026-07-02T00:00:00Z",
                            "--apply",
                        ]
                    )

            self.assertEqual(rc, 1)
            self.assertIn("warning: search index skipped: boom", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
