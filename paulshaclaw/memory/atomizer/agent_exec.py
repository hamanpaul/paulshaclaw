from __future__ import annotations

import hashlib
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class AgentExecError(Exception):
    """Raised when an agent subprocess cannot produce usable output."""


class AgentClient(ABC):
    @abstractmethod
    def run(self, prompt: str) -> str:
        """Return raw agent output for a prompt."""


class AgentExecClient(AgentClient):
    def __init__(self, command: list[str], timeout: int = 600) -> None:
        self._command = list(command)
        self._timeout = timeout

    def run(self, prompt: str) -> str:
        if not self._command:
            raise AgentExecError("agent command not configured")
        try:
            completed = subprocess.run(
                self._command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AgentExecError(f"agent command not found: {self._command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AgentExecError(f"agent timed out after {self._timeout}s") from exc
        if completed.returncode != 0:
            raise AgentExecError(f"agent exited with code {completed.returncode}")
        if not completed.stdout.strip():
            raise AgentExecError("agent produced empty output")
        return completed.stdout


class FakeAgentClient(AgentClient):
    def __init__(self, canned_output: str) -> None:
        self._canned_output = canned_output

    def run(self, prompt: str) -> str:
        return self._canned_output


class CachingAgentClient(AgentClient):
    """Freeze raw output by prompt hash so reruns stay deterministic."""

    def __init__(self, inner: AgentClient, cache_dir: Path) -> None:
        self._inner = inner
        self._cache_dir = cache_dir

    def cache_path_for(self, prompt: str) -> Path:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{prompt_hash}.txt"

    @staticmethod
    def _write_text_atomically(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def run(self, prompt: str) -> str:
        path = self.cache_path_for(prompt)
        if path.exists():
            try:
                cached = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                pass
            else:
                if cached:
                    return cached
        output = self._inner.run(prompt)
        self._write_text_atomically(path, output)
        return output
