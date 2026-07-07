---
dispatch: hold
slice_id: p2-usability-phase0
plan: docs/superpowers/plans/2026-07-06-p2-usability-phase0.md
depends_on: []
---

# P2 — 易用性 Phase 0（拆包前的包內可用性） 設計

> 日期：2026-07-06 ｜ 狀態：草案（待覆審）｜ 對應：#125 評估補充 Phase 0、#91（env facade）
> 定位：**不動 repo 邊界**、不等站穩閘；既是易用性交付、也是 #125 拆包的解耦前置。交付形態：2 PR。

## 1. 背景

repo review（#125 評估補充）：功能完成度高，最弱面是易用性——`pyproject.toml` 零 `[project.scripts]`（入口全是 `python -m paulshaclaw.<pkg>.cli`）、`Path.home()` 散落 29 處無 facade（#91）、部分模組硬編碼個人路徑、版號治理死（`VERSION` 0.0.0 vs pyproject 0.1.0、0 tag）。

## 2. PR-A（S）：入口 + 版號 + 清殼

### 2.1 `psc` 傘狀 CLI
- `[project.scripts] psc = "paulshaclaw.cli:main"`；新增薄 dispatcher `paulshaclaw/cli.py`：
  - `psc memory …` → `paulshaclaw.memory.cli.main(argv)`（該 CLI 首參即 `memory`，直傳）
  - `psc coordinator …` → `paulshaclaw.coordinator.cli.main(argv)`
  - 其餘/未知子命令 → usage + exit 2。
- **零行為變更**：dispatcher 不解析業務參數、不注入預設值；`python -m` 舊入口保留不動。

### 2.2 版號治理（R-07 對齊）
- `VERSION` 0.0.0 → `0.1.0` 對齊 pyproject；打 tag `v0.1.0`（R-07：tag 與 VERSION 正規化後相等——去 `v` 前綴比對）。
- CI 一致性檢查：pytest 內加一測（讀 VERSION 與 pyproject 比對），不新增 workflow。

### 2.3 清空殼目錄
- 移除 `paulshaclaw/janitor/`、`paulshaclaw/chat/`（0 LOC 佔位）。
- **保留 `paulshaclaw/config/`**——PR-B facade 的家。

## 3. PR-B（M）：env facade（#91）+ LLM 後端收斂

### 3.1 facade：`paulshaclaw/config/paths.py`
- 提供：`repo_root() / memory_root() / agents_root() / config_root() / worktree_root()`。
- 解析序：對應 `PSC_*` env（如 `PSC_MEMORY_ROOT`）→ 既有慣例預設（`~/.agents/memory` 等 path-split 契約不變）。
- 遷移：29 處 `Path.home()` call site + `coordinator/seams.py` 與 `memory/importer/backfill.py` 的硬編碼預設，全改走 facade。
- **收編 P0-1 Stage A 的 2 個過渡 env**（extra corpus root）：facade 統一命名與讀取，Stage A 的佔位 env 名保留為別名一版後移除。
- facade 也補齊 helper：`notes_root()` / `state_path()` / `copilot_history_root()` / `max_root()` / `projects_config_path()`，讓 hooks 與 scripts 不必各自拼 `~/.agents/*`、`.copilot/*`。
- **相容規則**：`PSC_CONFIG_ROOT` 在 hook / importer 舊慣例中仍可當「home-like base root」供 `.copilot/history-session-state` 與 `.agents/config/projects.yaml` 推導；`config_root()` 本身仍代表 `~/.config/paulshaclaw` 契約預設。

### 3.2 LLM 後端收斂
- `agent_exec.command` config 既有（預設 `scripts/claude-gemma4`）：補文件（config 鍵、env 覆寫鏈、替換為任意 Anthropic-native／OpenAI-compatible endpoint 的步驟）。
- upstream URL env 命名保留（secret env 相容），讀取集中經 facade/config 層，移除散落的直接 `os.environ` 讀點。
- 讀取鏈定稿：
  1. `agent_exec.command`：`atomizer.yaml` → `~/.config/paulshaclaw/atomizer.override.yaml`
  2. `agent_exec.upstream_url`：`PSC_CLAUDE_GEMMA4_UPSTREAM_URL`（相容 env，設了就贏）→ override / default config → 內建預設
- 後端替換步驟：
  1. 在 override 檔改 `agent_exec.command` 指到新 wrapper / CLI。
  2. 需要不同 upstream 時，同步改 `agent_exec.upstream_url`；臨時切換則用 `PSC_CLAUDE_GEMMA4_UPSTREAM_URL`。
  3. `importer/title.py`、SkillOpt/atomizer/promoter 全部共用同一組設定，不再各自硬寫 command / URL。

### 3.3 依賴序
- P0-1 Stage A（2 處 env 化）→ PR-B（facade 收編）。PR-A 無依賴可先行。

## 4. 測試與驗收

- [ ] `pip install -e .` 後 `psc memory dream status` / `psc coordinator --help` 可用；`python -m` 舊入口不變。
- [ ] `Path.home()` **僅允許存在於 `paulshaclaw/config/paths.py`**（facade 本體）；其餘 `paulshaclaw/`（非 tests）直接呼叫點 = 0；`git grep '/home/'`（非 tests、非佔位）= 0。
- [ ] 假 `$HOME` + 自訂 `PSC_*` env 下 facade 單元測試綠；全套件回歸綠。
- [ ] 版號一致採**正規化 semver 比對**：pyproject version == `VERSION`（`0.1.0`），最新 tag 去 `v` 前綴後相等（R-07 語意，`v0.1.0` ≡ `0.1.0`）；一致性測試綠。
- [ ] 版號/tag 操作遵 R-07（禁非版本 tag）。

## 5. 風險

- facade 遷移面寬（29 處）：純機械替換但要防 import cycle——facade 僅依賴 stdlib，不 import 業務包。
- tag 推送屬對外動作：依慣例由 owner 執行或明確授權後代行。
- hooks 部署為複製模式：facade 檔案若被 hooks 引用，改動後需重跑 install 同步（既知坑，交付 checklist 註明）。
