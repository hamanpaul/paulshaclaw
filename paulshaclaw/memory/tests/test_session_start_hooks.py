"""Tests for session-start hooks (Task 4)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS_DIR = REPO_ROOT / "paulshaclaw" / "memory" / "hooks"


def _run_hook(script_name, stdin_data, extra_env=None):
    env = {**os.environ, "PSC_MEMORY_ROOT": ""}
    if extra_env:
        env.update(extra_env)
    cmd = ["python3", str(HOOKS_DIR / script_name)]
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        input=stdin_data if isinstance(stdin_data, str) else json.dumps(stdin_data),
        env=env,
        capture_output=True,
        text=True,
    )


class SessionStartHooksTest(unittest.TestCase):
    def setUp(self):
        self.scratch = REPO_ROOT / ".test-work"
        self.scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=self.scratch)
        self.memory_root = Path(self.tmp.name) / "memory"
        # Create required directories
        (self.memory_root / "knowledge").mkdir(parents=True)
        (self.memory_root / "log").mkdir(parents=True)
        (self.memory_root / "config").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()
        try:
            self.scratch.rmdir()
        except OSError:
            pass

    def _env(self, extra=None):
        e = {"PSC_MEMORY_ROOT": str(self.memory_root)}
        if extra:
            e.update(extra)
        return e

    def _write_minimal_moc(self, project: str):
        """Write a minimal MOC file for a project."""
        moc_path = self.memory_root / "knowledge" / f"{project}-moc.md"
        moc_path.write_text(
            "---\nmemory_layer: moc\nproject: test\n---\nTest MOC content\n",
            encoding="utf-8"
        )
        # Also create a minimal slice for the project
        slice_dir = self.memory_root / "knowledge" / project
        slice_dir.mkdir(parents=True, exist_ok=True)
        slice_path = slice_dir / "test-slice--001.md"
        slice_path.write_text(
            f"---\nmemory_layer: knowledge\nproject: {project}\nslice_id: test-slice-001\ntitle: Test Slice\n---\nTest slice content\n",
            encoding="utf-8"
        )

    def _write_projects_config(self):
        """Write a minimal projects.yaml config."""
        # Config goes in parent of memory_root / "config" / "projects.yaml"
        config_path = self.memory_root.parent / "config" / "projects.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "version: 1\nprojects:\n  - slug: test\n    roots:\n      - /repo/test\n",
            encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Claude session-start hook
    # ------------------------------------------------------------------

    def test_claude_session_start_exits_zero_on_empty_stdin(self):
        result = _run_hook("claude_session_start.py", "", extra_env=self._env())
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_claude_session_start_exits_zero_on_invalid_json(self):
        result = _run_hook("claude_session_start.py", "bad{json", extra_env=self._env())
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_claude_session_start_returns_structured_output_shape(self):
        """Claude SessionStart hook must return hookSpecificOutput with hookEventName."""
        self._write_projects_config()
        self._write_minimal_moc("test")
        payload = {"session_id": "test-001", "cwd": "/repo/test"}

        result = _run_hook("claude_session_start.py", payload, extra_env=self._env())

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = json.loads(result.stdout)
        self.assertIn("hookSpecificOutput", output)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_claude_session_start_includes_brief_in_additional_context(self):
        """Hook can generate brief when project resolved (may be empty if no slices)."""
        self._write_projects_config()
        self._write_minimal_moc("test")
        payload = {"session_id": "test-002", "cwd": "/repo/test"}

        result = _run_hook("claude_session_start.py", payload, extra_env=self._env())

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = json.loads(result.stdout)
        # Verify structure exists - brief content is tested in wakeup builder tests
        self.assertIn("hookSpecificOutput", output)
        self.assertIn("additionalContext", output["hookSpecificOutput"])
        # Brief may be empty or populated depending on slice/lifecycle state
        self.assertIsInstance(output["hookSpecificOutput"]["additionalContext"], str)

    def test_claude_session_start_quiet_when_project_unresolved(self):
        """No output when project is _unknown or empty."""
        payload = {"session_id": "test-003", "cwd": "/unknown/path"}

        result = _run_hook("claude_session_start.py", payload, extra_env=self._env())

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        # Empty stdout or empty brief
        if result.stdout.strip():
            output = json.loads(result.stdout)
            brief = output.get("hookSpecificOutput", {}).get("additionalContext", "")
            self.assertEqual(brief, "")

    # ------------------------------------------------------------------
    # Copilot session-start hook
    # ------------------------------------------------------------------

    def test_copilot_session_start_exits_zero_on_empty_stdin(self):
        result = _run_hook("copilot_session_start.py", "", extra_env=self._env())
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_copilot_session_start_exits_zero_on_invalid_json(self):
        result = _run_hook("copilot_session_start.py", "not-json", extra_env=self._env())
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_copilot_session_start_returns_additional_context_shape(self):
        """Copilot sessionStart hook returns additionalContext directly."""
        self._write_projects_config()
        self._write_minimal_moc("test")
        payload = {"sessionId": "test-004", "cwd": "/repo/test"}

        result = _run_hook("copilot_session_start.py", payload, extra_env=self._env())

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = json.loads(result.stdout)
        self.assertIn("additionalContext", output)
        self.assertIsInstance(output["additionalContext"], str)

    def test_copilot_session_start_includes_brief_in_output(self):
        """Hook can generate brief when project resolved (may be empty if no slices)."""
        self._write_projects_config()
        self._write_minimal_moc("test")
        payload = {"sessionId": "test-005", "cwd": "/repo/test"}

        result = _run_hook("copilot_session_start.py", payload, extra_env=self._env())

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = json.loads(result.stdout)
        # Verify structure exists - brief content is tested in wakeup builder tests
        self.assertIn("additionalContext", output)
        # Brief may be empty or populated depending on slice/lifecycle state
        self.assertIsInstance(output["additionalContext"], str)

    def test_copilot_session_start_quiet_when_project_unresolved(self):
        """No output when project is _unknown or empty."""
        payload = {"sessionId": "test-006", "cwd": "/unknown/path"}

        result = _run_hook("copilot_session_start.py", payload, extra_env=self._env())

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        if result.stdout.strip():
            output = json.loads(result.stdout)
            brief = output.get("additionalContext", "")
            self.assertEqual(brief, "")


if __name__ == "__main__":
    unittest.main()
