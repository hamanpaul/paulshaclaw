## Why

Stage 4 persona 模組測試完備（11/11）卻從未通電：`PERSONA_CATALOG` 寫死在 `contract.py`、與實際多 agent 派工流程的角色邊界對不上，README 宣稱的 `personas.yaml` 也不存在。要把 persona 接成 CLAUDE.md `multi_agent_devflow` / `scope_violation` 的強制機制，第一步須先把 catalog config 化並依派工流程重定義三角色——這是後續 ①②③ 護欄、coordinator CLI、CI 硬後盾的基礎（見設計 §11 Phase 0）。

## What Changes

- 新增 `paulshaclaw/persona/personas.yaml`：以 config 宣告 `manager`/`builder`/`reviewer` 三角色契約，取代 `contract.py` 寫死的 `PERSONA_CATALOG`。
- 新增 loader：讀 `personas.yaml` → `dict[str, PersonaContract]`，經既有 `validate_persona_schema` 驗證；缺檔／非法 **fail-closed**（沿用 Stage4 guardrail fail-closed 慣例）。
- 依多 agent 派工流程**重定義三角色 scope/tools（v2）**：
  - `manager`：`write_paths` = `docs/**`、`openspec/**`、`lifecycle.yaml`、`runtime/handoff/**`；`allowed_tools` = `coordinator.dispatch`、`coordinator.handoff`、`git`、`gh`、`openspec`、`python -m unittest`。
  - `builder`：`write_paths` = `paulshaclaw/**`、`tests/**`、`openspec/changes/archive/**`；`allowed_tools` = `python -m unittest`、`rg`、`edit`、`git add`、`git commit`（✗ `git push`／`gh pr`）。
  - `reviewer`：`write_paths` = `reports/review/**`；`allowed_tools` = `python -m unittest`、`rg`（✗ 改 code）。
- **零行為改變**：`guardrail` / `context` / `shadow` 公開 API 不變；`personas.yaml` 沿用既有 `PersonaContract` 欄位（`role`/`version`/`summary`/`allowed_phases`/`write_paths`/`allowed_tools`），不改 code 欄位命名（避免 scope 外破壞既有測試）。

## Capabilities

### New Capabilities

<!-- 無；Phase 0 不引入新 capability，僅修改既有 stage4 -->

### Modified Capabilities

- `stage4`: persona catalog 由寫死 Python 改為 config-driven（`personas.yaml` + loader，缺檔／非法 fail-closed）；`manager`/`builder`/`reviewer` 三角色的 `allowed_phases`／`write_paths`／`allowed_tools` 依多 agent 派工流程重定義。

## Impact

- 代碼：`paulshaclaw/persona/contract.py`（catalog 來源改 loader）、新增 `paulshaclaw/persona/personas.yaml`＋loader 模組、`tests/`（補 config round-trip 與 v2 scope 測試）。
- 設計依據：`docs/superpowers/specs/2026-06-18-persona-dispatch-guardrail-design.md` §4 / §11。
- 無 runtime 行為變更、無新增外部依賴；`allowed_phases` 仍限 Stage3 canonical vocabulary（`research`/`define`/`plan`/`build`/`verify`/`review`/`ship`）。
