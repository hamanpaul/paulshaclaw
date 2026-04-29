# paulshaclaw

個人 agent 工作流設計文件庫。本 repo 是 docs-first 設計庫，不是可部署的應用程式。

## 專案簡介

`paulshaclaw` 提供 PaulShiaBro 個人 agent 系統的設計文件、規格、research notes 及骨架配置。
實際 runtime 狀態與 secrets 分別存放於 `~/.agents/` 與 `~/.config/paulshaclaw/`。

### Stage 架構

| Stage | 名稱 | 狀態 |
|-------|------|------|
| 0 | 工具骨架（OpenSpec + Superpowers） | 完成 |
| 1 | PaulShiaBro daemon / TUI / Telegram bot | 進行中 |
| 2 | `obs-auto-moc` 記憶基底 | 規劃中 |
| 3 | Slash-command lifecycle 與 artifacts | 規劃中 |
| 4 | Persona 合約與 handoff 護欄 | 規劃中 |

完整 Stage 清單見 [`docs/`](./docs/)。

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

`scripts/start.sh` applies the Stage 8 footer to the current tmux session with `status-interval 30`. Copilot accounts are read from real config; account labels and request allowances are not hardcoded. If no runtime config file exists, Stage 8 falls back to built-in defaults with zero Copilot accounts.

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
