## Why

Phase 1（archived `2026-06-18-persona-phase1-shadow-gate`）已交付 `persona.gate` 薄 CLI 與 verdict 邏輯（`build_verdict` / `evaluate_diff` / `compute_changed_paths`）＋ handoff manifest 讀寫（`handoff.read_manifest`），但 gate 仍是 **opt-in 本機 CLI**——沒有任何 CI 會在 PR 時自動把 diff 餵進 gate。設計 §8 的「自建硬後盾」要把 ② PR diff gate 接成 GitHub Actions workflow，作為 conventions 永遠做不到的那一層（conventions 只在 PR 時跑通用 rule，無法做 in-loop pre-push 軟回饋，也不認 persona scope）。

本 change 交付設計 §8 / §11 Phase 3 的 **shadow 形狀**：一支自我封裝的 CI runner `paulshaclaw/persona/scope_ci.py` ＋ 一個 `.github/workflows/persona-scope.yml`。**本階段刻意只到 shadow**：workflow 恆 exit 0、**非 required status check**、無 branch-protection 變更。真正翻 enforce（shadow→enforce）與自管豁免 label `policy-exempt:persona-scope` 為**文件化的未來手動步驟**（寫進本 proposal 與 design），本階段不啟用。

設計動機（§8 註）：in-loop 的 pre-push 軟 ②（§5）conventions 永遠做不到（它只在 PR 時跑），故硬後盾一定自建；而自建第一步必須是 shadow，先對真 PR 觀測、調 contract 至零誤殺，才談翻 enforce。

## What Changes

- 新增 `paulshaclaw/persona/scope_ci.py`：薄 CI runner，`main(argv=None, env=None) -> int`（`env` 可注入測試，預設讀 `os.environ`）。
  - **base 解析**：`origin/<GITHUB_BASE_REF>`（`GITHUB_BASE_REF` 預設 `main`）；**head 解析**：`GITHUB_SHA`（無則 `HEAD`）。
  - **manifest 探測**：找 `runtime/handoff/*.json` 中 **mtime 最新** 的一份；**找不到（常態）→ 印 `no manifest, skipped (shadow)` 通知並 return 0**（絕不報錯）。這是硬安全要求：絕大多數 PR（含本 Phase 3 PR 自身、其他 repo 的 PR）皆無 manifest，**必須照樣 pass**。
  - **有 manifest**：`handoff.read_manifest(manifest)` 取 `from_role` → reuse `gate.compute_changed_paths(base, head)` 取 diff（取 diff 失敗 fail-closed 但 **shadow 仍記錄並放行**）→ `gate.load_manifest_ok(...)` ＋ `gate.build_verdict(...)` 算 verdict → 印 verdict JSON（含 `mode: shadow`）。
  - **shadow 恆 return 0**：不論 verdict `ok` 真假、不論 diff 是否取得，shadow 模式恆 exit 0（observe/annotate-only）。判定邏輯**全 reuse** `gate.py`，**不重寫 scope 邏輯**。
- 新增 `.github/workflows/persona-scope.yml`：`on: pull_request`；checkout `fetch-depth: 0`（gate 需 base 與 head 的共同祖先）；setup Python 3.12；`pip install pytest -r requirements-stage9.txt`（取得 `PyYAML`，loader 載 `personas.yaml` 需要）；跑 `python -m paulshaclaw.persona.scope_ci`。**Shadow、恆 exit 0、非 required**。
- 新增測試 `tests/test_persona_phase3_scope_ci.py`：無 manifest → exit 0 ＋ `skipped` 通知；有合法 manifest ＋ in-scope diff（monkeypatch `gate.compute_changed_paths`）→ verdict `ok`、exit 0；out-of-scope diff → verdict 含 violations 但 **shadow 仍 exit 0**。全程注入 `env` ＋ monkeypatch git，**不依賴真 GitHub 環境**。
- 新增 `paulshaclaw/persona/__init__.py` 匯出 `scope_ci`。

## 文件化（本階段不啟用，未來手動步驟）

- **enforce 翻牌（shadow→enforce）**：待 shadow 對真 PR 觀測至零誤殺後，手動把 `scope_ci.main` 改吃 `--enforce`（或讀 `personas.yaml` 的 `enforcement: enforce`）使 verdict `ok=false` 時 exit 1，並在 repo branch protection 手動把 `persona-scope` 設為 **required status check**。此翻牌**僅文件化、不在本 change 執行**（branch-protection 變更為 repo 管理事務，非本 PR 範圍）。
- **豁免 label `policy-exempt:persona-scope`**：enforce 後，PR 掛此 label 時 gate 內部判讀為放行（與 conventions R-rule 框架平行、不相依）。本階段**僅文件化**，shadow 不需要也不讀此 label。

## Capabilities

### New Capabilities

<!-- 無新 capability；Phase 3 延伸既有 stage4 persona contract 能力（CI 硬後盾的 shadow 形狀） -->

### Modified Capabilities

- `stage4`: 新增 persona 派工護欄 ② 的 **CI 硬後盾 shadow 形狀**——`scope_ci.py`（解析 PR base/head、探測最新 handoff manifest、無 manifest 乾淨跳過、有 manifest 則 reuse `gate` verdict、shadow 恆 exit 0）＋ `persona-scope.yml`（`on: pull_request`、non-blocking、非 required）。reuse 既有 `gate` / `handoff` 判定邏輯，不引入 enforce、不改既有 workflow、不動 branch protection。

## Impact

- 代碼：新增 `paulshaclaw/persona/scope_ci.py`；新增 `.github/workflows/persona-scope.yml`；`paulshaclaw/persona/__init__.py` 匯出 `scope_ci`；新增 `tests/test_persona_phase3_scope_ci.py`。
- **僅新增（additive）**：MUST NOT 修改 `.github/workflows/tests.yml` 或 `.github/workflows/policy-check.yml`。
- 設計依據：`docs/superpowers/specs/2026-06-18-persona-dispatch-guardrail-design.md` §5 / §6 / §8 / §11（Phase 3）/ §13。
- 實作計畫：`docs/superpowers/plans/2026-06-18-persona-phase3-scope-gate.md`。
- 無 runtime 行為變更（新 workflow 恆 exit 0、非 required，對既有 merge 流程零影響）、無新增外部依賴（`git` 為既有前提；`PyYAML` 已在 `requirements-stage9.txt`）；`allowed_phases` 仍限 Stage3 canonical vocabulary。
