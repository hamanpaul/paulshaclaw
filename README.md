# paulshaclaw

個人 agent 工作流設計文件庫。本 repo 是 docs-first 設計庫，不是可部署的應用程式。

## 專案簡介

`paulshaclaw` 提供 PaulShiaBro 個人 agent 系統的設計文件、規格、research notes 及骨架配置。
實際 runtime 狀態與 secrets 分別存放於 `~/.agents/` 與 `~/.config/paulshaclaw/`。

### Stage 架構

**完整 Stage 統計**（狀態依據：`openspec/changes/archive/` 任務完成率 + 代碼存在與否）：

| Stage | 名稱 | 狀態 | archive tasks | 實作代碼 |
|-------|------|------|:------------:|:-------:|
| 0 | 前置工具 refine / rename / openspec 骨架 | **完成** | 13/13 | 腳本、yaml |
| 1 | PaulShiaBro core daemon + TUI + Telegram bot | **完成** | 15+13/15+13 | bot, core, tui |
| 2 | ~/.agents/memory 記憶中樞 + dream mode 24x7 | **spec 完成；Importer MVP 與 Security Policy 皆已落地** | 13/13；`stage2-memory-importer-mvp` 30/30；`stage2-memory-security-policy` 48/48 | routing.md, service.md, memory/{importer,policy,hooks}/（runtime 仍待 obs-auto-moc watcher 安全網串接） |
| 3 | Lifecycle（slash / artifact / phase gate） | **完成** | 9/9 | lifecycle/ |
| 4 | Persona（角色目錄 / handoff / guardrail） | **完成** | 11/11 | persona/ |
| 5 | 觀測 / 健康 / failover / 錯誤 log | **完成** | 9/9 | observability/ |
| 6 | 安全與機敏治理（ops-companion） | **完成** | 14/14 | security/ |
| 7 | 部署（core / state / secret 三分） | **完成** | 10/10 | deploy/ |
| 8 | Cost footer（token / Copilot budget） | **完成** | 21/21 | cost/ |
| 9 | Project Monitor（跨專案狀態同步） | **完成** | merged to main | monitor/ |
| 10 | 互通 / protocol 演進（socket / ACP / MCP） | **postponed** | — | — |
| 11 | Operator Cockpit（多 session pane 列表） | **MVP 完成** | multi-session 21/21；baseline scaffold 0/13 | cockpit/ |

**各 Stage 功能、邊界與啟用方式**（依據 `docs/research/05` §5.3、各 spec 及代碼）：

| Stage | 功能一句話 | 工作區域邊界 | 啟用方式 |
|-------|-----------|-----------|--------|
| 0 | 把地基的工具擦亮、對齊命名、補 Claude Code 支援 | skill/tool rename；ref-manifest；worktree helper；openspec 骨架 | `bash scripts/test-stage0-tooling-foundation.sh`<br>`bash scripts/sync-ref.sh`<br>`bash scripts/using-git-worktrees.sh <workstream>` |
| 1 | 把人類操作介面（TUI + Telegram）與控制核心做起來 | daemon / Telegram bot / TUI；registry；pane scanner；coordinator seam | 完整啟動（含 Stage 8/9/11）：`bash scripts/start.sh`<br>需設：`PSC_TELEGRAM_BOT_TOKEN` + `PSC_STAGE1_CONFIG`<br>單獨 daemon：`python3 -m paulshaclaw.core.daemon --config <path> --command /status`<br>單獨 bot：`python3 -m paulshaclaw.bot.listener [--config <path>]` |
| 2 | 把 agent 的記憶從散落收斂成分層可治理的結構 | inbox→work-centric→knowledge routing；janitor service boundary；obs-auto-moc 對接 | 由外部 obs-auto-moc systemd service 驅動：<br>`paulsha-memory-ingest.timer`（每 15 分鐘）<br>`paulsha-memory-janitor.timer`（每日 02:30）<br>驗證：`bash paulshaclaw/memory/tests/stage2_integration_check.sh` |
| 3 | 把「自然語言下指令」轉成「artifact-driven lifecycle」 | artifact frontmatter；lifecycle.yaml；phase gate；slash routes | artifact 靜態 gate 驗證：`python3 -m paulshaclaw.lifecycle.gate --artifact <path>`<br>測試套件：`python3 -m unittest tests.test_stage3_lifecycle_mvp -v` |
| 4 | 把「誰有資格做什麼」正式化成 persona contract | personas.yaml；guardrail；handoff；slice roster | Python library（無獨立 CLI）：<br>`from paulshaclaw.persona.guardrail import PersonaGuardrail`<br>測試套件：`python3 -m unittest tests.test_stage4_persona_contract -v` |
| 5 | 看得見、修得了、追得到錯誤 | health probes；supervisor；error log sink；chaos/recovery playbook | Python library（無獨立 CLI）：<br>`from paulshaclaw.observability.baseline import build_health_report`<br>測試套件：`python3 -m unittest tests.test_stage5_observability_recovery -v` |
| 6 | 該擋的動作擋住、該留的痕跡留下 | approval gate；secret redaction；audit trail；classification | Python library（無獨立 CLI）：<br>`from paulshaclaw.security.ops_companion import ApprovalGate, RedactionEngine`<br>測試套件：`python3 -m unittest tests.test_ops_companion_security -v` |
| 7 | 能從零台機器裝起來 | psc install / upgrade / uninstall；template rename；三軸部署分離 | `python3 -m paulshaclaw.deploy install`<br>`python3 -m paulshaclaw.deploy upgrade`<br>`python3 -m paulshaclaw.deploy uninstall` |
| 8 | token / Copilot 用量可見、可控 | cost snapshot；provider adapter；tmux footer；CLI | 一次性快照：`python3 -m paulshaclaw.cost --once`<br>tmux footer 狀態行：`python3 -m paulshaclaw.cost.status --plain`<br>（`scripts/start.sh` 自動掛入 tmux status-right） |
| 9 | 跨專案狀態對齊，供 Stage 1/3 作為 task source | monitor service；global config；read API（lock-based） | 常駐背景（由 `scripts/start.sh` 啟動）：`python3 -m paulshaclaw.monitor`<br>一次性掃描：`python3 -m paulshaclaw.monitor --once`<br>可選：`--config <path>` |
| 10 | 上線後強化跨 process 互通協定 | postponed：ACP / MCP / unix socket protocol | — |
| 11 | Operator 可跨 tmux session 統覽 pane 並切換 active slot | 多 session pane 聚合；active-slot swap；cockpit TUI | 需在 tmux 內執行（由 `scripts/start.sh` 自動啟動）：<br>`python3 -m paulshaclaw.cockpit --cockpit-pane $TMUX_PANE` |

**Stage 依賴與結合方式**（依據 `docs/research/05` §6）：

```
Stage 0 (工具)
    │ 硬依賴
    ▼
Stage 1 (daemon/TUI/bot) ←─軟─→ Stage 2 (memory)  ←── Stage 9 (monitor)
    │
    ├── Stage 3 (lifecycle) ──→ Stage 4 (persona)
    ├── Stage 5 (觀測)
    └── Stage 6 (安全)

Stage 7 (部署) 跨越所有 stage
Stage 11 (cockpit) 依賴 Stage 1
```

七大設計原則（詳見 `docs/research/05` §3）：
Hub-and-spoke · Artifact-first · Proposal-first · Fail-close · Stage 獨立性 · 三軸分層 · always-on 失敗域分離

詳細 Stage 設計見 [`docs/research/`](./docs/research/)。

**Stage 2 sub-spec**：
- Stage 2 — Memory Importer MVP（記憶基底 + Importer，hooks 三家 + obs-auto-moc watcher 安全網）
  - 設計規格：[`docs/superpowers/specs/2026-05-24-stage2-memory-importer-mvp-design.md`](./docs/superpowers/specs/2026-05-24-stage2-memory-importer-mvp-design.md)
  - OpenSpec change：[`openspec/changes/stage2-memory-importer-mvp/`](./openspec/changes/stage2-memory-importer-mvp/)（proposal / design / tasks / specs delta against `stage2-memory-governance`）
- Stage 2 — Memory Security Policy（Topic 8，記憶管理安全契約：redaction / classification / audit / policy enforcement）
  - 設計規格：[`docs/superpowers/specs/2026-05-24-stage2-memory-security-policy-design.md`](./docs/superpowers/specs/2026-05-24-stage2-memory-security-policy-design.md)
  - OpenSpec archive：[`openspec/changes/archive/2026-05-25-stage2-memory-security-policy/`](./openspec/changes/archive/2026-05-25-stage2-memory-security-policy/)（proposal / design / tasks / specs delta 已同步回 `stage2-memory-governance`）
- Stage 2 — Memory Atomizer/Linker（Topic 3，已落地）+ T3.2 LLM 語意晉升（規劃中）
  - T3 確定性 MVP（結構拆分 → 1:1 升級 → processing/relations ledger）：[`docs/superpowers/specs/2026-05-31-stage2-t3-atomizer-linker-design.md`](./docs/superpowers/specs/2026-05-31-stage2-t3-atomizer-linker-design.md)
  - T3.2 規劃：把 `Promoter` 換成 LLM 語意實作（per-session 語意拆分/合併 + tag + session 內/已知實體 relations；跨 session 演進脈絡與全域實體圖留 Topic 5）。
  - **LLM 後端決策（exec 模式）**：T3.2 不自造 API/SDK client，改為「**config 可設定、以 `exec` 叫起的 agent 命令**」當後端（預設 `scripts/claude-gemma4`，地端 vLLM，零 API、走訂閱/OAuth 由該 agent 自理）。此「configurable agent exec」與 paulshiabro `/agent` 共用——`/agent` 叫起 claude-gemma4 並串 Telegram 的路徑已抽成 config；`/agent start %pane`／`/agent startf %pane` 改為在呼叫端指定的既有 pane 啟動 agent（取代原本切新 pane，先驗證該 pane 為 idle shell、未被 claude/minicom 等佔用），作為 T3.2 前置。fail-closed：LLM 不可用則 session 留 `split`，dream 隔日重試。

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

`scripts/start.sh` applies the Stage 8 footer to the current tmux session with the configured `status-interval` from `tmux_refresh_seconds` (default `30`), and widens `status-right-length` so the full line is not clipped. The tmux footer renders with `--no-refresh` (cheap, cache-only); a lifecycle-bound **cost refresh loop** rebuilds the snapshot on the same cadence (disable with `PSC_COST_REFRESH_DISABLED=1`). Keeping the heavy collect off the per-interval tmux render is what stops it from piling up and OOM-ing the WSL VM. If `PAULSHACLAW_CONFIG` is set when `start.sh` runs, the same config path is passed into the tmux footer command. Copilot accounts are read from config; `accounts[].label` is the short footer alias (for example `haman`, `arc`). If no runtime config file exists, Stage 8 falls back to the bundled sample config.

> **footer 用量資料來源備註**
> - `cpt`（Copilot）顯示 plan 用量百分比（如 `haman:21%`，無上限的 business/enterprise 顯示 `arc:∞`），來自 `/copilot_internal/user` 的 `quota_snapshots.premium_interactions`（與 Copilot CLI statusline 同源，單次 HTTP GET、不掃本地 log）。label 來自 `cost.providers.copilot.accounts[].label`；若 quota 取不到，後備為本地 `events.jsonl` 的計數（已加 mtime／檔案大小邊界，避免掃描歸檔大檔當機）。
> - `cc`（Claude Code）trusted source 是 `~/.agents/state/cost/claude_rate_limits.json` sidecar；若沒有這個檔案，就只會顯示 `--` 或 estimated fallback。
> - `cdx`（Codex）trusted source 預設已啟用，優先讀本地最新 session 的 `payload.rate_limits`（network endpoint 常回 403），顯示 5h／weekly 用量。

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
