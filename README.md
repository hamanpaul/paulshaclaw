# paulshaclaw

個人 agent 工作流設計文件庫。本 repo 是 docs-first 設計庫，不是可部署的應用程式。

## 專案簡介

`paulshaclaw` 提供 PaulShiaBro 個人 agent 系統的設計文件、規格、research notes 及骨架配置。
實際 runtime 狀態與 secrets 分別存放於 `~/.agents/` 與 `~/.config/paulshaclaw/`。

### Stage 架構

**完整 Stage 統計**（依據 `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md`）：

| # | 名稱 | 狀態 | 核心產出 | 工作區域邊界 |
|---|------|------|--------|-----------|
| 0 | 前置工具 refine / rename / Claude Code 支援 | 規劃中 | skill/tool 套件、命名表、openspec 骨架 | 工具重構與一致化；命名系統統一 |
| 0-tooling | 工具集成與政策檢查 | 規劃中 | tool-matrix.md、ref-manifest.yaml、worktree 腳本 | 詳細工具重命名矩陣；外部ref管理 |
| 1 | PaulShiaBro core daemon + TUI + Telegram bot | 進行中 | daemon binary、registry、三個介面（TUI/Telegram/CLI） | 運行時核心；agent 發現與納管；pane 命名 convention |
| 1-core-runtime | 核心運行時規格 | 進行中 | config loader、daemon status/dispatch、coordinator seam | config 載入優先順序；狀態查詢；任務調度到 coordinator |
| 2 | ~/.agents/memory 記憶中樞 + dream mode 24x7 | 規劃中 | importer、classifier、Memory Janitor service、bootstrap manifest | agent session artifact 流入；work-centric 分類；24x7 背景提案 |
| 2-memory-governance | 記憶治理與路由 | 規劃中 | inbox→work-centric→knowledge 路徑、decayed/reactivation 事件 | canonical memory routing；sync-back gate to custom-skills；obs-auto-moc 對接 |
| 3 | Life-cycle（slash command / artifact / phase gate） | 規劃中 | lifecycle.yaml、gate engine、slash routes、golden slice | artifact-first 生命週期；phase gate；stage 1/2/3 邊界定義 |
| 4 | Persona（角色目錄 / handoff / guardrail） | 規劃中 | personas.yaml、loader、guardrail engine、slice roster | 角色合約；handoff 流程；資源與權限邊界 |
| 5 | 觀測 / 健康 / failover + 錯誤 log 追蹤 | 規劃中 | supervisor、health probes、error log sink、recovery playbook | 三 always-on 元件監控；chaos 復原；log 生命週期管理 |
| 6 | 安全與機敏治理（ops-companion 核心） | 規劃中 | approval gate、secret redaction、audit trail、classification | 高風險動作審批；secret 防洩；審計日誌；機敏資訊分類 |
| 6-security-governance | 安全治理規範 | 規劃中 | ops-companion integration、redaction rules、audit schema | 詳細安全控制矩陣；機敏資訊管理規則 |
| 7 | 部署（core / state / secret 三分） | 規劃中 | psc install、template rename 邏輯、private repo 腳手架 | 三軸部署分離；升級保護；卸載策略 |
| 8 | 成本治理（token / premium budget） | postponed | — | 待專案進正軌後處理 |
| 9 | Project Monitor（跨專案狀態同步 service） | 進行中 | monitor service、global config、read API | 跨專案狀態同步；Stage 1/3 的 task source |
| 10 | 互通 / protocol 演進（socket / ACP / MCP） | postponed | — | 待上線後強化 |
| 11 | Operator Cockpit（多 session pane 列表） | 進行中 | multi-session pane aggregation、unified dashboard | 跨 tmux session 的 pane 統一檢視；運維介面 |

**Stage 依賴圖**（詳見 `docs/research/05` §6）：

```
Stage 0 (前置工具)
    ↓ (硬依賴)
┌─→ Stage 1 (daemon/TUI/bot)  ← ← ← → Stage 2 (記憶中樞) ← ← ← Stage 9 (Project Monitor)
│   ├→ Stage 3 (lifecycle)
│   ├→ Stage 5 (觀測)
│   └→ Stage 6 (安全)
│
└─→ Stage 4 (Persona)
    ├→ Stage 5
    └→ Stage 6

Stage 7 (部署) 跨越所有 stage
Stage 11 (Cockpit) 依賴 Stage 1
```

**各 Stage 結合方式**（詳見 `docs/research/05` §4-7）：

1. **Hub-and-spoke**：Manager 是唯一 task authority，worker 只做 bounded execution
2. **Artifact-first + event-first**：任何階段沒有 artifact 落地 + 事件寫入，就等於沒發生過
3. **Proposal-first**：對 canonical 記憶的改動先走提案流程
4. **Fail-close**：guardrail / security gate 遇異常拒絕，不自動降級
5. **Stage 獨立性**：下游 stage 失敗不擊倒上游（§7 降級策略）
6. **三軸分層**：code (`paulshaclaw/`) / state (`~/.agents/`) / secret (`~/.config/paulshaclaw/`)
7. **三個 always-on 失敗域分離**：daemon / Telegram bot / Memory Janitor 不共享 process / lock / watchdog

詳細 Stage 設計見 [`docs/research/`](./docs/research/)。

## Install

本 repo 為文件庫，無需安裝。若需執行 policy check：

```bash
pip install -e ".[test]"  # 在 paulsha-conventions repo 執行
python3 -m policy_check --repo /path/to/paulshaclaw
```

## Usage

### Stage 8 cost footer

```bash
# Emit one JSON snapshot for debugging
python3 -m paulshaclaw.cost --once

# Render the tmux footer line
python3 -m paulshaclaw.cost.status --plain
```

`scripts/start.sh` applies the Stage 8 footer to the current tmux session with the configured `status-interval` from `tmux_refresh_seconds` (default `30`). Copilot accounts are read from real config; account labels and request allowances are not hardcoded. If no runtime config file exists, Stage 8 falls back to built-in defaults with zero Copilot accounts.

### 查閱設計文件

```bash
# 總覽架構
cat docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md

# Stage 1 核心 daemon 規格
cat paulshaclaw/
```

### OpenSpec 工作流

```bash
# 提案新變更
/opsx:propose

# 套用現有變更
/opsx:apply

# 歸檔完成變更
/opsx:archive
```

### 配置說明

- `config/paulshaclaw-stage1.sample.json`：Stage 1 配置範本
- `config/worktrees/stage-worktrees.tsv`：Worktree 對照表

## Version

`VERSION` 檔為版號 single source of truth（語意版控依 `stage-driven` profile）。

**版號語意**：
- **MAJOR**：對外正式 release
- **MINOR**：階段功能穩定（stage landed）
- **PATCH**：累積 batch 計數
- **-fix.N**：落地後修補

目前版號：`0.0.0`（骨架建立中）

## 相關連結

- 規範引擎：[hamanpaul/paulsha-conventions](https://github.com/hamanpaul/paulsha-conventions)
- 帳號預設：[hamanpaul/.github](https://github.com/hamanpaul/.github)
