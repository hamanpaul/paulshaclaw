from __future__ import annotations

import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

from paulshaclaw.memory.atomizer import agent_exec

STUB = Path(__file__).resolve().parent / "fixtures" / "atomizer" / "fake-agent.py"
CANONICAL_FAKE_JSON = (
    '[{"title":"alpha","artifact_kind":"report","project":"paulshaclaw",'
    '"tags":["t1"],"body":"alpha distilled","source_fragment_indices":[0],'
    '"relations":[{"type":"mentions","entity":"MTK"}]}]'
)


class AgentExecTests(unittest.TestCase):
    def make_sandbox(self, name: str) -> Path:
        root = Path(__file__).resolve().parent / ".tmp-agent-exec"
        path = root / f"{name}-{uuid.uuid4().hex}"
        path.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        self.addCleanup(self._cleanup_parent, root)
        return path

    @staticmethod
    def _cleanup_parent(root: Path) -> None:
        if root.exists() and not any(root.iterdir()):
            root.rmdir()

    def test_fake_client_returns_canned(self):
        client = agent_exec.FakeAgentClient(CANONICAL_FAKE_JSON)
        self.assertEqual(client.run("anything"), CANONICAL_FAKE_JSON)

    def test_exec_client_runs_stub_and_returns_stdout(self):
        client = agent_exec.AgentExecClient([sys.executable, str(STUB)], timeout=30)
        out = client.run("hello prompt")
        self.assertEqual(out.strip(), CANONICAL_FAKE_JSON)

    def test_exec_client_missing_command_raises(self):
        client = agent_exec.AgentExecClient(["/nonexistent/bin/nope"], timeout=5)
        with self.assertRaises(agent_exec.AgentExecError):
            client.run("x")

    def test_exec_client_nonzero_exit_raises(self):
        client = agent_exec.AgentExecClient(
            [sys.executable, "-c", "import sys; sys.exit(3)"],
            timeout=5,
        )
        with self.assertRaises(agent_exec.AgentExecError):
            client.run("x")

    def test_exec_client_timeout_raises(self):
        client = agent_exec.AgentExecClient(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            timeout=1,
        )
        with self.assertRaises(agent_exec.AgentExecError):
            client.run("x")

    def test_exec_client_empty_stdout_raises(self):
        client = agent_exec.AgentExecClient(
            [sys.executable, "-c", "import sys; sys.stdin.read(); print('', end='')"],
            timeout=5,
        )
        with self.assertRaises(agent_exec.AgentExecError):
            client.run("x")

    def test_caching_client_reuses_by_prompt_hash(self):
        calls = {"n": 0}

        class Counting(agent_exec.AgentClient):
            def run(self, prompt: str) -> str:
                calls["n"] += 1
                return CANONICAL_FAKE_JSON

        cache_dir = self.make_sandbox("cache-hit")
        cached = agent_exec.CachingAgentClient(Counting(), cache_dir)
        self.assertEqual(cached.run("p"), CANONICAL_FAKE_JSON)
        self.assertEqual(cached.run("p"), CANONICAL_FAKE_JSON)
        self.assertEqual(calls["n"], 1)

    def test_caching_client_corrupt_entry_is_miss(self):
        cache_dir = self.make_sandbox("cache-corrupt")
        cached = agent_exec.CachingAgentClient(
            agent_exec.FakeAgentClient(CANONICAL_FAKE_JSON),
            cache_dir,
        )
        cached.cache_path_for("p").write_bytes(b"\xff")
        self.assertEqual(cached.run("p"), CANONICAL_FAKE_JSON)

    def test_caching_client_empty_entry_is_miss(self):
        calls = {"n": 0}

        class Counting(agent_exec.AgentClient):
            def run(self, prompt: str) -> str:
                calls["n"] += 1
                return CANONICAL_FAKE_JSON

        cache_dir = self.make_sandbox("cache-empty")
        cached = agent_exec.CachingAgentClient(Counting(), cache_dir)
        cached.cache_path_for("p").write_text("", encoding="utf-8")
        self.assertEqual(cached.run("p"), CANONICAL_FAKE_JSON)
        self.assertEqual(calls["n"], 1)

    def test_caching_client_unreadable_entry_is_miss(self):
        calls = {"n": 0}

        class Counting(agent_exec.AgentClient):
            def run(self, prompt: str) -> str:
                calls["n"] += 1
                return CANONICAL_FAKE_JSON

        cache_dir = self.make_sandbox("cache-unreadable")
        cached = agent_exec.CachingAgentClient(Counting(), cache_dir)
        cached.cache_path_for("p").write_text("stale", encoding="utf-8")

        with mock.patch.object(Path, "read_text", side_effect=OSError("boom")):
            self.assertEqual(cached.run("p"), CANONICAL_FAKE_JSON)
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
