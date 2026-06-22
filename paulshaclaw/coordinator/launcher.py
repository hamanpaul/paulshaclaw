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


def build_copilot_argv(
    *,
    prompt: str,
    slice_id: str,
    log_dir: str,
    worktree: str | None = None,
    remote: str | None = None,
) -> list[str]:
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


def build_claude_argv(
    *,
    prompt: str,
    slice_id: str,
    log_dir: str,
    worktree: str | None = None,
    remote: str | None = None,
) -> list[str]:
    argv = [
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
    if worktree is not None:
        argv.extend(["--add-dir", worktree])
    return argv


def build_codex_argv(
    *,
    prompt: str,
    slice_id: str,
    log_dir: str,
    worktree: str | None = None,
    remote: str | None = "psc",
) -> list[str]:
    argv = [
        "codex",
        "exec",
        prompt,
        "--remote",
        remote or "psc",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "-o",
        str(Path(log_dir) / "last.json"),
    ]
    if worktree is not None:
        argv.extend(["-C", worktree])
    return argv


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

    def __init__(
        self,
        executor: str = "copilot",
        *,
        relay_target: str | None = None,
        codex_remote: str = "psc",
    ) -> None:
        if executor not in _ARGV_BUILDERS:
            raise ValueError(f"unknown executor: {executor}")
        self._executor = executor
        self._relay_target = relay_target
        self._codex_remote = codex_remote

    def launch(self, *, slice_id: str, prompt: str, worktree: str, log_dir: str) -> LaunchHandle:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        argv = _ARGV_BUILDERS[self._executor](
            prompt=prompt,
            slice_id=slice_id,
            log_dir=log_dir,
            worktree=worktree,
            remote=self._codex_remote,
        )
        env = {**os.environ, "PSC_SLICE_ID": slice_id}
        if self._relay_target is not None:
            env["PSC_RELAY_TARGET"] = self._relay_target
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
