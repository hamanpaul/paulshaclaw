## ADDED Requirements

### Requirement: Persona-scope CI runner 在無 manifest 時乾淨跳過

Stage4 SHALL 提供 CI runner `paulshaclaw/persona/scope_ci.py`，入口 `main(argv=None, env=None) -> int`（`env` 可注入測試，預設 `os.environ`）。runner MUST 探測 `runtime/handoff/*.json` 中 mtime 最新的一份；當**完全找不到** handoff manifest 時，runner MUST 印出帶 `skipped` 字樣的 shadow 跳過通知並 return 0，MUST NOT raise 或回傳非零。此為硬安全要求：絕大多數 PR（含本 change 自身與其他 repo PR）皆無 manifest，MUST 照樣 pass。

#### Scenario: 無 manifest 乾淨跳過並 exit 0

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase3_scope_ci.NoManifestTests -v`
- **THEN** 測試 MUST 驗證在 handoff 目錄為空（或不存在）時 `main` return 0，且輸出含 `skipped`，MUST NOT raise

### Requirement: Persona-scope CI runner 解析 PR base/head 並 reuse gate verdict

Stage4 的 `scope_ci.main` MUST 由注入的 `env` 解析 base = `origin/<GITHUB_BASE_REF>`（`GITHUB_BASE_REF` 缺省 `main`）與 head = `GITHUB_SHA`（缺省 `HEAD`）。當存在 handoff manifest 時，runner MUST 經 `handoff.read_manifest` 取 `from_role`，並 reuse `gate.compute_changed_paths` / `gate.load_manifest_ok` / `gate.build_verdict` 算出 verdict（`{role, changed_paths, violations, handoff_ok, ok}` 加 `mode`），MUST NOT 重寫 scope 判定邏輯。runner MUST 印出 verdict JSON。當 diff 取得失敗（`compute_changed_paths` raise）時，runner MUST fail-closed 標記（`diff_error` + `ok=false`）但於 shadow 模式仍 return 0。

#### Scenario: in-scope diff 在 shadow 下 verdict ok 且 exit 0

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase3_scope_ci.InScopeShadowTests -v`
- **THEN** 測試 MUST 以注入 `env` ＋ monkeypatch `gate.compute_changed_paths` 提供合法 manifest 與符合角色 write scope 的變更檔，驗證 `main` 印出 `violations` 為空、`ok` 為 true 的 verdict 且 return 0

### Requirement: Persona-scope CI runner 為 shadow 且恆放行（non-blocking）

Stage4 的 `scope_ci.main` 於 shadow 模式 MUST 恆 return 0（observe/annotate-only），不論 verdict `ok` 為真或假、不論 diff 是否取得成功。對應的 `.github/workflows/persona-scope.yml` MUST 為 `on: pull_request`、non-blocking、且 MUST NOT 被設為 required status check（branch-protection 翻牌為文件化的未來手動步驟）。enforce 模式（verdict `ok=false` 時 exit 非零）與自管豁免 label `policy-exempt:persona-scope` 於本階段 MUST 僅文件化、MUST NOT 啟用。本 change MUST NOT 修改 `.github/workflows/tests.yml` 或 `.github/workflows/policy-check.yml`。

#### Scenario: out-of-scope diff 在 shadow 下顯示 violations 但仍 exit 0

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase3_scope_ci.OutOfScopeShadowTests -v`
- **THEN** 測試 MUST 以注入 `env` ＋ monkeypatch `gate.compute_changed_paths` 提供合法 manifest 與越界變更檔，驗證 `main` 印出含該越界 path 的 `violations`、`ok` 為 false 的 verdict，但 shadow 模式 `main` 仍 return 0

#### Scenario: workflow 為 shadow non-blocking 且未改既有 workflow

- **WHEN** 審查者檢視 `.github/workflows/persona-scope.yml` 與既有 `.github/workflows/{tests,policy-check}.yml`
- **THEN** `persona-scope.yml` MUST 為 `on: pull_request`、跑 `python -m paulshaclaw.persona.scope_ci`、不設為 required、不含 branch-protection 變更；且既有兩個 workflow MUST 維持未被修改
