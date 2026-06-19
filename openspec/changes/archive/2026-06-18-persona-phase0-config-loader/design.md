## Context

persona catalog（`manager`/`builder`/`reviewer`）目前寫死於 `paulshaclaw/persona/contract.py` 的 `PERSONA_CATALOG`，`guardrail`/`context`/`shadow` 皆以它為預設來源。persona 模組目前**無任何 runtime 消費者**（孤島），故改 catalog 值在系統層無行為影響，僅影響直接斷言其值的單元測試。完整 5 階段設計見 `docs/superpowers/specs/2026-06-18-persona-dispatch-guardrail-design.md`；本 change 為 Phase 0。

## Goals / Non-Goals

**Goals:**
- catalog 由寫死改為 `personas.yaml` + loader（缺檔／解析失敗／schema 不過 → fail-closed）。
- 依多 agent 派工流程重定義三角色 `allowed_phases`／`write_paths`／`allowed_tools`（v2）。
- `guardrail`／`context`／`shadow` 公開 API 與判定邏輯不變；既有 stage4 測試維持綠（reviewer guardrail 行為不變）。

**Non-Goals:**
- ①②③ 護欄接線（Phase 1）、coordinator CLI（Phase 2）、CI 硬後盾（Phase 3）、fan-out（Phase 4）。
- 改 `PersonaContract` 欄位命名（`write_paths` 維持，不對齊既有 spec 文字的 `allowed_paths`／`role_id`／`handoff_targets` 用語——留 scope 外）。
- 改 guardrail／shadow 判定邏輯或新增 enforcement。

## Decisions

- **D1 — config 位置與覆寫**：預設 `paulshaclaw/persona/personas.yaml`（package-local，隨套件出貨，等價於原 catalog 宣告）；loader 支援路徑參數／環境變數覆寫，供日後 per-deployment 客製。理由：catalog 與模組強耦合，package-local 預設最簡且維持零行為改變；另案 `config/personas.yaml` 需現在就拉路徑 plumbing，否決。
- **D2 — loader 與 fail-closed**：新增 `paulshaclaw/persona/loader.py`，`load_catalog(path=None) -> dict[str, PersonaContract]`，經既有 `validate_persona_schema` 驗證；缺檔／解析失敗／schema 不過 → raise（fail-closed，呼應 Stage4 guardrail 慣例）。`contract.PERSONA_CATALOG` 改為 import 時由預設 `personas.yaml` 載入，**保持既有模組級匯出介面不變**（consumer 無感）。
- **D3 — 角色 v2 值變更**：`manager` 增 `openspec/**`、`runtime/handoff/**` 與 `git`／`gh`／`openspec` 工具；`builder` 增 `openspec/changes/archive/**` 與本地 `git add`／`git commit`（移除 push/PR）；`reviewer` 維持 `reports/review/**`。因無 runtime 消費者，系統層零影響，僅更新直接斷言 catalog 值的單元測試。
- **D4 — PyYAML**：已是 de-facto 相依（`cost`／`atomizer`／`janitor` 皆 import yaml；`requirements-stage9.txt` 列 `PyYAML>=6.0`），無新增相依。

## Risks / Trade-offs

- [既有測試直接斷言舊 catalog 值] → 屬單元斷言非 runtime 行為；隨 v2 一併更新，並以新 RED 測試覆蓋 v2 scope。
- [personas.yaml 與 `PersonaContract` 欄位漂移] → loader 走 `validate_persona_schema` + round-trip 測試擋。
- [package-local config 與三分式部署原則略有張力] → Phase 0 僅需「預設可運作」；override 路徑為日後 per-deployment 客製預留，本階段不啟用。
- [spec 文字用 `allowed_paths`/`role_id` 與 code 的 `write_paths`/`role` 既有漂移] → 本 change 的 delta spec 對齊 code 實況描述，但不改 code 欄位命名（避免破壞既有測試）。
