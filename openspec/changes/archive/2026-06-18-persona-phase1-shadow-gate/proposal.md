## Why

Phase 0 已把 persona catalog config 化（`personas.yaml` + loader）並依派工流程重定義三角色，但 persona 仍是**未通電的孤島**——沒有任何 runtime 路徑會把契約 render 進 prompt、也沒有任何閘門會拿 PR diff 去比對角色 scope。設計 §11 的 Phase 1 要在「不強制」的前提下先把三個強制點（①派工 contract render、②PR diff gate、③merge 前終檢）的**觀測形狀**接出來，採 Stage 2 promoter 同套 shadow→enforce canary：先 shadow（恆放行、只輸出 verdict）跑真 PR、調 contract 至零誤殺，再翻 enforce。

本 change 交付 Phase 1 的三個 building block：handoff manifest 的讀寫（角色身分載體，§6）、契約 render 成 prompt 前言（①，§5）、shadow diff-gate CLI（②，§5/§8）。皆 reuse 既有 `contract` / `guardrail` / `context` / `loader` API，不重寫判定邏輯。

## What Changes

- 新增 `paulshaclaw/persona/handoff.py`：`write_manifest(path, payload)` / `read_manifest(path)`，落地 §6 的 `runtime/handoff/<slice_id>.json`。`read_manifest` 經既有 `contract.validate_handoff_message` 驗證，非法 → `ValueError`；缺檔 **fail-closed**（沿用 Stage4 / loader fail-closed 慣例）。
- 新增 `paulshaclaw/persona/render.py`：`render_contract_prompt(role, catalog=None, overlay=None) -> str`，reuse `context.build_persona_context` 算出契約，輸出**確定性**的 prompt 前言（宣告 role / allowed_phases / write_paths / effective_tools，即 ① contract 注入）；未知 role → `ValueError`。
- 新增 `paulshaclaw/persona/gate.py`：薄 CLI `python -m paulshaclaw.persona.gate --role R --base main --head BR --manifest PATH [--enforce]`。以 `git diff --name-only <base>...<head>` 取變更檔，逐檔 `guardrail.evaluate_filesystem(role, path)`，並驗 handoff manifest；輸出 JSON verdict `{role, changed_paths, violations:[{path,reason}], handoff_ok, ok}`。**預設 shadow → 恆 exit 0（觀測/記錄）**；`--enforce` 時 `ok` 為 false → exit 1。catalog 走 `loader.load_catalog()`。
- 新增測試覆蓋：manifest round-trip + 非法/缺檔 fail-closed；render 輸出含角色 scope；gate 對 in-scope vs out-of-scope diff 的 verdict；shadow 恆 exit 0 vs enforce exit 1。
- **Phase 1 為 shadow-only**：runtime 無強制；gate 為 opt-in CLI。不接 coordinator dispatch（Phase 2）、不建 CI workflow（Phase 3）。

## Capabilities

### New Capabilities

<!-- 無新 capability；Phase 1 延伸既有 stage4 persona contract 能力 -->

### Modified Capabilities

- `stage4`: 新增 persona 派工護欄的 shadow 形狀——handoff manifest 讀寫（fail-closed）、contract render prompt 前言（①）、shadow diff-gate CLI（②，恆放行可翻 enforce）。皆 reuse 既有判定邏輯，不引入 runtime 強制。

## Impact

- 代碼：新增 `paulshaclaw/persona/{handoff,render,gate}.py`；`paulshaclaw/persona/__init__.py` 匯出新模組；新增 `tests/test_persona_phase1_shadow_gate.py`。
- 設計依據：`docs/superpowers/specs/2026-06-18-persona-dispatch-guardrail-design.md` §5 / §6 / §8 / §11（Phase 1）。
- 實作計畫：`docs/superpowers/plans/2026-06-18-persona-phase1-shadow-gate.md`。
- 無 runtime 行為變更（gate 為 opt-in CLI、預設 shadow 恆 exit 0）、無新增外部依賴（`git` 為既有前提）；`allowed_phases` 仍限 Stage3 canonical vocabulary。
