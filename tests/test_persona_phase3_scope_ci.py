from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


def _valid_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "from_role": "builder",
        "to_role": "reviewer",
        "phase": "review",
        "gate_status": "passed",
        "slice_id": "persona-phase3-scope-gate",
        "summary": "phase3 scope ci shadow",
        "artifact_refs": ["feature/persona-phase3-scope-gate"],
        "created_at": "2026-06-18T00:00:00+08:00",
        "base": "main",
        "head": "feature/persona-phase3-scope-gate",
    }
    payload.update(overrides)
    return payload


def _write_manifest(repo_root: Path, **overrides: object) -> Path:
    from paulshaclaw.persona import handoff

    path = repo_root / "runtime" / "handoff" / "persona-phase3-scope-gate.json"
    handoff.write_manifest(path, _valid_manifest(**overrides))
    return path


def _run(repo_root: Path, env: dict[str, str]) -> tuple[int, dict[str, object]]:
    """跑 scope_ci.main 並擷取 stdout JSON。"""
    from paulshaclaw.persona import scope_ci

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = scope_ci.main(argv=["--repo", str(repo_root)], env=env)
    out = buf.getvalue().strip().splitlines()
    payload = json.loads(out[-1]) if out else {}
    return code, payload


class NoManifestTests(unittest.TestCase):
    def test_empty_handoff_dir_skips_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "runtime" / "handoff").mkdir(parents=True)  # 空目錄
            code, payload = _run(repo, {"GITHUB_BASE_REF": "main"})
            self.assertEqual(code, 0)
            self.assertTrue(payload.get("skipped"))
            self.assertIn("skipped", json.dumps(payload))

    def test_no_runtime_dir_at_all_skips_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)  # 連 runtime/ 都沒有 → 仍須乾淨跳過、不報錯
            code, payload = _run(repo, {})
            self.assertEqual(code, 0)
            self.assertTrue(payload.get("skipped"))


class InScopeShadowTests(unittest.TestCase):
    def _patch_diff(self, paths: list[str]):
        from paulshaclaw.persona import gate

        original = gate.compute_changed_paths
        gate.compute_changed_paths = lambda base, head, repo=None: list(paths)
        self.addCleanup(setattr, gate, "compute_changed_paths", original)

    def test_in_scope_diff_ok_and_exit_zero(self) -> None:
        self._patch_diff(["paulshaclaw/persona/scope_ci.py", "tests/test_x.py"])
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _write_manifest(repo)  # from_role=builder
            code, payload = _run(repo, {"GITHUB_BASE_REF": "main", "GITHUB_SHA": "deadbeef"})
            self.assertEqual(code, 0)
            self.assertEqual(payload["role"], "builder")
            self.assertEqual(payload["violations"], [])
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "shadow")
            self.assertEqual(payload["base"], "origin/main")
            self.assertEqual(payload["head"], "deadbeef")


class OutOfScopeShadowTests(unittest.TestCase):
    def _patch_diff(self, paths: list[str]):
        from paulshaclaw.persona import gate

        original = gate.compute_changed_paths
        gate.compute_changed_paths = lambda base, head, repo=None: list(paths)
        self.addCleanup(setattr, gate, "compute_changed_paths", original)

    def test_out_of_scope_diff_violations_but_still_exit_zero(self) -> None:
        # builder 不可寫 docs/** → 越界
        self._patch_diff(["paulshaclaw/persona/scope_ci.py", "docs/secret.md"])
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _write_manifest(repo)  # from_role=builder
            code, payload = _run(repo, {"GITHUB_BASE_REF": "main"})
            self.assertEqual(code, 0)  # shadow 恆 0，即使越界
            self.assertFalse(payload["ok"])
            offending = [v["path"] for v in payload["violations"]]
            self.assertIn("docs/secret.md", offending)
            for v in payload["violations"]:
                self.assertTrue(v["reason"])  # 帶可審計原因

    def test_diff_failure_fail_closed_but_shadow_exit_zero(self) -> None:
        from paulshaclaw.persona import gate

        def _raise(base, head, repo=None):
            raise RuntimeError("git diff 失敗（fail-closed）: no merge base")

        original = gate.compute_changed_paths
        gate.compute_changed_paths = _raise
        self.addCleanup(setattr, gate, "compute_changed_paths", original)

        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _write_manifest(repo)
            code, payload = _run(repo, {"GITHUB_BASE_REF": "main"})
            self.assertEqual(code, 0)  # shadow 仍放行
            self.assertIn("diff_error", payload)
            self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
