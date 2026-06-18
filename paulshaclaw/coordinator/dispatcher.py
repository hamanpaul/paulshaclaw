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
        # (3) 取 dispatch 當下的 branch head（baseline）；取不到記 None。
        #     D5：baseline 持久化於 job 上（非實例 dict），故 poll_done 可跨進程比對。
        runner = git_runner or _default_git_runner
        try:
            dispatch_head: str | None = runner(["rev-parse", branch])
        except Exception:
            dispatch_head = None
        # (4) registry 記一筆 job（status=dispatched，含 dispatch_head baseline）
        job = self._registry.create_job(
            task=task, persona=persona, branch=branch,
            pane=pane_id, worktree=worktree, dispatch_head=dispatch_head,
        )
        return job

    def poll_done(
        self,
        job_id: str,
        git_runner: GitRunner | None = None,
    ) -> dict[str, object]:
        """branch 出現新 commit（head 異於 dispatch_head baseline）→ 標 done；否則維持原 status。

        baseline 從 job 記錄（`dispatch_head`）讀，故跨進程（CLI 多次獨立呼叫）仍可比對。
        baseline 為 None（dispatch 時取不到 head）時不自動完成——無 baseline 即無法判定有無新 commit。
        """
        job = self._registry.get_job(job_id)
        baseline = job.get("dispatch_head")
        if baseline is None:
            return job  # baseline 不明 → 不自動完成
        runner = git_runner or _default_git_runner
        try:
            current = runner(["rev-parse", job["branch"]])
        except Exception:
            return job  # 取不到 head → 無法判定，維持原狀
        if current != baseline:
            return self._registry.update_status(job_id, "done")
        return job
