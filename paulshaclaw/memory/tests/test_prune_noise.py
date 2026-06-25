from __future__ import annotations

import json
import pathlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from paulshaclaw.memory.cli import main


def _slice(root: Path, project: str, name: str, body: str) -> Path:
    p = root / "knowledge" / project / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nslice_id: {name.split('--')[-1].replace('.md','')}\nmemory_layer: knowledge\n"
        f"project: {project}\nartifact_kind: report\n---\n{body}\n", encoding="utf-8")
    return p


class PruneNoiseTests(unittest.TestCase):
    def _seed(self, root: Path):
        noise = _slice(root, "p", "cwd--sl-n1.md", "## CWD\n/home/paul_chen")
        good = _slice(root, "p", "versioning-and-release-policy--sl-g1.md",
                      "本 repo 採 conventional commit；tag 必須等於 VERSION，里程碑改用 marker branch。")
        return noise, good

    def test_dry_run_does_not_delete(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            noise, good = self._seed(root)
            rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                       "--now", "2026-06-25T00:00:00Z", "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertTrue(noise.exists())
            self.assertTrue(good.exists())

    def test_apply_deletes_noise_keeps_good_and_writes_manifest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            noise, good = self._seed(root)
            rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                       "--now", "2026-06-25T00:00:00Z", "--apply"])
            self.assertEqual(rc, 0)
            self.assertFalse(noise.exists())
            self.assertTrue(good.exists())
            manifests = list((root / "runtime" / "ledger").glob("prune-*.jsonl"))
            self.assertEqual(len(manifests), 1)
            rows = [json.loads(l) for l in manifests[0].read_text().splitlines() if l.strip()]
            self.assertTrue(any(r["reason"].startswith("structural-echo") for r in rows))
            self.assertTrue((root / "knowledge" / "p-moc.md").exists())

    def test_durable_manifest_exists_before_any_delete(self):
        # #139 finding 2: a durable manifest of intended deletions must be written
        # BEFORE any unlink, so a later write failure can't leave deletes unaudited.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            ledger = root / "runtime" / "ledger"
            real_unlink = pathlib.Path.unlink
            manifest_present_at_first_unlink = []

            def spy_unlink(self_path, *a, **k):
                manifest_present_at_first_unlink.append(
                    bool(list(ledger.glob("prune-*.jsonl"))) if ledger.exists() else False)
                return real_unlink(self_path, *a, **k)

            with mock.patch.object(pathlib.Path, "unlink", spy_unlink):
                rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                           "--now", "2026-06-25T00:00:00Z", "--apply"])
            self.assertEqual(rc, 0)
            self.assertTrue(manifest_present_at_first_unlink, "expected at least one unlink")
            self.assertTrue(manifest_present_at_first_unlink[0],
                            "manifest must exist before the first delete")

    def test_apply_isolates_unreadable_file_without_deleting_it(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            noise, good = self._seed(root)
            bad = root / "knowledge" / "p" / "bad--sl-x.md"
            bad.write_bytes(b"\xff\xfe not utf8")
            rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                       "--now", "2026-06-25T00:00:00Z", "--apply"])
            self.assertEqual(rc, 0)
            self.assertTrue(good.exists())
            self.assertFalse(noise.exists())
            self.assertTrue(bad.exists())
            manifests = list((root / "runtime" / "ledger").glob("prune-*.jsonl"))
            self.assertEqual(len(manifests), 1)
            rows = [json.loads(l) for l in manifests[0].read_text().splitlines() if l.strip()]
            bad_rows = [r for r in rows if r["path"] == str(bad)]
            self.assertEqual(len(bad_rows), 1)
            self.assertEqual(bad_rows[0]["status"], "error")
            self.assertEqual(bad_rows[0]["reason"], "unreadable")


if __name__ == "__main__":
    unittest.main()
