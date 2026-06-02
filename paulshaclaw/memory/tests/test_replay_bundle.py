from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from paulshaclaw.memory.replay import bundle, cli


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _tmp_dir():
    return TemporaryDirectory(dir=_REPO_ROOT)


def _slice(root: Path, slice_id: str, *, filename: str | None = None) -> Path:
    name = filename or f"{slice_id}.md"
    path = root / "knowledge" / "p" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"slice_id: {slice_id}\n"
        "project: p\n"
        "memory_layer: knowledge\n"
        "distilled_from: claude:s1\n"
        "---\n"
        f"DISTILLED {slice_id}\n",
        encoding="utf-8",
    )
    return path


def _raw_inbox(root: Path) -> Path:
    path = root / "inbox" / "research" / "claude" / "2026-06-02" / "s1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "memory_layer: inbox\n"
        "project: p\n"
        "source_agent: claude\n"
        "source_session: s1\n"
        "source_artifact: research\n"
        "captured_at: 2026-06-02T00:00:00Z\n"
        "---\n"
        "RAW PROMPT CONTENT\n",
        encoding="utf-8",
    )
    return path


class ReplayBundleTests(unittest.TestCase):
    def test_build_writes_manifest_slices_ledger_and_excludes_raw(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            _raw_inbox(root)
            s = _slice(root, "sl-1")
            out = root / "bundle-out"

            bundle.build(root, [s], out, selection={"project": "p"}, now="2026-06-02T06:00:00Z")

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["raw_excluded"])
            self.assertEqual(manifest["counts"]["slices"], 1)
            self.assertTrue((out / "slices" / "sl-1.md").exists())
            self.assertTrue((out / "ledger.jsonl").exists())

            blob = "".join(
                p.read_text(encoding="utf-8")
                for p in out.rglob("*")
                if p.is_file()
            )
            self.assertIn("DISTILLED", blob)
            self.assertNotIn("RAW PROMPT CONTENT", blob)

    def test_rebuild_cleans_stale_slices(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            s1 = _slice(root, "sl-1")
            out = root / "bundle-out"

            bundle.build(root, [s1], out, selection={"project": "p"}, now="2026-06-02T06:00:00Z")
            self.assertTrue((out / "slices" / "sl-1.md").exists())

            (out / "slices" / "stale.md").write_text("STALE\n", encoding="utf-8")
            s2 = _slice(root, "sl-2")
            bundle.build(root, [s2], out, selection={"project": "p"}, now="2026-06-02T06:01:00Z")

            self.assertFalse((out / "slices" / "stale.md").exists())
            self.assertFalse((out / "slices" / "sl-1.md").exists())
            self.assertTrue((out / "slices" / "sl-2.md").exists())

    def test_empty_selection_writes_empty_bundle_with_warning(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            out = root / "bundle-out"

            bundle.build(root, [], out, selection={"project": "none"}, now="2026-06-02T06:00:00Z")

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["counts"]["slices"], 0)
            self.assertIn("warnings", manifest)
            self.assertTrue(any("empty" in w for w in manifest["warnings"]))

    def test_corrupt_lifecycle_ledger_emits_warning(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            s = _slice(root, "sl-1")
            out = root / "bundle-out"

            lifecycle_path = root / "runtime" / "ledger" / "lifecycle.jsonl"
            lifecycle_path.parent.mkdir(parents=True, exist_ok=True)
            lifecycle_path.write_text("{not-json}\n", encoding="utf-8")

            bundle.build(root, [s], out, selection={"project": "p"}, now="2026-06-02T06:00:00Z")

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("warnings", manifest)
            self.assertTrue(any("lifecycle" in w for w in manifest["warnings"]))
            self.assertTrue((out / "ledger.jsonl").exists())

    def test_duplicate_slice_ids_raise_bundle_error(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            s1 = _slice(root, "sl-dup", filename="a.md")
            s2 = _slice(root, "sl-dup", filename="b.md")
            out = root / "bundle-out"

            with self.assertRaises(bundle.BundleError):
                bundle.build(root, [s1, s2], out, selection={"project": "p"}, now="2026-06-02T06:00:00Z")

    def test_cli_warns_but_succeeds_on_empty_selection(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            out = root / "bundle-out"
            args = argparse.Namespace(
                memory_root=str(root),
                project="p",
                tag=None,
                entity=None,
                include_decayed=False,
                out=str(out),
                now="2026-06-02T06:00:00Z",
            )

            stderr = io.StringIO()
            stdout = io.StringIO()
            with (
                mock.patch("paulshaclaw.memory.replay.selector.select", return_value=[]),
                contextlib.redirect_stderr(stderr),
                contextlib.redirect_stdout(stdout),
            ):
                code = cli.run(args)

            self.assertEqual(code, 0)
            self.assertIn("empty", stderr.getvalue().lower())
            self.assertIn(str(out), stdout.getvalue())

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(any("empty" in w for w in manifest.get("warnings", [])))

    def test_cli_surfaces_selector_error_cleanly(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            out = root / "bundle-out"
            args = argparse.Namespace(
                memory_root=str(root),
                project=None,
                tag=None,
                entity=None,
                include_decayed=False,
                out=str(out),
                now="2026-06-02T06:00:00Z",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = cli.run(args)

            self.assertNotEqual(code, 0)
            self.assertIn("facet", stderr.getvalue())

    def test_cli_surfaces_relations_ledger_failure_cleanly(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            s = _slice(root, "sl-1")
            out = root / "bundle-out"
            args = argparse.Namespace(
                memory_root=str(root),
                project="p",
                tag=None,
                entity=None,
                include_decayed=False,
                out=str(out),
                now="2026-06-02T06:00:00Z",
            )

            stderr = io.StringIO()
            with (
                mock.patch("paulshaclaw.memory.replay.selector.select", return_value=[s]),
                mock.patch(
                    "paulshaclaw.memory.replay.bundle.relations.read_edges",
                    side_effect=Exception("boom"),
                ),
                contextlib.redirect_stderr(stderr),
            ):
                code = cli.run(args)

            self.assertNotEqual(code, 0)
            self.assertIn("bundle error", stderr.getvalue())

    def test_cli_surfaces_processing_ledger_failure_cleanly(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            s = _slice(root, "sl-1")
            out = root / "bundle-out"
            args = argparse.Namespace(
                memory_root=str(root),
                project="p",
                tag=None,
                entity=None,
                include_decayed=False,
                out=str(out),
                now="2026-06-02T06:00:00Z",
            )

            stderr = io.StringIO()
            with (
                mock.patch("paulshaclaw.memory.replay.selector.select", return_value=[s]),
                mock.patch(
                    "paulshaclaw.memory.replay.bundle.processing.read_events",
                    side_effect=Exception("boom"),
                ),
                contextlib.redirect_stderr(stderr),
            ):
                code = cli.run(args)

            self.assertNotEqual(code, 0)
            self.assertIn("bundle error", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
