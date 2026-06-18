from __future__ import annotations

import subprocess
from typing import Callable

from .registry import JobRegistry
from .seams import PaneSender, WorktreeCreator

# git_runner seam：收 git 參數、回 stdout 文字。預設真實作呼 git。
GitRunner = Callable[[list[str]], str]


def _default_git_runner(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _branch_for_task(task: str) -> str:
    return f"feature/{task}"


class Dispatcher:
    """派工原語：建 worktree → 送命令 → 記 job；poll_done 以 branch 新 commit 標 done。

    所有副作用經注入 seam（PaneSender / WorktreeCreator / git_runner）；
    單元測試注入 fake，不啟動真 tmux/worktree/copilot。
    """

    def __init__(
        self,
        registry: JobRegistry,
        pane_sender: PaneSender,
        worktree_creator: WorktreeCreator,
    ) -> None:
        self._registry = registry
        self._pane_sender = pane_sender
        self._worktree_creator = worktree_creator
        # job_id -> dispatch 當下的 branch head（baseline），供 poll_done 比對
        self._baseline_head: dict[str, str | None] = {}

    def dispatch(
        self,
        *,
        task: str,
        persona: str,
        pane_id: str,
        command: str,
        git_runner: GitRunner | None = None,
    ) -> dict[str, object]:
        branch = _branch_for_task(task)
        # (1) 先建 worktree；失敗則 raise（不送命令、不記 job — fail-closed）
        worktree = self._worktree_creator.create(branch)
        # (2) 忠實轉送呼叫者給的完整 command（本 change 不組裝 copilot 指令）
        self._pane_sender.send(pane_id, command)
        # (3) registry 記一筆 job（status=dispatched）
        job = self._registry.create_job(
            task=task, persona=persona, branch=branch,
            pane=pane_id, worktree=worktree,
        )
        # baseline head（若可取）供 poll_done 比對；取不到記 None
        runner = git_runner or _default_git_runner
        try:
            self._baseline_head[job["job_id"]] = runner(["rev-parse", branch])
        except Exception:
            self._baseline_head[job["job_id"]] = None
        return job

    def poll_done(
        self,
        job_id: str,
        git_runner: GitRunner | None = None,
    ) -> dict[str, object]:
        """branch 出現新 commit（head 異於 baseline）→ 標 done；否則維持原 status。"""
        job = self._registry.get_job(job_id)
        runner = git_runner or _default_git_runner
        try:
            current = runner(["rev-parse", job["branch"]])
        except Exception:
            return job  # 取不到 head → 無法判定，維持原狀
        baseline = self._baseline_head.get(job_id)
        if current != baseline:
            return self._registry.update_status(job_id, "done")
        return job
