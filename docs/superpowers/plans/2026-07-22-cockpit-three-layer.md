# Cockpit 三層直排 + 雙擊 swap + 自動歸位 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cockpit 移除 DETAIL window 改三層直排（banner/WORK/JOBS），WORK 支援滑鼠雙擊 swap，加 restore-before-swap 自動歸位與 JOBS `j` 收合。

**Architecture:** 全部改動集中在 `paulshaclaw/cockpit/`。preview 鏈連根拔（models/tmux/app/`__main__`）；`WorkListView(ListView)` 覆寫 `action_select_cursor` 使 `ListView.Selected` 成純滑鼠訊號；app 層手動計時雙擊偵測；`_displacement` 單槽 + `_activate` 演算法（終點 A/B/C/D）。權威設計：`docs/superpowers/specs/2026-07-22-cockpit-three-layer-doubleclick-design.md`（v8，codex 8 輪 PASS）；需求：`openspec/changes/cockpit-three-layer/specs/stage11-operator-cockpit/spec.md`。

**Tech Stack:** Python 3.12、textual 0.61.1（**不升版**）、unittest（`.venv/bin/python -m unittest`）、tmux 3.4。

## Global Constraints

- textual 釘在 0.61.1；只用 0.61 已支援的 tcss 屬性（`max-height`/`min-height`/`overflow-y` 皆可）
- **直譯器一律用 repo 的 `.venv/bin/python`**（裸 `python3` 無 `paulsha_cortex`，已實測 ModuleNotFoundError）；測試從 repo root 跑 `.venv/bin/python -m unittest ...`，冒煙跑 `PYTHONPATH=. .venv/bin/python -m paulshaclaw.cockpit ...`
- app.py 的 textual import 有 try/except stub fallback——所有新類別定義在 app.py 的 import 區塊之後，沿用現有 stub 模式，**不得**讓無 textual 環境 import 失敗
- 雙擊閾值 0.4s；tcss 數字：`#work-list` `1fr`+`min-height: 5`、`#global-jobs` `height: auto`+`max-height: 12`+`overflow-y: auto`、收合 `max_height=3`
- 註解/文件 zh-TW；commit 訊息 conventional（`feat(cockpit):`/`test(cockpit):`/`refactor(cockpit):`）
- **WORK 候選只列 cockpit session**（#249 已出貨行為，delta spec req 5 已 truth-up）——`store.py` 的 `candidate_section` 過濾**不是 bug、不得「修復」成跨 session**；他 session panes 只入枚舉與 banner 統計
- 分支：`feature/cockpit-three-layer`（已在其上）
- 每個 Task 結束時全測試套件必須綠燈：`.venv/bin/python -m unittest discover -s tests -v 2>&1 | tail -5`

---

### Task 1: preview 鏈連根拔（models / tmux / `__main__` / app 非 UI 部分）

**Files:**
- Modify: `paulshaclaw/cockpit/models.py`（刪 `preview` 欄位、刪 `PaneDetail`）
- Modify: `paulshaclaw/cockpit/tmux.py`（刪 `capture_preview`、`capture_previews` 分流）
- Modify: `paulshaclaw/cockpit/__main__.py`（刪 `preview_loader` 接線）
- Modify: `paulshaclaw/cockpit/app.py`（刪 `preview_loader` 參數、`_selected_preview`、`_loader_accepts_capture_previews`、`_reconcile_state` 的 `light` 分流）
- Modify: `tests/test_stage11_operator_cockpit.py`（helper 與既有測試修正）

**Interfaces:**
- Consumes: 現有 `PaneRecord`、`TmuxClient.list_panes`
- Produces: `TmuxClient.list_panes(*, cockpit_pane_id: str) -> tuple[PaneRecord, ...]`（無 `capture_previews` 參數）；`PaneRecord` 無 `preview` 欄位；`CockpitApp.__init__`/`from_snapshot` 無 `preview_loader` 參數；`CockpitApp._reconcile_state()` 無 `light` 參數

- [ ] **Step 1: models.py 刪 preview 欄位與 PaneDetail**

`paulshaclaw/cockpit/models.py`：刪 `PaneRecord` 的 `preview: tuple[str, ...]` 欄位（第 26 行）；整段刪除 `PaneDetail` dataclass（第 68-72 行，repo 內零使用，已 grep 確認）。

- [ ] **Step 2: tmux.py 簡化**

`paulshaclaw/cockpit/tmux.py`：
1. 檔頭 import 加 `from dataclasses import replace`
2. `parse_list_panes` 中 `PaneRecord(...)` 建構刪去 `preview=(),` 一行
3. `TmuxClient.list_panes` 整個方法替換為：

```python
    def list_panes(self, *, cockpit_pane_id: str) -> tuple[PaneRecord, ...]:
        """List panes with a readable summary per pane.

        三層版面後 refresh 恆為一次 ``list-panes``（外加 title 缺失 minicom pane
        的小 ``ps``）；cockpit 不再抓任何 pane preview。``cockpit_pane_id`` 保留
        為 loader 契約參數（呼叫端以 keyword 傳入）。"""
        try:
            completed = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", LIST_PANES_FORMAT],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ()
        panes = parse_list_panes(completed.stdout)
        return tuple(replace(pane, summary=derive_summary(pane)) for pane in panes)
```

4. 整個刪除 `capture_preview` 方法

- [ ] **Step 3: `__main__.py` 刪接線**

刪 `preview_loader=tmux_client.capture_preview,` 一行（`__main__.py:42`）。

- [ ] **Step 4: app.py 非 UI 部分**

1. `__init__` 與 `from_snapshot`：刪 `preview_loader` 參數與 `self.preview_loader = preview_loader`
2. 整個刪除 `_selected_preview`（`app.py:624-630`）與 `_loader_accepts_capture_previews`（`app.py:615-621`）
3. `_reconcile_state` 替換為（並更新三個呼叫點 `_on_refresh_tick`／`_on_help_closed`／`_after_manager_tick` 刪去 `light=True`）：

```python
    def _reconcile_state(self) -> None:
        if self.pane_loader is None:
            return
        # 三層版面後 refresh 恆為單次 list-panes（無 preview 重載、無分流）。
        panes = self.pane_loader(cockpit_pane_id=self.state.cockpit_pane_id)
        self.state = self.state.refresh(panes)
        try:
            self._refresh_widgets()
        except Exception:
            pass
```

注意：`_refresh_widgets` 中對 `self._selected_preview(selected)` 的呼叫（detail 渲染段內）留待 Task 2 隨整段刪除；本 Task 先以 `for line in ():` 佔位會破壞 minimal diff——正確作法是本 Task 直接把該迴圈兩行刪掉（`for line in self._selected_preview(selected): segs.append(...)`）。

- [ ] **Step 5: 既有測試修正**

`tests/test_stage11_operator_cockpit.py`：
1. `pane_record` helper（:52-86）：刪 `preview` 參數與 `preview=preview,`
2. 全檔清除殘餘 `preview=` 實參：`grep -n "preview" tests/test_stage11_operator_cockpit.py` 逐筆處理——`preview=(),`、`preview=("active",),`、`preview=("job 1",),`、`preview=("traffic",),` 等實參直接刪除
3. `test_light_refresh_reloads_panes_without_previews`（:425-435）整個替換為：

```python
    def test_refresh_reloads_panes_with_single_loader_call(self) -> None:
        seen: dict[str, object] = {}

        def loader(*, cockpit_pane_id: str):
            seen["cockpit_pane_id"] = cockpit_pane_id
            return (pane_record("%0", active=True),)

        app = CockpitApp.from_snapshot(
            panes=(pane_record("%0", active=True),),
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=Mock(),
            pane_loader=loader,
        )
        app._reconcile_state()
        self.assertEqual(seen["cockpit_pane_id"], "%0")
```

4. `test_down_updates_selected_preview_target`（:1070 起）：改名 `test_down_updates_selected_pane` 並把對 preview 內容的斷言改為對 `state.selected_pane.pane_id` 的斷言（保留按鍵行為驗證，刪 preview 斷言行）
5. 其餘 `preview_loader=` 實參（若 grep 到）直接刪除
6. **`tests/test_stage11_operator_cockpit_e2e.py`** 的 fixture helper（:24、:37）：刪 `preview: tuple[str, ...] = (),` 參數與 `preview=preview,` 一行；該檔其他 `preview=` 實參一併刪
7. **`tests/test_cockpit_redesign.py:27-28`** 的 positional 建構——刪去最後一個 positional `()`（原 preview 位）：

```python
def pane(pid, *, session="main", window="0", title="pane", command="bash",
         left=0, top=0, width=80, height=24):
    return PaneRecord(pid, session, window, title, command, left, top, width,
                      height, False)
```

8. 收尾驗證：`grep -rn "preview" tests/ --include="*.py"` 清到零命中

- [ ] **Step 6: 跑套件（預期 Task 2 前仍有 detail 相關殘紅則於此修）**

Run: `.venv/bin/python -m unittest tests.test_stage11_operator_cockpit -v 2>&1 | tail -8`
Expected: 若有殘餘 failure 全部源自本 Task 遺漏的 preview 引用——回頭清乾淨至綠燈。

- [ ] **Step 7: Commit**

```bash
git add paulshaclaw/cockpit/ tests/test_stage11_operator_cockpit.py
git commit -m "refactor(cockpit): preview 鏈連根拔——refresh 恆為單次 list-panes"
```

---

### Task 2: 三層直排版面 + tcss + 刪 detail 渲染段

**Files:**
- Modify: `paulshaclaw/cockpit/app.py`（compose、`_refresh_widgets`）
- Modify: `paulshaclaw/cockpit/cockpit.tcss`
- Create: `tests/test_cockpit_three_layer.py`
- Modify: `tests/test_stage11_operator_cockpit.py`（`#pane-detail` mock 引用清除）

**Interfaces:**
- Consumes: Task 1 的簡化 `_reconcile_state`
- Produces: 三層 widget 樹（`#brand-banner` → `#work-list` → `#global-jobs`）；測試共用 helpers `pane_record`／`FakeActions`／`make_app`（本檔定義，後續 Task 沿用）

- [ ] **Step 1: 新測試檔骨架＋失敗的版面測試**

Create `tests/test_cockpit_three_layer.py`：

```python
"""cockpit-three-layer 變更的行為測試（版面／雙擊／歸位／JOBS 收合）。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

try:
    from textual.app import App as _TextualApp
    from textual.widgets import ListView
    HAS_TEXTUAL = hasattr(_TextualApp, "run_test")
except Exception:
    ListView = None  # type: ignore
    HAS_TEXTUAL = False

from paulshaclaw.cockpit.app import CockpitApp
from paulshaclaw.cockpit.models import PaneRecord


def pane_record(pane_id, *, session_name="main", window_index="0", title="pane",
                command="bash", left=0, top=0, width=80, height=24, active=False,
                summary=""):
    return PaneRecord(
        pane_id=pane_id, session_name=session_name, window_index=window_index,
        title=title, command=command, left=left, top=top, width=width,
        height=height, active=active, summary=summary,
    )


class FakeActions:
    """錄呼叫序的 layout actions；fail_first_swap=True 時「生涯第一次」swap 拋錯。

    生涯計數用獨立 _swap_count——測試中 calls.clear() 只清錄音、不重置失敗
    計數，確保「restore 失敗後重試」情境的第二次 swap 是乾淨成功路徑。"""

    def __init__(self, fail_first_swap=False, fail_all_swaps=False):
        self.calls = []
        self._swap_count = 0
        self.fail_first_swap = fail_first_swap
        self.fail_all_swaps = fail_all_swaps

    def swap_selected_with_active(self, *, selected_pane_id, active_pane_id):
        self.calls.append(("swap", selected_pane_id, active_pane_id))
        self._swap_count += 1
        if self.fail_all_swaps or (self.fail_first_swap and self._swap_count == 1):
            raise RuntimeError("tmux swap failed (fake)")

    def focus_pane(self, pane_id):
        self.calls.append(("focus", pane_id))

    def return_to_cockpit(self, cockpit_pane_id):
        self.calls.append(("focus", cockpit_pane_id))

    def swaps(self):
        return [c for c in self.calls if c[0] == "swap"]


DEFAULT_PANES = (
    pane_record("%0", title="cockpit", active=True),
    pane_record("%1", title="slot", left=81, width=119, height=50),
    pane_record("%2", title="agent", top=25, height=12),
    pane_record("%3", title="pytest", top=38, height=12),
)


def make_app(actions=None, panes=DEFAULT_PANES, **extra):
    return CockpitApp.from_snapshot(
        panes=panes,
        cockpit_pane_id="%0",
        cockpit_session_name="main",
        jobs_by_pane={},
        actions=actions if actions is not None else FakeActions(),
        pane_loader=lambda *, cockpit_pane_id: panes,
        **extra,
    )


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class ThreeLayerLayoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_layer_order_and_no_detail(self):
        app = make_app()
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            self.assertFalse(list(app.query("#pane-detail")))
            banner = app.query_one("#brand-banner")
            work = app.query_one("#work-list")
            jobs = app.query_one("#global-jobs")
            self.assertLess(banner.region.y, work.region.y)
            self.assertLess(work.region.y, jobs.region.y)

    async def test_small_terminal_keeps_work_min_height(self):
        app = make_app()
        async with app.run_test(size=(80, 15)) as pilot:
            await pilot.pause()
            work = app.query_one("#work-list")
            self.assertGreaterEqual(work.region.height, 5)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer -v 2>&1 | tail -5`
Expected: FAIL（`#pane-detail` 仍存在／版面仍左右欄）

- [ ] **Step 3: app.py compose 改三層＋刪 detail 渲染段**

1. `compose()` 替換為：

```python
    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="brand-banner")  # 破蝦哥 🦞 banner（issue #116）；內容於 on_mount 填入
        yield ListView(id="work-list")
        yield Static("", id="global-jobs")
        yield Footer()
```

2. 從 textual import 行與 stub 區刪 `Horizontal`／`Vertical`（`from textual.containers import ...` 整行刪；stub 的 `_Container`／`Horizontal = Vertical = _Container` 刪）
3. `_refresh_widgets`：整段刪除 detail 渲染（自 `selected = self.state.selected_pane` 起、至 `detail_widget.update(detail_renderable)` 止，約 `app.py:714-750`）；`_state_segment` 若因此無使用者則一併刪除（grep 確認）
4. 刪 `#pane-detail` 相關 `_set_border` 呼叫（隨上段消失）

- [ ] **Step 4: cockpit.tcss 更新**

1. 刪 `#main-row`／`#left-pane`／`#right-pane`／`#pane-detail` 四個區塊（tcss :50-58、:73-80）
2. `#work-list` 加 `min-height: 5;`
3. `#global-jobs` 的 `max-height: 10;` 改 `max-height: 12;`，並加 `overflow-y: auto;`

- [ ] **Step 5: 既有測試的 `#pane-detail` 引用清除**

`tests/test_stage11_operator_cockpit.py`：
1. 三處 widgets mock dict（:411、:858、:882）刪 `"#pane-detail"` key
2. :417-418 對 `widgets["#pane-detail"].update` 的斷言改為 `widgets["#global-jobs"].update`（refresh 仍每輪更新 JOBS）
3. `grep -n "pane-detail\|pane_detail" tests/` 清到零命中

- [ ] **Step 6: 跑測試確認通過**

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer tests.test_stage11_operator_cockpit -v 2>&1 | tail -5`
Expected: PASS（全綠）

- [ ] **Step 7: Commit**

```bash
git add paulshaclaw/cockpit/app.py paulshaclaw/cockpit/cockpit.tcss tests/
git commit -m "feat(cockpit): 三層直排版面（banner/WORK/JOBS），移除 DETAIL"
```

---

### Task 3: WorkItem / WorkListView + Enter 單一權威

**Files:**
- Modify: `paulshaclaw/cockpit/app.py`
- Test: `tests/test_cockpit_three_layer.py`

**Interfaces:**
- Consumes: Task 2 的三層 compose
- Produces: `WorkItem(ListItem)`——建構參數 `pane_id: str | None`、屬性 `.pane_id`、列 id `row-<N>`（`pane_id.lstrip('%')`）；`WorkListView(ListView)`——覆寫 `action_select_cursor()`；`CockpitApp._work_row_pane_ids(active) -> tuple[str, ...]`；app 無 `on_key`

- [ ] **Step 1: 失敗測試——Enter 恰好一次 swap**

Append 到 `tests/test_cockpit_three_layer.py`：

```python
@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class EnterSingleAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_enter_triggers_exactly_one_swap(self):
        actions = FakeActions()
        app = make_app(actions=actions)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
        self.assertEqual(len(actions.swaps()), 1)
        self.assertEqual(actions.swaps()[0], ("swap", "%2", "%1"))
```

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer.EnterSingleAuthorityTests -v`
Expected: 現況可能 PASS（單發）或 FAIL——記錄現值作基準；本測試的目的是鎖住改造後仍恰好一次。

- [ ] **Step 2: 實作 WorkItem / WorkListView**

`app.py`，textual import／stub 區塊之後加：

```python
class WorkItem(ListItem):
    """工作清單列：附掛 pane_id 供雙擊偵測直讀（Selected.item.pane_id）。"""

    def __init__(self, *args, pane_id: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pane_id = pane_id


class WorkListView(ListView):
    """WORK 清單：enter 覆寫為直達 app swap action。

    覆寫公開 action ``action_select_cursor``（ListView 自身 enter binding 的
    action）→ 鍵盤路徑不再 post ``ListView.Selected``，``Selected`` 從此為純滑
    鼠訊號（design doc §3.1-§3.2；textual 0.61 原始碼佐證見該文件）。"""

    def action_select_cursor(self) -> None:
        app = getattr(self, "app", None)
        action = getattr(app, "action_swap_selected", None)
        if callable(action):
            action()
```

- [ ] **Step 3: 接線**

1. `compose()` 的 `yield ListView(id="work-list")` 改 `yield WorkListView(id="work-list")`
2. 加 helper（放 `_work_list_renderables` 旁）：

```python
    def _work_row_pane_ids(self, active: PaneRecord | None) -> tuple[str, ...]:
        """與 _work_row_segments 同順序的 pane_id 投影（ACTIVE 首列）。"""
        ids: list[str] = []
        if active is not None:
            ids.append(active.pane_id)
        ids.extend(pane.pane_id for pane in self.state.candidate_section)
        return tuple(ids)
```

3. `_refresh_widgets` 工作清單 rebuild 迴圈改為：

```python
            for renderable, pane_id in zip(
                self._work_list_renderables(active), self._work_row_pane_ids(active)
            ):
                work_list.append(
                    WorkItem(
                        Static(renderable),
                        pane_id=pane_id,
                        id=f"row-{pane_id.lstrip('%')}",
                    )
                )
```

4. `query_one("#work-list", ListView)` 三處（:310、:414、:704）維持不動——`WorkListView` 是 `ListView` subclass，查詢相容
5. **整個刪除 `on_key`**（`app.py:582-595`）；app 級 `BINDINGS` 的 `Binding("enter", "swap_selected", ...)` 保留（footer 顯示＋work-list 未 focus 時後援）

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer -v 2>&1 | tail -5`
Expected: PASS；另跑 `.venv/bin/python -m unittest tests.test_stage11_operator_cockpit -v 2>&1 | tail -5` 確認 Enter/swap 既有測試仍綠（若有直接呼叫 `app.on_key` 的舊測試，改為呼叫 `app.action_swap_selected()`）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/cockpit/app.py tests/
git commit -m "feat(cockpit): WorkListView 覆寫 select_cursor——Enter 單一權威、Selected 成純滑鼠訊號"
```

---

### Task 4: 雙擊偵測 + guards + 手勢中斷

**Files:**
- Modify: `paulshaclaw/cockpit/app.py`
- Test: `tests/test_cockpit_three_layer.py`

**Interfaces:**
- Consumes: Task 3 的 `WorkItem.pane_id`
- Produces: 模組常數 `DOUBLE_CLICK_SECONDS = 0.4`；`CockpitApp.__init__(..., clock: Callable[[], float] | None = None)`（`from_snapshot` 同步傳遞）；`self._clock`、`self._last_click: tuple[str, float] | None`；`on_list_view_selected(event)`；`action_swap_selected` 入口先 `self._last_click = None`

- [ ] **Step 1: 失敗測試（單測，注入 clock，不需 textual）**

Append：

```python
class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def selected_event(pane_id, list_id="work-list"):
    return SimpleNamespace(
        list_view=SimpleNamespace(id=list_id),
        item=SimpleNamespace(pane_id=pane_id),
    )


class DoubleClickTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.actions = FakeActions()
        self.app = make_app(actions=self.actions, clock=self.clock)

    def click(self, pane_id, list_id="work-list"):
        self.app.on_list_view_selected(selected_event(pane_id, list_id))

    def test_double_click_within_threshold_swaps_once(self):
        self.click("%2")
        self.clock.now += 0.2
        self.click("%2")
        self.assertEqual(self.actions.swaps(), [("swap", "%2", "%1")])

    def test_slow_second_click_does_not_swap(self):
        self.click("%2")
        self.clock.now += 0.5
        self.click("%2")
        self.assertEqual(self.actions.swaps(), [])
        self.assertEqual(self.app._last_click, ("%2", self.clock.now))

    def test_cross_row_does_not_swap_and_rerecords(self):
        self.click("%2")
        self.clock.now += 0.1
        self.click("%3")
        self.assertEqual(self.actions.swaps(), [])
        self.assertEqual(self.app._last_click[0], "%3")

    def test_active_row_click_interrupts_gesture(self):
        self.click("%2")
        self.clock.now += 0.1
        self.click("%1")  # ACTIVE 列
        self.clock.now += 0.1
        self.click("%2")  # 第三擊＝新首擊
        self.assertEqual(self.actions.swaps(), [])
        self.assertEqual(self.app._last_click[0], "%2")

    def test_double_click_on_active_row_is_noop(self):
        self.click("%1")
        self.clock.now += 0.1
        self.click("%1")
        self.assertEqual(self.actions.swaps(), [])
        self.assertIsNone(self.app._last_click)

    def test_item_without_pane_id_interrupts_gesture(self):
        self.click("%2")
        self.clock.now += 0.1
        self.click(None)
        self.assertIsNone(self.app._last_click)

    def test_non_work_list_event_does_not_touch_state(self):
        self.click("%2")
        self.clock.now += 0.1
        self.click("%2", list_id="other-list")  # 完全忽略
        self.clock.now += 0.1
        self.click("%2")  # 與首擊仍配對（WORK-local 語意）
        self.assertEqual(self.actions.swaps(), [("swap", "%2", "%1")])

    def test_triple_click_starts_new_cycle(self):
        self.click("%2")
        self.clock.now += 0.1
        self.click("%2")  # 觸發 swap、清空
        self.clock.now += 0.1
        self.click("%2")  # 新首擊
        self.assertEqual(len(self.actions.swaps()), 1)
        self.assertEqual(self.app._last_click[0], "%2")

    def test_mismatch_guard_downgrades_to_first_click(self):
        self.app.state = self.app.state.set_selection(1)  # 選 %3
        self.click("%2")
        self.clock.now += 0.1
        self.click("%2")
        self.assertEqual(self.actions.swaps(), [])
        self.assertEqual(self.app._last_click[0], "%2")

    def test_enter_swap_clears_pending_click(self):
        self.click("%2")
        self.clock.now += 0.1
        self.app.action_swap_selected()  # Enter 路徑
        n = len(self.actions.swaps())
        self.clock.now += 0.1
        self.click("%2")  # 不得與最初首擊配對
        self.assertEqual(len(self.actions.swaps()), n)

    def test_blocked_modal_prevents_swap(self):
        with patch.object(self.app, "_help_modal_open", return_value=True):
            self.click("%2")
            self.clock.now += 0.1
            self.click("%2")
        self.assertEqual(self.actions.swaps(), [])
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer.DoubleClickTests -v 2>&1 | tail -5`
Expected: FAIL（`clock` 參數不存在／`on_list_view_selected` 未實作）

- [ ] **Step 3: 實作**

`app.py`：
1. 檔頭 `import time`；模組層加 `DOUBLE_CLICK_SECONDS = 0.4`（放 `REFRESH_INTERVAL_SECONDS` 旁，附註解「雙擊判定窗；handler-time 取樣，design doc §3.2」）
2. `__init__` 簽名加 `clock: Callable[[], float] | None = None`，body 加：

```python
        # 雙擊偵測（design doc §3.2）：pane_id 為 key、可注入 clock 供測試。
        self._clock: Callable[[], float] = clock or time.monotonic
        self._last_click: tuple[str, float] | None = None
```

3. `from_snapshot` 簽名與轉傳同步加 `clock`
4. 新 handler（放 `on_list_view_highlighted` 之後）：

```python
    def on_list_view_selected(self, event: object) -> None:
        """純滑鼠訊號（WorkListView 已覆寫鍵盤路徑）→ 手動雙擊偵測。

        guards 與手勢中斷語意見 design doc §3.2。"""
        list_view = getattr(event, "list_view", None)
        if getattr(list_view, "id", None) != "work-list":
            return  # 非 work-list：不碰手勢狀態（現 UI 唯一 ListView，§7 不變量守護）
        pane_id = getattr(getattr(event, "item", None), "pane_id", None)
        active = self.state.active_pane
        if not pane_id or (active is not None and pane_id == active.pane_id):
            self._last_click = None  # 手勢中斷：配對點擊必須連續
            return
        now = self._clock()
        last = self._last_click
        if (
            last is not None
            and last[0] == pane_id
            and now - last[1] < DOUBLE_CLICK_SECONDS
        ):
            selected = self.state.selected_pane
            if selected is not None and selected.pane_id == pane_id:
                self.action_swap_selected()  # 入口即清 _last_click
                return
            # mismatch guard：選取與點擊目標不同步 → 降級為新首擊（fail-safe）
        self._last_click = (pane_id, now)
```

5. `action_swap_selected` 開頭（`_background_actions_blocked` 檢查之前）加 `self._last_click = None`
6. `action_show_help` 與 `action_manager_panel` 各加 `self._last_click = None`（modal 開啟＝手勢作廢）

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer -v 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/cockpit/app.py tests/test_cockpit_three_layer.py
git commit -m "feat(cockpit): WORK 雙擊 swap——0.4s/pane_id 手動計時＋guards＋手勢中斷"
```

---

### Task 5: Pilot 實鏈測試 + 唯一 ListView 不變量

**Files:**
- Test: `tests/test_cockpit_three_layer.py`

**Interfaces:**
- Consumes: Task 3 的列 id `row-<N>`、Task 4 的 `clock` 注入
- Produces: textual 升版守門測試（`Selected`-on-click 語意變即紅燈）

- [ ] **Step 1: 寫測試**

Append：

```python
@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class EventChainAndInvariantTests(unittest.IsolatedAsyncioTestCase):
    async def test_double_click_real_event_chain(self):
        clock = FakeClock()
        actions = FakeActions()
        app = make_app(actions=actions, clock=clock)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#row-2")
            clock.now += 0.1
            await pilot.click("#row-2")
            await pilot.pause()
        self.assertIn(("swap", "%2", "%1"), actions.calls)

    async def test_sole_listview_invariant_across_states(self):
        from textual.widgets import ListView as TextualListView

        app = make_app()
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            def assert_sole():
                # 0.61 的 app.query 只查 current screen——modal 開啟時要查
                # base screen（screen_stack[0]）驗唯一，並斷言 modal screen 零 ListView。
                base = app.screen_stack[0]
                views = list(base.query(TextualListView))
                self.assertEqual(len(views), 1)
                self.assertEqual(views[0].id, "work-list")
                for screen in app.screen_stack[1:]:
                    self.assertEqual(len(list(screen.query(TextualListView))), 0)

            assert_sole()                       # mount 後
            await pilot.press("question_mark")  # help 開
            await pilot.pause(); assert_sole()
            await pilot.press("escape")         # help 關
            await pilot.pause(); assert_sole()
            await pilot.press("m")              # manager 開
            await pilot.pause(); assert_sole()
            await pilot.press("escape")         # manager 關
            await pilot.pause(); assert_sole()
            app._on_refresh_tick()              # refresh 後
            assert_sole()
```

- [ ] **Step 2: 跑測試確認通過**

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer.EventChainAndInvariantTests -v 2>&1 | tail -5`
Expected: PASS（若 `pilot.click("#row-2")` 因列不可見失敗，先 `work_list.scroll_visible()`；若 manager modal 因讀不到 status 卡住，先 `app.manager_client = SimpleNamespace(read_status=lambda: {}, submit_request=lambda *a, **k: None)`）

- [ ] **Step 3: Commit**

```bash
git add tests/test_cockpit_three_layer.py
git commit -m "test(cockpit): 雙擊實鏈 Pilot 測試＋唯一 ListView 多檢查點不變量"
```

---

### Task 6: restore-before-swap（`_displacement` + `_activate` 終點 A/B/C/D）

**Files:**
- Modify: `paulshaclaw/cockpit/app.py`
- Test: `tests/test_cockpit_three_layer.py`

**Interfaces:**
- Consumes: `FakeActions`（fail 開關）、`LayoutActionService` 既有介面（**不動**）
- Produces: `self._displacement: tuple[str, str] | None`（(occupant, displaced)）；`CockpitApp._activate(target_pane_id: str, slot_pane_id: str) -> None`；`CockpitApp._notify_soft(message: str) -> None`；`action_swap_selected` 改走 `_activate`

- [ ] **Step 1: 失敗測試（fake actions 錄呼叫序）**

Append：

```python
class RestoreBeforeSwapTests(unittest.TestCase):
    def setUp(self):
        self.actions = FakeActions()
        self.app = make_app(actions=self.actions, clock=FakeClock())

    def test_plain_activate_sets_record(self):
        self.app._activate("%2", "%1")
        self.assertEqual(self.actions.calls, [("swap", "%2", "%1"), ("focus", "%2")])
        self.assertEqual(self.app._displacement, ("%2", "%1"))

    def test_second_activate_restores_first(self):
        self.app._activate("%2", "%1")
        self.actions.calls.clear()
        self.app._activate("%3", "%1")
        self.assertEqual(
            self.actions.calls,
            [("swap", "%1", "%2"), ("swap", "%3", "%1"), ("focus", "%3")],
        )
        self.assertEqual(self.app._displacement, ("%3", "%1"))

    def test_activating_displaced_completes_via_restore_only(self):
        self.app._displacement = ("%2", "%1")
        self.app._activate("%1", "%2")
        self.assertEqual(self.actions.calls, [("swap", "%1", "%2")])
        self.assertIsNone(self.app._displacement)

    def test_restore_failure_aborts_activation(self):
        self.app.notify = Mock()
        self.actions.fail_first_swap = True
        self.app._displacement = ("%2", "%1")
        self.app._activate("%3", "%1")
        self.assertEqual(len(self.actions.swaps()), 1)  # 只有 restore 嘗試
        self.assertIsNone(self.app._displacement)
        self.app.notify.assert_called()
        # 重試＝乾淨 plain swap
        self.actions.calls.clear()
        self.app._activate("%3", "%1")
        self.assertEqual(self.actions.swaps(), [("swap", "%3", "%1")])

    def test_restore_failure_with_displaced_target_also_aborts(self):
        self.actions.fail_first_swap = True
        self.app._displacement = ("%2", "%1")
        self.app._activate("%1", "%2")  # 組合分支：C == displaced ∧ restore 拋錯
        self.assertEqual(len(self.actions.swaps()), 1)
        self.assertIsNone(self.app._displacement)

    def test_missing_recorded_pane_drops_record_silently(self):
        self.app._displacement = ("%9", "%8")  # 不存在於快照
        self.app._activate("%2", "%1")
        self.assertEqual(self.actions.calls, [("swap", "%2", "%1"), ("focus", "%2")])
        self.assertEqual(self.app._displacement, ("%2", "%1"))

    def test_main_swap_failure_keeps_record_cleared(self):
        self.app.notify = Mock()
        self.actions.fail_all_swaps = True
        self.app._activate("%2", "%1")
        self.assertIsNone(self.app._displacement)
        self.app.notify.assert_called()

    def test_action_swap_selected_routes_through_activate(self):
        self.app.action_swap_selected()  # 預設選取 %2
        self.assertEqual(self.actions.swaps(), [("swap", "%2", "%1")])
        self.assertEqual(self.app._displacement, ("%2", "%1"))
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer.RestoreBeforeSwapTests -v 2>&1 | tail -5`
Expected: FAIL（`_activate` 不存在）

- [ ] **Step 3: 實作**

`app.py`：
1. `__init__` 加：

```python
        # restore-before-swap（design doc §4）：單槽 (occupant, displaced)，重啟歸零。
        self._displacement: tuple[str, str] | None = None
```

2. `action_swap_selected` 替換為：

```python
    def action_swap_selected(self) -> None:
        self._last_click = None  # 任何來源觸發 swap 一律先清雙擊手勢
        if self._background_actions_blocked():
            return
        active_pane = self.state.active_pane
        selected_pane = self.state.selected_pane
        if active_pane is None or selected_pane is None:
            return
        self._activate(selected_pane.pane_id, active_pane.pane_id)
```

3. 新增（放 `action_swap_selected` 之後）：

```python
    def _activate(self, target_pane_id: str, slot_pane_id: str) -> None:
        """activate(C)：restore-before-swap 前置＋主 swap（design doc §4.2 終點 A-D）。

        C 必屬 candidate_section（排除 active）⇒ C == occupant 不可能。
        序列化依據＝Textual 單執行緒事件迴圈＋同步 subprocess。"""
        proceed = True
        record = self._displacement
        if record is not None:
            occupant_id, displaced_id = record
            alive = {pane.pane_id for pane in self.state.panes}
            if occupant_id in alive and displaced_id in alive:
                try:
                    self.actions.swap_selected_with_active(
                        selected_pane_id=displaced_id, active_pane_id=occupant_id
                    )
                    self._displacement = None
                    if target_pane_id == displaced_id:
                        proceed = False  # 終點 A：restore 即完成（C 已回 slot）
                    else:
                        slot_pane_id = displaced_id  # slot 現由原住民佔回
                except Exception as exc:  # noqa: BLE001 — CalledProcessError 等一律 fail-soft
                    self._displacement = None
                    self._notify_soft(f"restore swap failed: {exc}")
                    proceed = False  # 終點 B：中止，不做主 swap；下次即 plain swap
            else:
                self._displacement = None  # liveness 丟棄（pane 關閉是日常，不 notify）
        if proceed:
            try:
                self.actions.swap_selected_with_active(
                    selected_pane_id=target_pane_id, active_pane_id=slot_pane_id
                )
                self._displacement = (target_pane_id, slot_pane_id)  # 終點 C
                self.actions.focus_pane(target_pane_id)
            except Exception as exc:  # noqa: BLE001
                self._notify_soft(f"swap failed: {exc}")  # 終點 D：record 維持 None
        self._reconcile_state()  # 所有終點一律全量 re-scan

    def _notify_soft(self, message: str) -> None:
        """fail-soft 通知（沿用 _after_manager_tick 的 notify 容錯模式）。"""
        notifier = getattr(self, "notify", None)
        if callable(notifier):
            try:
                notifier(message, severity="error")
            except TypeError:
                notifier(message)
```

- [ ] **Step 4: 跑測試確認通過（含全套件）**

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer tests.test_stage11_operator_cockpit -v 2>&1 | tail -5`
Expected: PASS。注意：既有 swap 測試若斷言「swap 後立即呼叫 focus_pane」順序不同，依新序（swap→record→focus→re-scan）更新斷言。

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/cockpit/app.py tests/test_cockpit_three_layer.py
git commit -m "feat(cockpit): restore-before-swap 自動歸位——activate 終點 A/B/C/D"
```

---

### Task 7: JOBS 收合（`j` toggle）

**Files:**
- Modify: `paulshaclaw/cockpit/app.py`
- Test: `tests/test_cockpit_three_layer.py`

**Interfaces:**
- Consumes: `_refresh_jobs_panel` 既有結構、`slices_from_status`
- Produces: `Binding("j", "toggle_jobs", ...)`；`self._jobs_collapsed: bool`；`action_toggle_jobs()`

- [ ] **Step 1: 失敗測試**

Append：

```python
@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class JobsToggleTests(unittest.IsolatedAsyncioTestCase):
    def _status(self):
        return {"in_flight": [{"slice_id": "s1", "state": "running"}]}

    async def test_toggle_collapse_and_expand(self):
        app = make_app()
        app.manager_client = SimpleNamespace(
            read_status=self._status, submit_request=lambda *a, **k: None
        )
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            jobs = app.query_one("#global-jobs")
            expanded = jobs.region.height
            await pilot.press("j")
            await pilot.pause()
            self.assertLessEqual(jobs.region.height, 3)
            self.assertIn("▸", str(jobs.border_title))
            self.assertIn("1 slices", str(jobs.border_title))
            await pilot.press("j")
            await pilot.pause()
            self.assertEqual(jobs.region.height, expanded)

    async def test_toggle_blocked_while_modal_open(self):
        app = make_app()
        app.manager_client = SimpleNamespace(
            read_status=self._status, submit_request=lambda *a, **k: None
        )
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            self.assertFalse(app._jobs_collapsed)
            await pilot.press("escape")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer.JobsToggleTests -v 2>&1 | tail -5`
Expected: FAIL（`j` 未綁定）

- [ ] **Step 3: 實作**

`app.py`：
1. `BINDINGS` 加 `Binding("j", "toggle_jobs", "j 收合/展開 JOBS"),`
2. `__init__` 加 `self._jobs_collapsed = False  # JOBS 收合態（in-memory，重啟歸零）`
3. 新增 action：

```python
    def action_toggle_jobs(self) -> None:
        if self._background_actions_blocked():
            return
        self._jobs_collapsed = not self._jobs_collapsed
        self._refresh_jobs_panel()
```

4. `_refresh_jobs_panel` 在 `rows = slices_from_status(status)` 之後插入收合分支、展開路徑補 max_height 還原：

```python
        if self._jobs_collapsed:
            # 收合：只剩 border 標題列（上框+空內容+下框 ≤3），N 照常刷新。
            self._set_border(jobs_widget, f"JOBS ▸ {len(rows)} slices", None)
            try:
                jobs_widget.styles.max_height = 3
            except Exception:
                pass
            jobs_widget.update("")
            return
        try:
            jobs_widget.styles.max_height = 12
        except Exception:
            pass
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m unittest tests.test_cockpit_three_layer -v 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/cockpit/app.py tests/test_cockpit_three_layer.py
git commit -m "feat(cockpit): JOBS j 鍵收合（預設展開、收合 ≤3 行、N 隨 refresh）"
```

---

### Task 8: 說明文案 + 全套件 + 冒煙 + 收尾

**Files:**
- Modify: `paulshaclaw/cockpit/help.py`
- Modify: `docs/superpowers/specs/2026-07-22-cockpit-three-layer-doubleclick-design.md`（狀態註記）
- Modify: `openspec/changes/cockpit-three-layer/tasks.md`（勾選）

**Interfaces:**
- Consumes: 全部前置 Task
- Produces: 可交付的分支（待 PR）

- [ ] **Step 1: help 文案**

`help.py` `render_help_text` 的結尾清單改為：

```python
        return "\n".join(
            [
                "Stage 11 Cockpit Help",
                "",
                "Keys:",
                *rows,
                "",
                "Behavior:",
                "The work list shows panes of the cockpit session; other sessions",
                "are enumerated and counted in the banner summary only (#249).",
                "Enter or double-click swaps the selected pane with the active slot.",
                "A previous swap is restored automatically before the next one.",
                "j collapses / expands the JOBS panel.",
                "The active slot is never inferred from another session with matching geometry.",
            ]
        )
```

同步更新既有 help 相關測試的預期文字（`grep -rn "Enter swaps\|all local tmux sessions\|Multi-session" tests/` 逐筆修正斷言）。注意：「WORK 只列 cockpit session」是 #249 已出貨行為（`store.py:102`），本 change 的 delta spec 已 truth-up（req 5 MODIFIED）——help 文案照上述新語意寫，勿寫回跨 session 舊語。

- [ ] **Step 2: 全測試套件**

Run: `.venv/bin/python -m unittest discover -s tests -v 2>&1 | tail -8`
Expected: 全綠（OK，無 FAIL/ERROR）

- [ ] **Step 3: 本機冒煙（tmux 內實跑）**

在 tmux session 內某 pane 執行：
```bash
cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. .venv/bin/python -m paulshaclaw.cockpit --cockpit-pane "$TMUX_PANE"
```
檢查：三層版面呈現、雙擊候選列會 swap、再雙擊另一列會先歸位、`j` 收合展開、`?` 說明含新互動、`q` 離開。

- [ ] **Step 4: 收尾與 commit**

1. design doc 狀態行改：`v8 定稿（…）｜ 實作完成（本 plan 全 Task 綠燈）`
2. `openspec/changes/cockpit-three-layer/tasks.md` 全部勾選
3. Commit：

```bash
git add paulshaclaw/cockpit/help.py docs/ openspec/ tests/
git commit -m "feat(cockpit): help 文案納入雙擊/歸位/j 收合；change tasks 收尾"
```
