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

- `plan.md`：遵循 writing-plans 結構（`Scope/Steps/Relevant files/Verification/Decisions`）
- `task.md`：可驗證任務清單（每項可獨立完成）
- `todo.md`：遵循短迭代格式（`Current Sprint/Blockers/Evidence/Handoff`）

路徑格式：

- `docs/superpowers/workstreams/<workstream>/plan.md`
- `docs/superpowers/workstreams/<workstream>/task.md`
- `docs/superpowers/workstreams/<workstream>/todo.md`

## 5. /opsx:new 與 /opsx:ff 約定

- `/opsx:new <workstream>`：建立單一功能的 plan/task/todo 骨架與分支對照。
- `/opsx:ff <workstream>`：做 fleet-friendly 切分檢查（寫入邊界、依賴、測試 gate），再進入實作。

## 6. 串聯收斂（Serial Convergence）

> 本節反映截至 2026-04-20 各 worktree 的實際進度，記錄 Stage 3 共享合約凍結後的收斂策略。

### 6.1 現況快照

| Worktree | Branch | 進度摘要 |
|---|---|---|
| `stage1-core-daemon-tui-bot` | `wt/stage1-core-daemon-tui-bot` | daemon `/status`、`/dispatch`、config seam、coordinator seam 已實作，smoke test 通過 |
| `stage2-paulsha-memory` | `wt/stage2-paulsha-memory` | `inbox → work-centric → knowledge` 路由、importer/classifier/replay、janitor 邊界、decayed/reactivation 事件已有 spec 和 routing 文件 |
| `stage6-ops-companion-security` | `wt/stage6-ops-companion-security` | approval gate（阻擋 `/ship`）、append-only audit entry（含 `previous_hash/entry_hash`）、Stage 7 消費介面已有 spec |
| `stage3-lifecycle-mvp` | `wt/stage3-lifecycle-mvp` | 尚為 placeholder；依賴 Stage 1/2 merge 後才能啟動 runtime 實作 |
| `stage4/5/7` | main placeholder | 依賴 Stage 3 合約；合約已凍結於 `openspec/specs/stage3/README.md` |

### 6.2 收斂順序

```
Stage 0 (已鋪設骨架，main)
    │
    ├─► Stage 1 merge → main   ← 解除 Stage 3/5/6/7 阻塞
    │
    ├─► Stage 2 merge → main   ← 解除 Stage 3 importer 通知阻塞
    │
    ├─► Stage 6 merge → main   ← 可獨立 merge（硬依賴 Stage 0/1）；
    │                            audit trail runtime 整合仍需等 Stage 3 events.jsonl 落地
    │
    └─► Stage 3 worktree 啟動 runtime 實作
              │
              └─► Stage 4 persona loader 啟動（依賴 Stage 3 events.jsonl）
                       │
                       └─► Stage 5 觀測/failover 啟動（依賴 gate report + events）
                                │
                                └─► Stage 7 deploy 啟動（lifecycle template 路徑已定）
```

### 6.3 Stage 3 共享合約凍結聲明

**`openspec/specs/stage3/README.md`** 已於本 PR 凍結以下共享合約（詳見該文件）：

- 七個正規 phase 名稱（`research/define/plan/build/verify/review/ship`）
- Stage 1 daemon 最小介面：`/status` + `/dispatch` 的 JSON 回傳欄位、config seam、coordinator seam
- Stage 2 memory 最小介面：`inbox → work-centric → knowledge` 路由、importer/classifier/replay/janitor 邊界、decayed/reactivation 事件種類
- Artifact frontmatter 必填欄位（含 `slice_id / artifact_kind / supersedes / checksum`）
- `lifecycle.yaml` 最小 shape（含 `current_slice / current_phase / gates`）
- Gate report shape 及十種核心事件種類
- Stage 6 audit 所需 `meta` 欄位

後續 Stage 3/4/5/6/7 worktree 的 runtime 實作應以此合約為輸入，不得重新定義其中的介面。

## 7. Worktree 與分支配置

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
