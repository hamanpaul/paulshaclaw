## Why

Stage 1 core daemon / TUI / Telegram bot 最小基線已於 worktree `wt/stage1-core-daemon-tui-bot` 完成實作，並於 commit `49d2739` 以 `--no-ff` 合併回 main。Stage 3 canonical contract v0.1（`openspec/specs/stage3/README.md` §2）明確把 Stage 1 daemon 的 `/status`、`/dispatch`、config seam、coordinator seam 列為下游必須可依賴的介面，但 Stage 1 本體沒有 openspec change 追認，導致 Stage 3 / 5 / 6 / 7 的 runtime change 缺乏 diff 原點。本 change 以 reverse-record 方式把 Stage 1 已落地工作事後追認為 `stage1-core-runtime` capability，作為後續 Stage 1 範圍變更的唯一基線。

## What Changes

- 追認 `paulshaclaw/core/daemon.py` 為 daemon runtime baseline（`/status`、`/dispatch` 兩個指令、JSON 回傳 shape 對齊 Stage 3 contract §2.2/§2.3）
- 追認 `paulshaclaw/core/config.py` 為 config seam baseline（`--config` flag → `PSC_STAGE1_CONFIG` 環境變數 → 失敗報錯的精確 precedence、必填欄位檢查）
- 追認 `paulshaclaw/core/__init__.py` 提供 `CoordinatorClient` Protocol 與 `LocalCoordinator` 預設實作為 coordinator seam baseline
- 追認 `paulshaclaw/tui/view.py` 為 TUI pane/task 展示 baseline
- 追認 `paulshaclaw/bot/telegram.py` 為 Telegram bot router baseline（`allowed_user_ids` 白名單、未授權使用者拒絕、授權使用者路由至 daemon）
- 追認 `config/paulshaclaw-stage1.sample.json` 為 Stage 1 sample config baseline
- 追認 `tests/test_stage1_smoke.py` 為 Stage 1 smoke test baseline（12 條案例：config loader / daemon / TUI / telegram 三類 / CLI 子程序三類）
- 追認 `docs/superpowers/workstreams/stage1-core-daemon-tui-bot/` 的 `plan/task/todo/review/module-boundaries/evidence/*` 為工作流程證據基線
- 無 **BREAKING**

## Capabilities

### New Capabilities

- `stage1-core-runtime`: Stage 1 core daemon、TUI、Telegram bot 最小執行時合約。本 capability 涵蓋 daemon `/status`/`/dispatch` JSON shape、config 載入 precedence、coordinator seam Protocol、TUI 渲染、Telegram authz gate、sample config、smoke test 驗收等全部 Stage 1 §8 驗收條目。

### Modified Capabilities

（無。Stage 1 為首次基線追認，沒有既有 capability 需要修改。）

## Impact

- **Code**：
  - `paulshaclaw/core/daemon.py`、`paulshaclaw/core/config.py`、`paulshaclaw/core/__init__.py`
  - `paulshaclaw/tui/view.py`、`paulshaclaw/bot/telegram.py`
  - `paulshaclaw/__init__.py`、各 subpackage `__init__.py`
- **Specs**：
  - 新增 canonical `openspec/specs/stage1-core-runtime/spec.md`（由 archive 自動同步產生）
- **Config / Tests**：
  - `config/paulshaclaw-stage1.sample.json`
  - `tests/test_stage1_smoke.py`（12 條案例）
- **Docs / Workflows**：
  - `docs/superpowers/workstreams/stage1-core-daemon-tui-bot/{plan,task,todo,review,module-boundaries}.md`
  - `docs/superpowers/workstreams/stage1-core-daemon-tui-bot/evidence/*`
  - `docs/superpowers/archive/stage1-core-daemon-tui-bot-20260420T1855570800.md`
- **Downstream stages**：
  - Stage 3 lifecycle runtime 以 `stage1-core-runtime` 為 `/status`/`/dispatch` 的 consumer
  - Stage 5 observability 以 daemon 為 metric 來源
  - Stage 6 security 以 Telegram authz gate 為 audit 起點
  - Stage 7 deploy 以 sample config 結構為設定檔模板
