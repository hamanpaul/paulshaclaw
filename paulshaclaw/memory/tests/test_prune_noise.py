from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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


if __name__ == "__main__":
    unittest.main()
