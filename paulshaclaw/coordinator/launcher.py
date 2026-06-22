from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LaunchHandle:
    executor: str
    session_name: str
    pid: int
    log_path: str


def build_copilot_argv(*, prompt: str, slice_id: str, log_dir: str) -> list[str]:
    return [
        "copilot",
        "-p",
        prompt,
        "--remote",
        "--name",
        slice_id,
        "--log-dir",
        log_dir,
        "--output-format",
        "json",
        "--allow-all",
    ]


def build_claude_argv(*, prompt: str, slice_id: str, log_dir: str) -> list[str]:
    return [
        "claude",
        "-p",
        prompt,
        "--remote-control",
        "--output-format",
        "stream-json",
        "--name",
        slice_id,
        "--permission-mode",
        "acceptEdits",
    ]


def build_codex_argv(*, prompt: str, slice_id: str, log_dir: str) -> list[str]:
    return [
        "codex",
        "exec",
        prompt,
        "--remote",
        "psc",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "-o",
        str(Path(log_dir) / "last.json"),
    ]


@runtime_checkable
class AgentLauncher(Protocol):
    def launch(
        self,
        *,
        slice_id: str,
        prompt: str,
        worktree: str,
        log_dir: str,
    ) -> LaunchHandle: ...


_ARGV_BUILDERS = {
    "copilot": build_copilot_argv,
    "claude": build_claude_argv,
    "codex": build_codex_argv,
}


class SubprocessLauncher:
    """真實作：headless subprocess 啟動。測試 MUST 注入 fake，不實體化。"""

    def __init__(self, executor: str = "copilot") -> None:
        if executor not in _ARGV_BUILDERS:
            raise ValueError(f"unknown executor: {executor}")
        self._executor = executor

    def launch(self, *, slice_id: str, prompt: str, worktree: str, log_dir: str) -> LaunchHandle:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        argv = _ARGV_BUILDERS[self._executor](
            prompt=prompt,
            slice_id=slice_id,
            log_dir=log_dir,
        )
        env = {**os.environ, "PSC_SLICE_ID": slice_id}
        log_path = str(Path(log_dir) / f"{slice_id}.jsonl")
        with open(log_path, "ab") as logf:
            proc = subprocess.Popen(
                argv,
                cwd=worktree,
                env=env,
                stdout=logf,
                stderr=subprocess.STDOUT,
            )
        return LaunchHandle(
            executor=self._executor,
            session_name=slice_id,
            pid=proc.pid,
            log_path=log_path,
        )
