# stage9-project-monitor / plan

## Scope

- Stage: 9
- 目標: 落地 Project Monitor service，作為 Stage 1 dispatch 與 Stage 3 lifecycle 的 canonical task source；同時引入 paulshaclaw 首個 global config
- 先決依賴: Stage 0 baseline；read-only 消費 Stage 1 / Stage 3 的 public artifact 格式（todo.md / task.md / openspec archive）
- In scope:
  - `paulshaclaw/monitor/`（scanner / parser / watcher / api / models）
  - `paulshaclaw/config/paulshaclaw.sample.yaml`（首個 global config 樣本）
  - 全局 config loader（CLI flag → env → `~/.config/paulshaclaw/paulshaclaw.yaml` → sample fallback）
  - `tests/test_stage9_project_monitor.py` 與整合測試 fixture
  - `openspec/specs/stage9-project-monitor/spec.md`（archive 後）
  - `docs/superpowers/workstreams/stage9-project-monitor/`
- Out of scope:
  - 修改 Stage 1 daemon / Stage 3 lifecycle 內部 task 選擇邏輯（消費端在另一個 change）
  - 擴展 `.paul-project.yml` schema（design §4 decision #4：保持現狀）
  - Stage 11 cockpit 加入 project-level pane（後續 follow-up）
  - 真實 systemd unit 或 deploy 腳本（Stage 7 範疇）

## Steps

### Phase 1: TDD Red — 合約鎖定

1. 撰寫 `tests/test_stage9_project_monitor.py` smoke 測試，鎖定：
   - 全局 config 載入契約（與 Stage 1 `load_config` 風格對齊）
   - workspace 列舉、tracked-vs-legacy 分類規則（design §3.2）
   - ProjectState schema 萃取（completed / in_progress / pending）
   - processing_task / next_task / blockers 解析
   - `--once` CLI 模式輸出 JSON snapshot
2. 執行 `python3 -m unittest tests.test_stage9_project_monitor -v` 並保存 red 證據至 `evidence/`。

### Phase 2: TDD Green — 最小可跑

1. 建立 `paulshaclaw/monitor/` package layout：
   - `models.py`（ProjectState / StageRef / StageView / TaskRef / Signal）
   - `config.py`（global config loader + schema validation）
   - `scanner.py`（workspace 列舉 + tracked/legacy classifier）
   - `parser.py`（todo.md / task.md / archive / git branch state 萃取）
   - `__main__.py`（CLI 入口，支援 `--once` 與後續 `query`）
2. 實作 `Watcher` 與 `GitInspector` interface（design §4 decision #2/#5：watchdog + subprocess git，包在 interface 後）。
3. 重跑 unit + integration 測試至轉綠。

### Phase 3: Service runtime + Read API

1. 實作三個 loop：periodic scanner / filesystem watcher（debounced）/ Unix socket server（`~/.agents/run/project-monitor.sock`，0600）。
2. 實作 `list_projects` / `get_project_state` / `subscribe` JSON 契約（design §3.6）。
3. 撰寫 service-level test（啟動 monitor → 改 todo.md → assert subscriber 收到 coalesced event）。

### Phase 4: 文件、證據、收斂

1. 補齊 spec、task checkbox、todo evidence 連結、review.md。
2. 執行 `python3 -m unittest discover -s tests` 全量回歸。
3. 自我 review，盤點 risk（scan cost / stale snapshot / drift / secret leakage 見 design §5）。
4. 準備 archive：將 `openspec/changes/2026-04-26-stage9-project-monitor/specs/stage9-project-monitor/spec.md` 落到 `openspec/specs/stage9-project-monitor/spec.md`。

## Relevant files

- `paulshaclaw/monitor/`
- `paulshaclaw/config/paulshaclaw.sample.yaml`
- `tests/test_stage9_project_monitor.py`
- `openspec/changes/2026-04-26-stage9-project-monitor/`（propose 階段成果，apply 後 archive）
- `openspec/specs/stage9-project-monitor/spec.md`（archive 後 canonical）
- `config/worktrees/stage-worktrees.tsv`（已加 stage9 row）
- `docs/superpowers/workstreams/stage9-project-monitor/{plan,task,todo,review}.md`
- `docs/superpowers/workstreams/stage9-project-monitor/evidence/`

## Verification

1. `python3 -m unittest tests.test_stage9_project_monitor -v` 先失敗後通過。
2. `python3 -m unittest discover -s tests` 全量通過（含 Stage 1 / Stage 11 既有測試不被打破）。
3. `python3 -m paulshaclaw.monitor --once --config <fixture>` 退出 0 並輸出符合 spec §B6 的 JSON。
4. Service test：啟動 monitor → 編輯 fixture 內 todo.md → subscriber 在 debounce window 內收到 coalesced event。
5. Integration test：將 monitor 指向 paulshaclaw 自己的 clone，比對輸出與 2026-04-26 手動驗證的 stage 狀態一致。

## Decisions

- Stage 9 編號重用，原「既有資產匯入」mission 保持永久取消（design §4 decision #1，canonical doc 已在 propose 階段更新）。
- Transport 限定 local Unix domain socket，不開 HTTP（design §4 decision #3）。
- `.paul-project.yml` schema 本輪不擴展（design §4 decision #4）。
- watchdog 為 watcher 預設 lib，subprocess git 為 branch inspection 預設策略；兩者皆包在內部 interface 後（design §4 decision #2/#5）。
- 此階段只負責產 monitor 與 read API；Stage 1/3 改為消費 monitor 是另一個 change，不在 scope 內。
- Single source of truth 原則：monitor 不持久化 per-project 平行狀態，只做 in-memory snapshot。
