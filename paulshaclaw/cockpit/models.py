from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlotAnchor:
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class PaneRecord:
    pane_id: str
    session_name: str
    window_index: str
    title: str
    command: str
    left: int
    top: int
    width: int
    height: int
    active: bool
    pane_tty: str = ""
    pane_current_path: str = ""
    host_short: str = ""
    # Human label for the work list: the pane title when set, otherwise a
    # derived fallback (e.g. "minicom COM0" / "[node]"). Empty until enriched.
    summary: str = ""

    @property
    def display_summary(self) -> str:
        return self.summary or self.title

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def anchor(self) -> SlotAnchor:
        return SlotAnchor(
            left=self.left,
            top=self.top,
            width=self.width,
            height=self.height,
        )


@dataclass(frozen=True)
class JobSummary:
    source: str
    status: str
    trace_id: str | None
    pane_id: str | None
    scope: str | None


@dataclass(frozen=True)
class JobRow:
    slice_id: str
    state: str
    source_section: str
    # manager status 的 attention／held／recent_done 條目本來就帶著「為什麼」與
    # 「可以做什麼」，先前攤平成 JobRow 時被丟掉，operator 只看得到狀態字串。
    # 這幾欄一路帶到渲染層，讓 needs_human 有可執行的下一步（#264）。
    reason: str = ""
    next_actions: tuple[str, ...] = ()
    job_id: str = ""
    branch: str = ""
    needs_human: bool = False

    @property
    def workflow_id(self) -> str:
        """``wf-<hash>-<phase>`` 形式的 slice 拆出 workflow 前綴，其餘回空字串。"""
        prefix, _, remainder = self.slice_id.partition("-")
        if prefix != "wf" or not remainder:
            return ""
        run_hash, _, phase = remainder.partition("-")
        return f"wf-{run_hash}" if phase else ""

    @property
    def display_name(self) -> str:
        """主顯示名：`wf-<hash>-` 這種執行環境前綴降為次要，留下看得懂的任務名。"""
        workflow_id = self.workflow_id
        if not workflow_id:
            return self.slice_id
        return self.slice_id[len(workflow_id) + 1 :]

    @property
    def human_state(self) -> str:
        """區分兩種 needs_human：job 已收工待裁決 vs. slice 仍卡著等人動手。"""
        if not self.needs_human:
            return ""
        return "待裁決" if self.source_section == "recent_done" else "阻塞中"

    @property
    def detail_line(self) -> str:
        """needs_human 的第二行：為什麼 + 下一步。

        任一項缺就明說是上游沒給，不留一列「只有狀態、沒有意義」的東西給
        operator 猜。命令用 ``--actor $USER`` 而非佔位符，讓它可以直接複製執行；
        多個 action 時保留 ``a|b`` 形式，因為那本來就要人挑一個。
        """
        if not self.needs_human:
            return ""
        if not self.reason and not self.next_actions:
            return "上游未帶 reason／next_actions（manager status 契約缺口）"
        why = self.reason or "上游未帶 reason"
        if self.next_actions:
            actions = "|".join(self.next_actions)
            how = f"cortex slice-action {self.slice_id} {actions} --actor $USER"
        else:
            how = "無可執行 action，需查 manager handoff manifest"
        return f"{why} · {how}"
