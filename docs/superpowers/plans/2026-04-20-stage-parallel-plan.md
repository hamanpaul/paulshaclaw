# 全 Stage 平行開發計畫（fleet / multi-agent / subagent）

## 1. 目標

在啟動 Stage 3（A 路線）前，先把 Stage 0~7 的 `plan/task/todo` 全部切成可平行、低耦合、可驗證的工作流，避免多 agent 互相覆蓋。

## 2. 平行切分原則

1. 一個功能（workstream）對應一個主 worktree 分支。
2. 每個 workstream 必須宣告「可寫範圍」與「禁止寫入範圍」。
3. 共用檔（例如 `docs/research/05...`）只能由 `stage0-tooling-foundation` 維護。
4. 任何要 sync 回 `custom-skills` 的內容，必須先通過該 Stage 測試並保留證據。

## 3. Stage 平行矩陣

| Stage | Workstream | 先決依賴 | 可寫範圍 | 禁止寫入（避免互撞） | 測試 gate（sync-back 前） |
|---|---|---|---|---|---|
| 0 | `stage0-tooling-foundation` | 無 | `openspec/specs/stage0/`、`scripts/`、`docs/research/05...` | `paulshaclaw/core/`、`paulshaclaw/runtime/` | Stage0 規格檢查 + 文件一致性 |
| 1 | `stage1-core-daemon-tui-bot` | Stage0 baseline | `paulshaclaw/core/`、`paulshaclaw/tui/`、`paulshaclaw/bot/` | `openspec/specs/stage2+` | Stage1 integration smoke |
| 2 | `stage2-paulsha-memory` | Stage0 baseline | `paulshaclaw/memory/`、`paulshaclaw/janitor/`、`openspec/specs/stage2/` | Stage1 core/bot 實作路徑 | Stage2 importer/classifier/replay |
| 3 | `stage3-lifecycle-mvp` | Stage1 + Stage2 baseline | `paulshaclaw/lifecycle/`、`openspec/specs/stage3/` | Stage4+ persona/security 目錄 | Stage3 gate + golden slice |
| 4 | `stage4-persona-contract` | Stage3 baseline | `paulshaclaw/persona/`、`openspec/specs/stage4/` | Stage3 lifecycle engine 核心檔 | Stage4 guardrail + handoff |
| 5 | `stage5-observability-recovery` | Stage1 + Stage2 baseline | `paulshaclaw/observability/`、`docs/ops/` | Stage3/4 contract 定義檔 | Stage5 failover/recovery |
| 6 | `stage6-ops-companion-security` | Stage0 + Stage1 baseline | `paulshaclaw/security/`、`openspec/specs/stage6/` | Stage1/2 非 security 實作 | Stage6 approval/redaction/audit |
| 7 | `stage7-deploy-three-plane` | Stage1 最小可跑版 | `paulshaclaw/deploy/`、`paulshaclaw/config/`、`openspec/specs/stage7/` | Stage1~6 的執行邏輯檔 | Stage7 install/upgrade/uninstall |

## 4. Plan / Task / Todo 產物規範

每個 workstream 目錄固定三份文件：

- `plan.md`: 範圍、邊界、介面契約
- `task.md`: 可驗證任務清單（每項可獨立完成）
- `todo.md`: 當前短迭代執行細項

路徑格式：

- `docs/superpowers/workstreams/<workstream>/plan.md`
- `docs/superpowers/workstreams/<workstream>/task.md`
- `docs/superpowers/workstreams/<workstream>/todo.md`

## 5. /opsx:new 與 /opsx:ff 約定

- `/opsx:new <workstream>`：建立單一功能的 plan/task/todo 骨架與分支對照。
- `/opsx:ff <workstream>`：做 fleet-friendly 切分檢查（寫入邊界、依賴、測試 gate），再進入實作。

## 6. Worktree 與分支配置

| Workstream | Branch | Worktree Path |
|---|---|---|
| `stage0-tooling-foundation` | `wt/stage0-tooling-foundation` | `/home/paul_chen/prj_pri/paulshaclaw-worktrees/stage0-tooling-foundation` |
| `stage1-core-daemon-tui-bot` | `wt/stage1-core-daemon-tui-bot` | `/home/paul_chen/prj_pri/paulshaclaw-worktrees/stage1-core-daemon-tui-bot` |
| `stage2-paulsha-memory` | `wt/stage2-paulsha-memory` | `/home/paul_chen/prj_pri/paulshaclaw-worktrees/stage2-paulsha-memory` |
| `stage3-lifecycle-mvp` | `wt/stage3-lifecycle-mvp` | `/home/paul_chen/prj_pri/paulshaclaw-worktrees/stage3-lifecycle-mvp` |
| `stage4-persona-contract` | `wt/stage4-persona-contract` | `/home/paul_chen/prj_pri/paulshaclaw-worktrees/stage4-persona-contract` |
| `stage5-observability-recovery` | `wt/stage5-observability-recovery` | `/home/paul_chen/prj_pri/paulshaclaw-worktrees/stage5-observability-recovery` |
| `stage6-ops-companion-security` | `wt/stage6-ops-companion-security` | `/home/paul_chen/prj_pri/paulshaclaw-worktrees/stage6-ops-companion-security` |
| `stage7-deploy-three-plane` | `wt/stage7-deploy-three-plane` | `/home/paul_chen/prj_pri/paulshaclaw-worktrees/stage7-deploy-three-plane` |
