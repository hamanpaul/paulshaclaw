"""JOBS 面板：Tree 為底的節點模型與 widget（取代舊 Static + 行預算截斷）。

不 import .app（避免循環）；app.py 反過來從這裡 import 並 re-export，
保持模組層名稱不變以維持既有測試相容。
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .models import JobGroup, JobRow

try:
    from textual.widgets import Tree

    _HAS_TEXTUAL = True
except Exception:  # pragma: no cover - fallback when textual not installed
    _HAS_TEXTUAL = False


# 語意狀態樣式（#308 owner 裁決）：glyph 統一「•」，狀態靠顏色五桶區分——
# wait-for-start 白、working 綠、broke 紅、wait-confirm 橘、finished 灰。
# 純函式，供工作清單／DETAIL／JOBS 上色與單測共用；未知狀態退回中性藍灰
# （不猜語意，寧可視覺上退到「非五桶」）。
_WAIT_START = ""  # 白＝終端預設前景（與 banner 一致，#317：指定 #E2E8F0 會有色差）
_WORKING = "#22C55E"
_BROKE = "#EF4444"
_WAIT_CONFIRM = "#F97316"
_FINISHED = "#94A3B8"  # 與白色 name 並排仍可辨；#64748B 太暗（#311）

_STATUS_STYLE: dict[str, tuple[str, str]] = {
    # wait for start（白）：還沒輪到它動（含依賴未滿足的 blocked/held）
    "ready": ("•", _WAIT_START),
    "queued": ("•", _WAIT_START),
    "pending": ("•", _WAIT_START),
    "blocked": ("•", _WAIT_START),
    "held": ("•", _WAIT_START),
    "dispatched": ("•", _WAIT_START),
    # working（綠）
    "running": ("•", _WORKING),
    "active": ("•", _WORKING),
    "reviewing": ("•", _WORKING),
    # broke（紅）
    "failed": ("•", _BROKE),
    "error": ("•", _BROKE),
    "dead": ("•", _BROKE),
    "degraded": ("•", _BROKE),
    # wait confirm（橘）
    "needs_human": ("•", _WAIT_CONFIRM),
    "attention": ("•", _WAIT_CONFIRM),
    # finished（灰）
    "passed": ("•", _FINISHED),
    "verified": ("•", _FINISHED),
    "success": ("•", _FINISHED),
    "ok": ("•", _FINISHED),
    "done": ("•", _FINISHED),
    "completed": ("•", _FINISHED),
    "exited": ("•", _FINISHED),
    "workflow-tracked": ("•", _FINISHED),
    "superseded": ("•", _FINISHED),
}
_STATUS_DEFAULT: tuple[str, str] = ("•", "#64748B")  # 未知狀態退更暗，讓 #94A3B8 給 finished（#311）


def status_style(status: str) -> tuple[str, str]:
    """狀態字串 → (glyph, rich 顏色)。大小寫不敏感；未知狀態退回中性點。"""
    return _STATUS_STYLE.get((status or "").strip().lower(), _STATUS_DEFAULT)


def _display_width(text: str) -> int:
    """終端顯示寬度：CJK 全形字佔兩欄，用 len() 排版會整欄歪掉。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad_display(text: str, width: int) -> str:
    """依顯示寬度補到定寬（`f"{s:<18}"` 會把全形字當一欄，中文欄位對不齊）。"""
    return text + " " * max(0, width - _display_width(text))


def _ellipsize_middle(text: str, width: int) -> str:
    """過長的 slice 名從中間省略：頭（work 名）與尾（phase）都是辨識關鍵，不能只砍一端。"""
    if _display_width(text) <= width or width < 3:
        return text
    head: list[str] = []
    tail: list[str] = []
    used = 1  # 省略號本身
    chars = list(text)
    while chars:
        ch = chars.pop(0) if len(head) <= len(tail) else chars.pop()
        cost = _display_width(ch)
        if used + cost > width:
            break
        used += cost
        (head if len(head) <= len(tail) else tail).append(ch)
    return "".join(head) + "…" + "".join(reversed(tail))


_TRAILER_ELLIPSIZE_MIN = 8  # 縮到比這還窄只剩無資訊量的碎片，寧可留白


def _fit_trailer(parts: tuple[str, ...], width: int) -> str:
    """次要欄依重要性由高到低排；塞不下時從尾端整項丟棄並標示有省略。

    硬切字元會把 `paulsha-cortex` 砍成半個名字，比少顯示一項更難讀。但退讓到
    只剩最重要的一項仍塞不下時（窄面板＋37 字元 branch 是常態），整項丟棄會讓
    trailer 全空、連 wf-hash 都不剩（#299）——這時改用 _ellipsize_middle 縮進
    預算：頭尾都保，branch 的 issue 編號在頭段不會丟。
    """
    kept = [part for part in parts if part]
    dropped = False
    while kept and _display_width(" · ".join(kept)) > width:
        if len(kept) == 1:
            budget = width - 2 if dropped else width  # dropped 時預留 " …" 兩欄
            if budget >= _TRAILER_ELLIPSIZE_MIN:
                kept[0] = _ellipsize_middle(kept[0], budget)
                break
        kept.pop()
        dropped = True
    text = " · ".join(kept)
    if dropped and kept:
        text = f"{text} …"
    return text


# 顯示層縮寫表（#302，owner 指定字面）：只在渲染組裝時替換——model 層屬性、
# style key（status_style 吃原始 state）與 detail 行的可複製命令都維持原始字串。
# 日後擴充（如 adversarial-review）在這裡加一行即可。
_LABEL_ABBREVS: tuple[tuple[str, str], ...] = (
    ("workflow-tracked", "[wf]-tracked"),
    ("subagent-build", "[sub]-build"),
    (" phase", " ph"),
)


def _abbrev_label(text: str) -> str:
    for verbose, short in _LABEL_ABBREVS:
        text = text.replace(verbose, short)
    return text


def _abbrev_branch(branch: str) -> str:
    """`feature/<N>-<slug>` → `feat/<N>-<slug>`：前綴是 git 慣例贅詞，編號才是資訊。"""
    if branch.startswith("feature/"):
        return "feat/" + branch[len("feature/") :]
    return branch


# JOBS 主行版面（顯示寬，非字元數）：state／name 欄依本批 rows 的自然寬伸縮
# （#308），剩餘全給 trailer；固定值只剩上下限與量不到 widget 寬度時的保守後備。
# 版面模板：glyph(1)＋空格(1)＋state_col＋空格(1)＋name_col＋空格(1)＋trailer，
# 欄間距由模板的固定空格保證，永遠可分辨。
_STATE_COL_MIN = 6
_STATE_COL_MAX = 20
_NAME_COL_MIN = 12
_TRAILER_RESERVE = 16
_JOBS_WIDTH_FALLBACK = 88


# 頂層無子列沒有 Tree 箭頭，首段補兩格與「▶ •」的列對齊（#311：三種列的
# •／state／name／trailer 四欄同 x 起點；phase 子列吃 guide 縮排 2，天然對齊）。
_ROW_ALIGN_PREFIX = "  "


def _layout_columns(
    groups: tuple[JobGroup, ...], width: int
) -> tuple[int, int, int]:
    """量本批 rows 的自然欄寬 → (state_col, name_col, trailer_budget)。

    寬面板：兩欄拿剛好夠用的，全名不省略、剩餘全給 trailer；窄面板：name
    先讓步到 _NAME_COL_MIN，再輪到 trailer 的退讓語意——省略號是最後手段。
    """
    state_widths = [_STATE_COL_MIN]
    name_widths = [0]
    for group in groups:
        state_widths.append(_display_width(_abbrev_label(group.headline_state)))
        if group.is_single:
            # name 欄只放單列的 phase 名；群組列 name 留白、branch 走 trailer
            # 與單列同欄對齊（#314）。
            name_widths.append(
                _display_width(_abbrev_branch(_abbrev_label(group.display_name)))
            )
        else:
            for row in group.rows:
                state_widths.append(
                    _display_width(_abbrev_label(row.human_state or row.state))
                )
    state_col = min(max(state_widths), _STATE_COL_MAX)
    # 起點統一 +2：群組列的 Tree 展開箭頭吃 2 欄，無子列由 _ROW_ALIGN_PREFIX
    # 補齊——可用寬因此再 -2（#311）。
    avail = width - state_col - 6
    max_name = max(name_widths)
    name_col = min(max_name, max(_NAME_COL_MIN, avail - _TRAILER_RESERVE))
    name_col = max(min(name_col, avail), 1)
    trailer_budget = max(avail - name_col, 0)
    return state_col, name_col, trailer_budget


# #322 三軸行的固定欄寬：phase 與 persona 用定寬，work_id 吃剩餘的彈性欄。
_PHASE_COL = 8  # build／verify／claim／review…
_PERSONA_COL = 9  # manager／planner／builder／reviewer
_WORK_COL_MIN = 16  # work_id／任務名至少留出可辨識的寬度
# 與 app.py 的軸歸屬標記同步（缺值退回）。
_UNPROJECTED = "未歸屬"  # 無 repo
_UNASSIGNED = "未派工"  # 無 persona
_UNCATEGORIZED = "未分類"  # 無 phase


def _row_work_id(row: JobRow) -> str:
    """工作識別欄：workflow_run 帶 work_id，legacy slice 退回看得懂的 display_name。"""
    return row.work_id or row.display_name


def _row_is_axis(row: JobRow) -> bool:
    """是否「真正的三軸行」：workflow_run 才帶 phase／work_id／persona。

    legacy slice 只用 slice_id 字串猜 phase，沿用舊的 state／name／trailer 渲染
    （#322）。這道門檻是兩種版面並存的分界線。"""
    return bool(row.work_id and row.phase)


def _col1_text(row: JobRow, axis: str) -> str:
    """三軸行第 1 欄：stage 軸顯示 work_id，project／agent 軸顯示 phase。

    能進這道門檻的 row 一定帶 phase（`_row_is_axis` 的條件），故 phase 永不為空。"""
    if axis == "stage":
        return _row_work_id(row)
    return row.phase


def _col2_text(row: JobRow, axis: str) -> str:
    """三軸行第 2 欄：stage 軸顯示 persona（work_id 已佔第 1 欄），其餘軸顯示
    work_id。三軸每欄依 plan「第 2 層列」定：project→phase·work_id·persona、
    stage→work_id·persona·repo、agent→phase·work_id·repo。（#322 回归：stage
    軸原把 work_id 重複在第 1、2 欄，且整列缺 persona）"""
    if axis == "stage":
        return row.persona or _UNASSIGNED
    return _row_work_id(row)


def _col3_text(row: JobRow, axis: str) -> str:
    """三軸行第 3 欄：project 軸顯示 persona，stage／agent 軸顯示 project（退未歸屬）。"""
    if axis == "project":
        return row.persona or _UNASSIGNED
    return row.project or _UNPROJECTED


def _axis_layout_columns(
    groups: tuple[JobGroup, ...], width: int, axis: str
) -> tuple[int, int, int]:
    """量本批三軸行的自然欄寬 → (first_col, work_col, third_col)。

    第 1、3 欄依本批最寬者取寬（設上下限），work_id 吃掉剩餘全部預算；寬度不足
    時先保 work_id（辨識關鍵），再壓縮第 1、3 欄。（#322）"""
    firsts: list[int] = []
    thirds: list[int] = []
    for group in groups:
        for row in group.rows:
            if _row_is_axis(row):
                firsts.append(_display_width(_col1_text(row, axis)))
                thirds.append(_display_width(_col3_text(row, axis)))
    first_col = min(max(firsts, default=_PHASE_COL), 14)
    first_col = max(first_col, _PHASE_COL)
    third_col = min(max(thirds, default=_PERSONA_COL), 16)
    third_col = max(third_col, _PERSONA_COL)
    work_col = max(width - 1 - 1 - first_col - 1 - third_col - 1, _WORK_COL_MIN)
    return first_col, work_col, third_col


def _render_axis_row(
    row: JobRow, first_col: int, work_col: int, third_col: int, axis: str
) -> tuple[tuple[str, str], ...]:
    """三軸行的四欄語意化版面：`glyph(1) phase(8) work_id(彈性) persona(9)`。

    glyph 承載狀態語意（顏色），phase／work_id／persona 皆中性色——狀態不用文字
    展現，寬度不足時由 _pad_display 把 work_id 推到最右、省略號由 _ellipsize 處理
    （#317：trailer 維持終端預設前景）。"""
    glyph, color = status_style(_row_state_key(row))
    c1 = _pad_display(_ellipsize_middle(_col1_text(row, axis), first_col), first_col)
    c2 = _pad_display(_ellipsize_middle(_col2_text(row, axis), work_col), work_col)
    c3 = _pad_display(_ellipsize_middle(_col3_text(row, axis), third_col), third_col)
    return (
        (f"{glyph} ", color),
        (f"{c1} ", ""),
        (f"{c2} ", ""),
        (f"{c3} ", ""),
    )


@dataclass(frozen=True)
class JobsNodeSpec:
    """build_jobs_nodes 的純資料輸出：一個 Tree 節點該長什麼樣，不碰 widget。"""

    key: str
    segments: tuple[tuple[str, str], ...]
    children: tuple["JobsNodeSpec", ...] = ()
    expand: bool = False


def _group_state_key(group: JobGroup) -> str:
    """多 phase 群組的上色依據：有人在等就照 attention 上色，否則跟著領頭 slice。"""
    return "attention" if group.needs_human else group.lead.state


def _row_state_key(row: JobRow) -> str:
    """單一 slice 的上色依據：needs_human 一律當 attention，不管上游原始 state 字串是什麼。"""
    return "needs_human" if row.needs_human else row.state


def _detail_child(key: str, detail: str) -> JobsNodeSpec:
    # 黃色 ↳ detail：detail_line 含可複製命令，這裡不截斷，超寬交給 Tree 的橫向捲動。
    return JobsNodeSpec(key=key, segments=((f"↳ {detail}", "#FBBF24"),))


def _single_detail_children(group: JobGroup) -> tuple[JobsNodeSpec, ...]:
    if group.needs_human and group.detail_line:
        return (_detail_child(f"{group.key}/detail", group.detail_line),)
    return ()


def _legacy_phase_child(group: JobGroup, row: JobRow, state_col: int) -> tuple[tuple[str, str], ...]:
    """legacy slice 行（無 phase／work_id）的舊兩欄渲染：`glyph+state · phase_name`。

    保留原有字面：`_phase_label` 從 slice_id 字剝出 phase 短名（`wf-abc-build`
    → `build`），legacy 測試斷言「顯示 build 但不顯示完整 slice_id」靠它。（#322）"""
    glyph, color = status_style(_row_state_key(row))
    label_state = _abbrev_label(row.human_state or row.state)
    phase_name = _abbrev_label(group._phase_label(row))
    return (
        (f"{glyph} {_pad_display(label_state, state_col)} ", color),
        (phase_name, ""),
    )


def _row_child(
    group: JobGroup,
    row: JobRow,
    first_col: int,
    work_col: int,
    third_col: int,
    state_col: int,
    axis: str,
) -> JobsNodeSpec:
    """一行工作的 Tree 子節點：三軸行走四欄語意化，legacy 行走舊兩欄。

    detail 子行一律預設收合（enter/space 才展開），`_single_detail_children`
    的單列 detail 不在這裡（群組層已處理）——這裡只有多 phase 群的分 phase 行。"""
    if _row_is_axis(row):
        segments = _render_axis_row(row, first_col, work_col, third_col, axis)
    else:
        segments = _legacy_phase_child(group, row, state_col)
    children: tuple[JobsNodeSpec, ...] = ()
    if row.needs_human and row.detail_line:
        children = (_detail_child(f"{group.key}/{row.slice_id}/detail", row.detail_line),)
    return JobsNodeSpec(
        key=f"{group.key}/{row.slice_id}",
        segments=segments,
        children=children,
        # detail 一律預設收合（#322：42 筆 needs_human 全展開會把 10 行區吃光），
        # 游標停在該列按 enter/space 才展開（Tree 原生行為）。
        expand=False,
    )


def build_jobs_nodes(
    groups: tuple[JobGroup, ...],
    width: int = _JOBS_WIDTH_FALLBACK,
    axis: str = "project",
) -> tuple[JobsNodeSpec, ...]:
    """JobGroup 序列 → Tree 節點描述（純函式，不碰 widget，供單測與 widget 共用）。

    `axis`（`project`／`stage`／`agent`）決定三軸分組的版面：workflow_run 行（帶
    phase／work_id／persona）走四欄語意化，legacy slice 行沿用舊的 state／name／
    trailer。群組頭對三軸行顯示「軸身分（group.key）＋計數副標」；legacy 群組
    保留既有 headline_state／trailer。預設 `project` 軸（既有測試相容）。"""
    # 欄寬對整批 rows 計算一次（與舊版同：一次 layout 供全部群組共用）。
    first_col, work_col, third_col = _axis_layout_columns(groups, width, axis)
    state_col, name_col, trailer_budget = _layout_columns(groups, width)
    specs: list[JobsNodeSpec] = []
    for group in groups:
        specs.append(
            _group_spec(group, axis, first_col, work_col, third_col, state_col, name_col, trailer_budget)
        )
    return tuple(specs)


def _group_spec(
    group: JobGroup,
    axis: str,
    first_col: int,
    work_col: int,
    third_col: int,
    state_col: int,
    name_col: int,
    trailer_budget: int,
) -> JobsNodeSpec:
    """群組節點：單列直接當行顯示，多列走軸身分頭＋分 phase 行。"""
    if group.is_single:
        return _single_group_spec(
            group, axis, first_col, work_col, third_col, state_col, name_col, trailer_budget
        )
    return _multi_group_spec(
        group, axis, first_col, work_col, third_col, state_col, name_col, trailer_budget
    )


def _single_group_spec(
    group: JobGroup,
    axis: str,
    first_col: int,
    work_col: int,
    third_col: int,
    state_col: int,
    name_col: int,
    trailer_budget: int,
) -> JobsNodeSpec:
    """單列群：群組節點直接當一行（三軸行四欄、legacy 行舊版），detail 掛群組層。"""
    row = group.lead
    children = _single_detail_children(group)
    align = _ROW_ALIGN_PREFIX if not children else ""
    if _row_is_axis(row):
        # 三軸行不含 align，這裡補上（無子列補兩格與 Tree 箭頭同寬起點）。
        segments = list(_render_axis_row(row, first_col, work_col, third_col, axis))
        first_text, first_color = segments[0]
        segments = ((f"{align}{first_text}", first_color), *segments[1:])
    else:
        glyph, color = status_style(group.lead.state)
        trailer = _fit_trailer(
            (
                group.project,
                _abbrev_branch(group.branch) or group.workflow_id,
                group.note,
                _abbrev_label(group.raw_state),
            ),
            trailer_budget,
        )
        # legacy 頭已把 align 寫進首段，這裡不再重複補。
        segments = (
            (f"{align}{glyph} {_pad_display(_abbrev_label(group.headline_state), state_col)} ", color),
            (
                f"{_pad_display(_ellipsize_middle(_abbrev_branch(_abbrev_label(group.display_name)), name_col) if group.is_single else '', name_col)} ",
                "",
            ),
            (trailer, ""),
        )
    all_recent_done = bool(group.rows) and all(
        row.source_section == "recent_done" for row in group.rows
    )
    return JobsNodeSpec(
        key=group.key,
        segments=segments,
        children=children,
        # 整群都是 recent_done 時不展開（#322）；其餘（含 needs_human 單列的
        # reason）預設展開，讓工作列與其可執行下一步一眼可見。
        expand=not all_recent_done,
    )


def _multi_group_spec(
    group: JobGroup,
    axis: str,
    first_col: int,
    work_col: int,
    third_col: int,
    state_col: int,
    name_col: int,
    trailer_budget: int,
) -> JobsNodeSpec:
    """多列群：三軸行顯示「軸身分＋計数」頭＋分 phase 行；legacy 群保留舊版。"""
    has_axis_rows = any(_row_is_axis(row) for row in group.rows)
    glyph, color = status_style(_group_state_key(group))
    trailer = _fit_trailer(
        (
            group.project,
            _abbrev_branch(group.branch) or group.workflow_id,
            group.note,
            _abbrev_label(group.raw_state),
        ),
        trailer_budget,
    )
    if has_axis_rows:
        # 三軸頭：glyph + 軸身分（group.key：repo／phase／persona）+ 計数副標。
        main_segments = ((f"{glyph} {_abbrev_label(group.key)} ", color), (group.summary_trailer, ""))
    else:
        # legacy 頭：headline_state＋留白 name 欄＋trailer（#314 多列 name 留白）。
        # 多列群永遠有子列（分 phase 行），Tree 箭頭吃掉同寬起點，故不加 align 前綴。
        main_segments = (
            (f"{glyph} {_pad_display(_abbrev_label(group.headline_state), state_col)} ", color),
            (f"{_pad_display('', name_col)} ", ""),
            (trailer, ""),
        )
    # 分 phase 行：三軸行四欄、legacy 行舊兩欄，detail 一律預設收合。
    children = tuple(
        _row_child(group, row, first_col, work_col, third_col, state_col, axis)
        for row in group.rows
    )
    all_recent_done = bool(group.rows) and all(
        row.source_section == "recent_done" for row in group.rows
    )
    return JobsNodeSpec(
        key=group.key,
        segments=main_segments,
        children=children,
        # 群組層預設展開（讓工作列可見）；整群都是 recent_done 時不展開（#322）。
        expand=not all_recent_done,
    )


def _project_specs(specs: tuple[JobsNodeSpec, ...]) -> tuple[tuple[str, str], ...]:
    """純文字投影（忽略顏色／expand）：去閃爍重建判斷用的 diff key。"""
    flat: list[tuple[str, str]] = []

    def walk(items: tuple[JobsNodeSpec, ...]) -> None:
        for spec in items:
            flat.append((spec.key, "".join(text for text, _ in spec.segments)))
            walk(spec.children)

    walk(specs)
    return tuple(flat)


if _HAS_TEXTUAL:

    def _label(segments: tuple[tuple[str, str], ...]):
        # Tree.process_label 吃 rich Text；textual 本身硬依賴 rich，這裡不必像
        # app.py 的 _text 那樣 fail-soft（此分支已確定在有 textual 的環境）。
        from rich.text import Text

        text = Text()
        for value, style in segments:
            text.append(value, style=style or "")
        return text

    class JobsPanel(Tree):
        """JOBS 面板：全部鍵盤／滑鼠互動走 Tree 原生（enter/space toggle、方向鍵、
        滾輪、點擊箭頭），這裡只管資料 → 節點的重建，以及重建之間要保留的東西：
        使用者手動展開/收合、cursor 所在 node、scroll 位置。
        """

        def __init__(
            self,
            *,
            name: str | None = None,
            id: str | None = None,
            classes: str | None = None,
            disabled: bool = False,
        ) -> None:
            super().__init__("jobs", name=name, id=id, classes=classes, disabled=disabled)
            self.show_root = False
            self.guide_depth = 2
            # axis -> key -> 使用者上次手動設的展開狀態；軸切換後原軸的展開狀態照舊。
            self._user_expanded: dict[str, dict[str, bool]] = {}
            self._last_axis: str = "project"
            self._last_projection: tuple[tuple[str, str], ...] | None = None
            self._last_groups: tuple[JobGroup, ...] = ()

        # node.expand()/collapse()（space、enter 觸發 auto_expand、滑鼠點箭頭）
        # 一定會 post 這兩個 message；重建時我們改用 add(expand=...) 直接設
        # _expanded，不會走這條路徑，所以這裡收到的必然是使用者手動動作。
        def on_tree_node_expanded(self, event: "Tree.NodeExpanded") -> None:
            key = event.node.data
            if key is not None:
                self._user_expanded.setdefault(self._last_axis, {})[key] = True

        def on_tree_node_collapsed(self, event: "Tree.NodeCollapsed") -> None:
            key = event.node.data
            if key is not None:
                self._user_expanded.setdefault(self._last_axis, {})[key] = False

        def _panel_width(self) -> int:
            """widget 目前可寫入的顯示寬度；量不到（尚未 layout）時退回保守值。"""
            try:
                width = int(self.size.width) - 2
            except (TypeError, ValueError, AttributeError):
                return _JOBS_WIDTH_FALLBACK
            return width if width > 40 else _JOBS_WIDTH_FALLBACK

        def on_resize(self, event: object) -> None:
            # resize 立即以新寬度重排，不等下一個 status tick（#308）；寬度沒
            # 實質改變時投影 diff 會判「沒變」而跳過重建，這裡不必自己防抖。
            if self._last_groups:
                self.set_groups(self._last_groups, axis=self._last_axis)

        def set_groups(self, groups: tuple[JobGroup, ...], axis: str = "project") -> None:
            self._last_groups = tuple(groups)
            self._last_axis = axis
            specs = build_jobs_nodes(tuple(groups), width=self._panel_width(), axis=axis)
            projection = _project_specs(specs)
            if projection == self._last_projection:
                return

            cursor_key = self.cursor_node.data if self.cursor_node is not None else None
            scroll_offset = self.scroll_offset
            restored: list[object] = [None]
            axis_store = self._user_expanded.setdefault(axis, {})

            def build(parent, spec: JobsNodeSpec) -> None:
                label = _label(spec.segments)
                if spec.children:
                    expand = axis_store.get(spec.key, spec.expand)
                    node = parent.add(label, data=spec.key, expand=expand)
                    for child in spec.children:
                        build(node, child)
                else:
                    node = parent.add_leaf(label, data=spec.key)
                if spec.key == cursor_key:
                    restored[0] = node

            self.clear()
            self._last_projection = projection
            for spec in specs:
                build(self.root, spec)

            # node._line 要等 Tree 真的跑過一次 _build()（render 或存取 _tree_lines
            # 才會觸發）才有正確值；剛 add() 完就呼叫 select_node 會撿到 stale -1，
            # 被 cursor_line 的 validator clamp 成 0，選到錯的列。延到下一次 refresh
            # 之後再選，這時 _tree_lines 已經重建過。
            self.call_after_refresh(self._restore_selection, restored[0], scroll_offset)

        def _restore_selection(self, node, offset) -> None:
            if node is not None:
                self.select_node(node)
            try:
                target_x = min(max(offset.x, 0), self.max_scroll_x)
                target_y = min(max(offset.y, 0), self.max_scroll_y)
            except Exception:
                return
            self.scroll_to(x=target_x, y=target_y, animate=False)

        def clear(self):
            # 外部（收合分支）直呼 clear() 時投影快取必須一併失效，否則展開後
            # 同一份 groups 會被 diff 判「沒變」而跳過重建，Tree 停留在空白。
            self._last_projection = None
            return super().clear()

        def set_message(self, text: str, style: str = "#64748B") -> None:
            """清空並顯示單一 leaf 訊息（degraded／0 slices 用）。"""
            projection = (("__message__", text),)
            if projection == self._last_projection:
                return
            self.clear()
            self._last_projection = projection
            self.root.add_leaf(_label(((text, style),)), data="__message__")

else:  # pragma: no cover - fallback when textual not installed

    class JobsPanel:  # type: ignore[no-redef]
        """textual 缺席時的退化 stub：純 noop，讓 import 不炸。"""

        def __init__(self, *args, **kwargs) -> None:
            self.border_title = ""
            self.border_subtitle = ""

        def set_groups(self, groups, axis: str = "project") -> None:  # pragma: no cover - noop
            return None

        def set_message(self, text: str, style: str = "#64748B") -> None:  # pragma: no cover - noop
            return None

        def clear(self) -> None:  # pragma: no cover - noop
            return None
