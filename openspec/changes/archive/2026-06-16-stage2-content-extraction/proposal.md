## Why

Stage 2 記憶中樞運行 8 天，管線骨架健康但**核心空心**：所有 inbox session 的 `## Summary`/`## Prompts`/`## Touched files` 皆為 `(none)`——記下了「session 發生過」卻沒擷取「session 做了什麼」。實機追蹤確認為一條三段斷鏈：(1) adapter 從不讀 `transcript_path`；(2) atomizer 因 project 含 `/` 被 `is_safe_path_component` 擋而 skip（`atomize.slices:0`）；(3) promoter 從未由 identity 切到 LLM。使用者要的「每 session ≤20 字標題」位於鏈末，須先通前兩段。

## What Changes

- 三家 adapter（claude/codex/copilot）**讀 transcript/history 擷取真內容**：`user_prompts`、`touched_files`，及供標題生成的 assistant 內容。
- importer 於 **import 當下**呼叫本機 gemma4 產每 session **≤20 字繁中標題**；gemma4 離線時 fallback（首條 prompt 截斷）並標 `title_source` 供日後補生。
- atomizer **不再因 URL 形 project 而 skip**：含 `/` 的 project 消毒成 path-safe 路徑元件（rich `project` 仍留 metadata），輔以 `~/.agents/config/projects.yaml` 補登活躍專案取乾淨 slug。
- 新增 `backfill.py`：對既有 `archive/queue/**` 三家強制重抽（繞 checksum dedup），具 `--dry-run`、可重入。
- **非本提案**：`promoter: identity → llm`（gemma4 原子蒸餾）留 Phase 2。

## Capabilities

### New Capabilities
- `stage2-session-content`: 捕捉到的 session 必須帶有真實內容（user prompts、touched files）與一條 per-session ≤20 字標題；atomizer 對任意 project 識別碼格式皆能蒸餾、不得靜默丟棄；既有 session 可回填。

### Modified Capabilities
<!-- 無：既有 stage2-memory-governance 僅規範「session 以 metadata 信封被 ingest」，未規範內容擷取與標題；本提案的需求為全新行為，故以新 capability 表達。 -->

## Impact

- **程式碼**（皆 editable 套件，改完下次 hook 觸發即生效，**不動 `~/.agents/memory/hooks/*` 部署副本、不必重跑 install.sh**）：
  - `paulshaclaw/memory/importer/adapters/base.py`（transcript reader helpers + `last_assistant_message`/`chatMessages` 鍵）
  - `importer/adapters/{claude,codex,copilot}.py`（接上 reader）
  - `importer/title.py`（新；gemma4 標題 + fallback）
  - `importer/backfill.py`（新；強制回填）
  - `atomizer/config.py` + `atomizer/pipeline.py`（`sanitize_project_component` + split/promote/knowledge 路徑改用消毒值）
- **設定**：`~/.agents/config/projects.yaml` 補登 serialwrap / OCP-0602 / arcadyan 等。
- **外部相依**：本機 gemma4 (:8001)——可選，離線有 fallback，CI 測試全程 mock。
- **測試**：`paulshaclaw/memory/tests/`（既有 CI `tests.yml` 執行，滿足 R-19）。
- **設計全文**：`docs/superpowers/specs/2026-06-16-stage2-content-extraction-design.md`。
