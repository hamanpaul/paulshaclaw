from __future__ import annotations

from dataclasses import dataclass

# #322：phase → 執行角色。映射來源是 cortex 套件 `coordinator/workflow.py` 的
# `validate_manager_spine`（phase/persona 契約），不是 cockpit 端猜測。
# `未認領` 與未知 phase（含 legacy slice 無 phase）都退回空字串。
_PHASE_TO_PERSONA: dict[str, str] = {
    "claim": "manager",
    "ship": "manager",
    "define": "planner",
    "plan": "planner",
    "build": "builder",
    "verify": "reviewer",
    "review": "reviewer",
}

# #322：cortex 的 seven phases。`claim` 單列為「待認積壓」（沉底），其餘視為
# 「真正在管線裡」（12 件那種）。`未認領`（合成 self，來自 not_claimable）與未知
# phase 都不算 in-line。
_IN_LINE_PHASES: frozenset[str] = frozenset(
    {"define", "plan", "build", "verify", "review", "ship"}
)
_PENDING_PHASE: str = "claim"
_UNCLAIMED_PHASE: str = "未認領"


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
    # manager 是跨 repo 派工的，同一個 JOBS 面板會混進別的 project 的 workflow。
    # 不標 project，operator 根本知道該去哪個 repo 動手（#264）。
    repo: str = ""
    # #322 三軸重設計新增：workflow_run 條目本帶的真實三軸欄位（cortex 已從
    # slice 平面遷移到 workflow_run 平面，每條帶 work_id / current_phase / run_id）。
    # 全是預設值，舊的 legacy slice 建構點與既有測試不受影響。
    work_id: str = ""
    phase: str = ""
    run_id: str = ""
    kind: str = ""

    @property
    def project(self) -> str:
        """顯示用 project 名：`hamanpaul/paulsha-cortex` → `paulsha-cortex`。"""
        return self.repo.rpartition("/")[2] if self.repo else ""

    @property
    def persona(self) -> str:
        """phase → 執行角色。來源：cortex 套件 `coordinator/workflow.py`
        的 ``validate_manager_spine`` 是契約不是猜測（#322）。"""
        return _PHASE_TO_PERSONA.get(self.phase, "")

    @property
    def is_in_line(self) -> bool:
        """是否「真正在管線裡」：real phase 為 build/verify/review/...（非
        `claim` 待認積壓、非 `未認領`）。控制群組排序與「X 在管線」計數（#322）。"""
        return self.phase in _IN_LINE_PHASES

    @property
    def is_pending_claim(self) -> bool:
        """卡在 `claim`（尚未派工、無 job 紀錄）的積壓列（#322）。"""
        return self.phase == _PENDING_PHASE

    @property
    def is_not_claimable(self) -> bool:
        """`未認領`（來自 status.not_claimable，安裝版 cortex 0.1.8 沒此 key）（#322）。"""
        return self.phase == _UNCLAIMED_PHASE

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
        多個 action 時保留 ``a|b`` 形式，因為那本來就要人挑一個。（#322）

        workflow_run 走 ``cortex work <action> <work_id> --repo``（非 slice-action），
        但多數 action 需 fail-closed 的名義參數（``abandon`` 需 ``expected_run_id``＋
        ``reason``；``retry-build`` 需 40-hex ``expected_candidate``），detail 通常
        不附——故只給 ``next_actions`` 清單＋``run_id`` 讓使用者自行組命令（寧可少給
        也不給錯命令）。``claim`` 階段 manager 尚未派工，直接標「尚未派工」，勿誤讀成
        manager 正在跑。
        """
        if not self.needs_human:
            return ""
        if not self.reason and not self.next_actions:
            return "上游未帶 reason／next_actions（manager status 契約缺口）"
        why = self.reason or "上游未帶 reason"
        if self.is_pending_claim:
            # claim（派工前）manager 尚未建立 run：detail 明説「尚未派工」，勿誤讀。
            how = "尚未派工（manager 尚未建立 run）——需 manager 重新派工"
        elif self.kind == "workflow_run":
            # workflow_run 走 work-action，fail-closed 名義參數 detail 通常不附，
            # 只給可參考的下一步與 run_id，讓 operator 自行組命令（#322）。
            parts: list[str] = []
            if self.next_actions:
                parts.append("可選 action：" + "|".join(self.next_actions))
            if self.run_id:
                parts.append(f"run_id：{self.run_id}")
            how = "、".join(parts) if parts else "action 需 fail-closed 名義參數，無法自動產生可執行命令"
        elif self.next_actions:
            actions = "|".join(self.next_actions)
            how = f"cortex slice-action {self.slice_id} {actions} --actor $USER"
        else:
            how = "無可執行 action，需查 manager handoff manifest"
        return f"{why} · {how}"


@dataclass(frozen=True)
class JobGroup:
    """同一個 workflow／work 底下的 slice 收成一群。

    現場資料天然是 `project → workflow → phase` 三層，但攤平後同一個 workflow
    的四個 phase 會各佔一列（needs_human 還各帶一行細節），把面板行數吃光：
    實測 51 列其實只有 22 群、11 筆 needs_human 只代表 6 件事。收成摘要後
    10 行預算就裝得下全部要人動手的東西（#264）。
    """

    key: str
    rows: tuple[JobRow, ...]

    @property
    def lead(self) -> JobRow:
        return self.rows[0]

    @property
    def is_single(self) -> bool:
        return len(self.rows) == 1

    @property
    def needs_human_count(self) -> int:
        return sum(1 for row in self.rows if row.needs_human)

    @property
    def needs_human(self) -> bool:
        return self.needs_human_count > 0

    @property
    def item_count(self) -> int:
        """本群的工作總數（含各 phase）。（#322）"""
        return len(self.rows)

    @property
    def in_line_count(self) -> int:
        """本群「真正在管線裡」的個數（non-`claim`、non-`未認領` 的 real phase）。
        供群組標題「N 件 · X 在管線」的 X 使用。（#322）"""
        return sum(1 for row in self.rows if row.is_in_line)

    @property
    def pending_claim_count(self) -> int:
        """本群卡在 `claim`（尚未派工）的個數，控制排序沉底與標題「Y 待認領」。（#322）"""
        return sum(1 for row in self.rows if row.is_pending_claim)

    @property
    def not_claimable_count(self) -> int:
        """本群不可認領（全部 row 皆 ``not_claimable``）的個數；混合群（部分不可
        認領）亦列出，供標題「Z 不可認領」使用，補 ``is_unclaimed`` 只认整群的缺口。
        （#322）"""
        return sum(1 for row in self.rows if row.is_not_claimable)

    @property
    def is_unclaimed(self) -> bool:
        """整群都是未認領（全部 row 皆 `not_claimable`）。（#322）"""
        return bool(self.rows) and all(row.is_not_claimable for row in self.rows)

    @property
    def summary_trailer(self) -> str:
        """群組標題的計數副標：`N 件 · X 在管線 · Y 待認領 · Z 不可認領`。

        只印非零的區段：純未認領群只顯示「不可認領」，純在管線群不顯示待認領。
        供三軸分組時讓 operator 一眼看清每群的大小與積壓結構。（#322）"""
        parts = [f"{self.item_count} 件"]
        if self.in_line_count:
            parts.append(f"{self.in_line_count} 在管線")
        if self.pending_claim_count:
            parts.append(f"{self.pending_claim_count} 待認領")
        if self.not_claimable_count:
            parts.append(f"{self.not_claimable_count} 不可認領")
        return " · ".join(parts)

    @property
    def project(self) -> str:
        return self.lead.project

    @property
    def branch(self) -> str:
        """群組的 branch：同一 workflow 各 phase 共用一條分支；lead 沒值時
        （in_flight／ready／held 的 ingest 不帶 branch，見 app.py）退到第一個有值的 row。"""
        for row in self.rows:
            if row.branch:
                return row.branch
        return ""

    @property
    def workflow_id(self) -> str:
        return self.lead.workflow_id

    @property
    def job_id(self) -> str:
        return self.lead.job_id if self.is_single else ""

    @property
    def human_state(self) -> str:
        return self.lead.human_state if self.is_single else ""

    @property
    def state_label(self) -> str:
        """單筆沿用原狀態；多筆講「幾個 phase、幾個等人」。"""
        if self.is_single:
            return self.lead.state
        waiting = self.needs_human_count
        if waiting == len(self.rows):
            return f"{len(self.rows)} phase 全待裁決"
        if waiting:
            return f"{len(self.rows)} phase（{waiting} 待裁決）"
        states = {row.state for row in self.rows}
        if len(states) == 1:
            return f"{len(self.rows)} phase {states.pop()}"
        return f"{len(self.rows)} phase"

    @property
    def headline_state(self) -> str:
        """狀態欄要講的那一件事。

        單筆 needs_human 時 `needs_human` 與「待裁決」同義，兩個都印只是把
        次要欄的空間吃掉，讓 workflow id 這種真正要用來識別的東西被擠掉。
        """
        if self.is_single:
            return self.human_state or self.lead.state
        return self.state_label

    @property
    def raw_state(self) -> str:
        """原始 job state；與 headline 同義時不重複顯示。"""
        if not self.is_single:
            return ""
        state = self.lead.state
        return "" if state == self.headline_state or self.human_state == "待裁決" else state

    @property
    def display_name(self) -> str:
        """多筆時主欄位放群組身分，phase 移到細節行。

        operator 認得的身分是 branch（issue 編號在裡面），wf-hash 是機器 id
        （#305）——有 branch 就用它，沒有才退回 workflow id／work 名。
        """
        if self.is_single:
            return self.lead.display_name
        return self.branch or self.workflow_id or self.key

    @property
    def note(self) -> str:
        """次要欄附註：「上游沒給 reason」這件事要講，但不值得佔一整行——
        面板只有 10 行，那一行留給真的有原因、有下一步可做的群。"""
        if not self.needs_human:
            return ""
        if any(row.reason or row.next_actions for row in self.rows):
            return ""
        return "原因未知"

    @property
    def detail_line(self) -> str:
        """只在有實質內容（原因或可執行動作）時才佔第二行。

        多筆共用同一個 reason 時併成一句並列出 phase；reason 各異時逐 phase 列，
        因為那時 operator 需要知道是哪個 phase 卡在什麼上。
        """
        # 第二行是給「要人動手」的群用的。held 這種依賴未滿足會自己解開，
        # 把它的 reasons 攤出來只會把真正等人的群擠掉（實測可長到 500+ 字）。
        if not self.needs_human:
            return ""
        if self.is_single:
            row = self.lead
            return row.detail_line if (row.reason or row.next_actions) else ""
        reasons = {row.reason for row in self.rows if row.reason}
        if not reasons:
            return ""
        phases = " / ".join(self._phase_label(row) for row in self.rows)
        if len(reasons) == 1:
            return f"{reasons.pop()} · {phases}"
        return " / ".join(
            f"{self._phase_label(row)}: {row.reason or '—'}" for row in self.rows
        )

    def _phase_label(self, row: JobRow) -> str:
        """群組內的短 phase 名：把共用的 work 前綴剝掉，只留辨識用的尾段。"""
        name = row.display_name
        prefix = f"{self.key}-"
        return name[len(prefix) :] if name.startswith(prefix) else name
