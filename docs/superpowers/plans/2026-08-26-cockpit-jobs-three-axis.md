---
work_item: cockpit-jobs-three-axis
---

# Plan：cockpit JOBS 面板三軸重設計（issue #322）

目標 repo：paulshaclaw｜對應 issue：#322｜PR body 須 `Closes #322`

互動 mockup：[`2026-08-26-cockpit-jobs-three-axis-mockup.html`](2026-08-26-cockpit-jobs-three-axis-mockup.html)——單檔自足，內嵌 2026-08-26 現場 59 筆真實資料，可切三軸並對照「修之前／修之後」。

## Context

使用者反映看不懂 JOBS 面板「哪個 project、卡在哪個 stage、由哪個 agent 執行」。經實測 `~/.agents/control/status.json`（2026-08-26 現場），問題**不是顯示不清楚，是資料根本沒進到畫面**：

```
attention n = 43
kind 分布 = {'workflow_run': 42, 'slice': 1}
可辨識 id 欄位分布 = {None: 42, 'slice_id': 1}
```

`app.py:217-219` 對每筆 attention 呼叫 `_slice_id_from_item()`（`app.py:122`，只認 `slice_id`/`id`/`name`/`title`），取不到就 `continue`。而 cortex 已從 slice 平面遷移到 workflow_run 平面，42 筆 workflow_run 條目帶的是 `work_id` + `run_id`，**四個 key 一個都沒有 → 整批被丟棄**。

面板現在實際只剩 1 筆 legacy slice + 10 筆 recent_done。真正需要人處理的 42 件工作，一件都不在畫面上。這也解釋了為何 #292→#317 一連串顯示層修正（配色、對齊、縮寫、trailer 排版）都沒解決使用者的困惑——修的是那 11 列的樣式，看不到的 42 列從未被觸及。

同時實測確認：`repo` 42/42 都有值（cortex 39、hippo 3），`current_phase` 也齊（claim 30、build 5、verify 4、review 2、define 1）。**三軸所需資料上游全部備妥**，缺的是 ingest 與資訊架構。

第二個發現：**30/42 卡在 `claim`，且在 `jobs.json` 中完全沒有對應 job 紀錄**——最大宗的「卡住」不是某個 agent 跑掛，是連認領都沒發生。面板必須讓這件事一眼可見。

### 已與使用者確認的決策

| 項目 | 決定 |
|---|---|
| 面板主軸 | 三軸都要，可切換（by project / by stage / by agent） |
| project 層級 | 兩層：repo → 任務（work_id） |
| stage 層級 | **只一層**，用 cortex 的 7 個 phase；放棄 Stage 0~5 上層（repo 內無任何 runtime 資料可對應，只存在 `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md` 的文字） |
| agent 來源 | **只用 phase→persona 確定性推導**，不讀 `jobs.json`、不動 cortex repo |
| 版面容量 | 維持 `max-height: 12`，靠折疊與捲動 |

---

## 範圍

只改 `paulshaclaw`，不動 `paulsha-cortex`。不新增檔案以外的相依。

---

## 設計

### 1. 修 ingest 門檻（最關鍵，其餘都建立在這之上）

`app.py:122` `_slice_id_from_item()` 增加 `work_id` / `run_id` fallback，並保持原優先序在前（legacy slice 不受影響）：

```python
for key in ("slice_id", "id", "name", "title", "work_id", "run_id"):
```

`app.py:212-234` 的 attention 迴圈改為依 `item["kind"]` 分流：`workflow_run` 走新欄位（`work_id` / `current_phase` / `run_id` / `blocking_reason`），`slice`（與缺 `kind` 的舊資料）走現行路徑。

`blocking_reason` 是 `DiagnosticReason` dict，人可讀內容在 `detail`（≤400 字），機器碼在 `reason`；現行 `_text_field(item, "reason", "gate_reason")` 只取得機器碼。新增取 `blocking_reason.detail` 當補充說明——現場 42 筆中 32 筆 `reason` 為 `None`，只靠 `reason` 會有 32 列無說明。

同時補上兩個現存盲區：
- `status["not_claimable"]`（現場 6 筆）：合成 phase `"未認領"`，帶 `next_step_hint` 當 detail。用 `status.get("not_claimable", [])` 容錯——安裝版 cortex 0.1.8 沒有這個 key。
- `status["slices"]`（現場 1 筆）：現行完全沒讀。

### 2. `JobRow` 增欄（`models.py:60`）

新增 `work_id`、`phase`、`run_id`、`kind` 四欄，全部給預設值以免動到既有建構點。`slice_id` 欄位保留原名不改（改名會波及 `jobs_panel.py` 的 node key 規則與三個測試檔），對 workflow_run 條目填 `work_id`。

新增衍生 property：

```python
@property
def persona(self) -> str:
    """phase → 執行角色。來源：cortex 套件（site-packages）的
    coordinator/workflow.py `validate_manager_spine`，是契約不是猜測。"""
```

映射：`claim`/`ship`→`manager`、`define`/`plan`→`planner`、`build`→`builder`、`verify`/`review`→`reviewer`；`未認領` 與未知 phase → `""`。

`claim` 階段實測 30/30 無 job 紀錄（尚未派工），persona 顯示 `manager` 但需在 detail 標明「尚未派工」，避免誤讀成 manager 正在跑。

### 3. 分組改為軸驅動（取代 `app.py:265-303`）

現行 `_group_key()` 靠 `_PHASE_SUFFIXES` 硬編碼清單猜 slice_id 字串前綴——有了真實 `work_id`/`repo`/`phase` 欄位後這套猜測全部退役。

```python
GroupAxis = Literal["project", "stage", "agent"]
```

三軸各自的分組鍵與樹形（一律兩層 + detail 子行，不因軸而變深）：

| 軸 | 第 1 層 | 第 2 層列 |
|---|---|---|
| `project` | repo（`paulsha-cortex` / `paulsha-hippo` / `未歸屬`） | phase · work_id · persona |
| `stage` | phase（7 個 + `未認領`） | work_id · persona · repo |
| `agent` | persona（4 個 + `未派工`） | phase · work_id · repo |

`group_job_rows()` 改收 `axis` 參數。排序規則（回應 30 筆 claim 積壓沉底）：

1. 群組層：含 needs_human 的優先；`未認領` 群與 recent_done 群永遠沉底
2. 群組內：非 `claim` 的任務優先於 `claim`——12 行剛好容納現場 12 件真正在管線裡的工作，30 筆待認領積壓自然落在捲動線以下

`recent_done` 不佔預設視野：歸入所屬 repo 群但排在最後，且不設 `expand`。

**detail 子行改為預設收合**（做 mockup 才發現，必須改）：`jobs_panel.py:245,296` 現行是 `expand=row.needs_human`——needs_human 就自動展開 detail。舊資料只有 1 筆 needs_human 所以無感，新版 42 筆全部是 needs_human，全展開就是 42 列 + 42 行 detail = 84 行，10 行可視區只剩 4~5 件工作可見，比現況更難用。

改為：群組層預設展開（讓工作列可見），**detail 子行預設收合**，游標停在該列按 enter/space 才展開（Tree 原生行為，不需新程式碼）。工作列本身已帶 phase / work_id / persona 三欄，多數時候不必展開 detail 就能判斷該不該處理。

### 4. 版面：四欄語意化（`jobs_panel.py`）

現行 trailer 把 `project · branch · note · raw_state` 擠成一串（`jobs_panel.py:259-275`），四種資訊沒有固定欄位、寬度不足時整段被 `_fit_trailer` 由右往左砍掉——這正是「看不出是哪個 project」的直接成因。改為固定四欄：

```
JOBS · 58 件 · 12 在管線 · 30 待認領                    [by project]
──────────────────────────────────────────────────────────────────
▾ ● paulsha-cortex                            39 件 · 9 在管線
  ▾ ● build    fix-instance-config-isolation      builder
      ↳ periodic tick 續跑 workflow 時擲出例外：ValueError: workflo…
    ● verify   test-r21-regex-resilience          reviewer
    ● define   fix-read-repo-tier-fail-closed     planner
    ● claim    manager-gitconfig-delivery         manager  尚未派工
▸ ● paulsha-hippo                              3 件 · 3 在管線
▸ ○ 未認領                                     6 件
```

欄位模板：`glyph(1) 空格 phase(8) 空格 work_id(彈性) 空格 persona(9)`。

沿用既有基礎設施，不重寫：
- `_layout_columns()`（`jobs_panel.py:164`）擴充為算四欄；`_display_width()`（CJK 全形）、`_pad_display()`、`_ellipsize_middle()`、`_fit_trailer()` 原樣沿用
- `status_style()` 五桶配色（`jobs_panel.py:31`）不動；新增 phase 欄用中性色，狀態語意仍只由 glyph 顏色承載（#317 owner 裁決：trailer 維持終端預設前景）
- `build_jobs_nodes()`（`jobs_panel.py:249`）保持純函式、不碰 widget 的既有契約——這是三個測試檔的斷言基礎
- node key 規則沿用 `{group.key}` / `{group.key}/{row_id}` / `.../detail`，`set_groups()` 的 cursor 還原（`jobs_panel.py:376-418`）不需改

`_PHASE_SUFFIXES`（`app.py:267-275`）與 `JobRow.workflow_id` / `JobGroup._phase_label()` 等為字串猜測服務的程式碼一併刪除。

### 5. 軸切換與標題列

`app.py:332` BINDINGS 新增 `Binding("g", "cycle_jobs_axis", "JOBS 分組軸")`（`g` 未被佔用；現有為 tab/j/m/t/c/?/q）。循環 project → stage → agent。

軸狀態存在 `CockpitApp` 上（同 `_jobs_collapsed` 的做法），border subtitle 顯示 `[by project]`。border title 改為分層計數：`58 件 · 12 在管線 · 30 待認領 · 6 不可認領`——現行只顯示 `N slices · M 待人工`，看不出積壓結構。

切軸時整棵樹重建，`_user_expanded` 需按軸分別保存（key 前綴帶軸名），否則切回來展開狀態錯亂。

### 6. detail 子行的可執行命令

現行 `JobRow.detail_line`（`models.py:107-125`）產出 `cortex slice-action <slice_id> <actions> --actor $USER`。workflow_run 走的是不同 request type（cortex 套件 `control/contract.py` 的 `REQUEST_TYPES` 含 `work-action`），且多數 action 有 fail-closed 的必要參數（`abandon` 需 `expected_run_id` + `actor` + `reason`；`retry-build` 需 40-hex `expected_candidate`）。

**實作時必須先跑 `cortex work-action --help` 確認實際 CLI 形式與參數**，不可照抄 slice-action 的格式。若 CLI 無法在一行內完整表達，detail 行改為顯示 `next_actions` 清單 + `run_id`，讓使用者自行組命令——寧可少給也不給錯命令。

---

## 要改的檔案

| 檔案 | 改動 |
|---|---|
| `paulshaclaw/cockpit/app.py` | `_slice_id_from_item` fallback；`slices_from_status` 依 kind 分流 + 補 not_claimable/slices；`_group_key`/`group_job_rows` 改軸驅動；刪 `_PHASE_SUFFIXES`；`_refresh_jobs_panel` 標題計數；新增 `action_cycle_jobs_axis` + BINDINGS |
| `paulshaclaw/cockpit/models.py` | `JobRow` 增四欄 + `persona` property；`JobGroup` 增分層計數 property；刪 `workflow_id`/`_phase_label` |
| `paulshaclaw/cockpit/jobs_panel.py` | `_layout_columns` 擴四欄；`build_jobs_nodes` 改四欄模板；`_user_expanded` key 帶軸前綴 |
| `paulshaclaw/cockpit/cockpit.tcss` | 不改（維持 `max-height: 12`） |

---

## 驗證

TDD：先寫紅燈測試再實作。既有測試是重要的回歸網，`build_jobs_nodes` 純函式契約與 node key 規則不得破壞。

**新增測試**（餵真實形狀的 fixture，取自現場 status.json）：

1. `slices_from_status` 收到 42 筆無 `slice_id` 的 workflow_run 條目，回傳 42 個 `JobRow`——**這是本次的核心回歸測試**，防止 ingest 門檻再次靜默吃掉整批資料
2. `kind: "slice"` 的舊條目行為不變（既有 1 筆 legacy slice）
3. `not_claimable` 6 筆納入且 phase 為 `未認領`；缺此 key 時不炸（cortex 0.1.8 相容）
4. `persona` property 對 7 個 phase 的映射與 cortex 套件 `coordinator/workflow.py` 的 `validate_manager_spine` 一致
5. 三個軸各自的分組鍵、群組排序（needs_human 優先、未認領沉底、claim 沉底）
6. `g` 鍵循環三軸（Pilot 測試）；切軸後展開狀態各自保存
7. 四欄版面在 80 寬終端不破版、CJK 不錯位

**既有測試**須全綠：`tests/test_cockpit_jobs_panel.py`、`test_cockpit_jobs_ux.py`、`test_stage11_operator_cockpit.py`、`test_cockpit_three_layer.py`、`test_cockpit_redesign.py`。

跑法（系統 python3 缺 `paulsha_cortex`，必須用 repo venv）：

```bash
cd <worktree> && PYTHONPATH=$PWD /home/paul_chen/prj_pri/paulshaclaw/.venv/bin/python -m pytest tests/ custom-skills/bro/tests/ -q
```

Pilot 測試在 `set_groups` 後斷言 cursor 前必須 `await pilot.pause()`（`call_after_refresh` 是非同步的）。

**真機驗收**（測試綠之後才做，不可省略——本次問題正是「測試全綠但畫面是空的」）：

```bash
PYTHONPATH=$PWD .venv/bin/python -m paulshaclaw.cockpit --cockpit-pane $TMUX_PANE --once
```

肉眼確認：42 筆 workflow_run 出現、repo 分成 cortex/hippo 兩群、phase 欄有值、persona 欄有值、`g` 可切三軸、12 行內先看到的是在管線中的工作而非 claim 積壓。

---

## 交付規範（本 repo policy 1.0.17）

- 分支 `feature/<slug>`，**slug 不得含小數點**（R-12）
- PR body 寫 `Closes #N`（R-17）；動工前 `gh issue view` 核對，查無對應 issue 照常進行
- 掛 label `policy-exempt:secret-scan`（R-21 為 repo 級恆 FAIL 狀態，每個 code PR 都要）
- 附 `changelog.d/` 碎片（R-09）
- 本機驗 policy 只能跑 `run.sh`，直呼 CLI 會讓 label/head-ref 靜默失效造出假綠假紅
- commit 前用**明確檔案清單** `git add`，勿 `git add -A`——跑全套測試會刪掉 test-artifacts 下 stage7-install-create-only 的兩個檔（env 與 systemd unit）
- PR 標題／內文／comment 一律 zh-tw

---

## 已知後續（本次不做，建議另開 issue）

1. `openspec/specs/stage11-operator-cockpit/spec.md:149` 只規範 JOBS 的收合與版面，**沒有規範內容**；JOBS 顯示規則目前只活在 CHANGELOG 與程式碼註解裡。本次的三軸資訊架構值得補進 spec。
2. cortex 端讓 `attention` 條目直接帶 `persona`/`executor`/`model`，cockpit 就能顯示「實際是 copilot 還是 codex 在跑」而非只有邏輯角色。
3. `_refresh_jobs_panel` 每 30 秒在 Textual 事件迴圈裡同步讀 55KB JSON（`app.py:826`），目前可接受但已是已知阻塞點。
4. `app.py:833/839` 用 `styles.max_height` 直接改，與 tcss `:67` 是兩個真相來源。
