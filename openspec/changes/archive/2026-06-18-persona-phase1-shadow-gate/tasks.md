## 1. TDD RED（先寫失敗測試）

- [ ] 1.1 新增 `tests/test_persona_phase1_shadow_gate.py`，`HandoffManifestTests`：round-trip、非法 manifest raise、缺檔 raise（`handoff` 模組尚不存在 → RED）
- [ ] 1.2 同檔 `RenderContractPromptTests`：輸出含 role 名與各 write_path 子字串、未知 role raise `ValueError`（`render` 模組尚不存在 → RED）
- [ ] 1.3 同檔 `GateVerdictTests`：in-scope diff → `violations` 空 + `ok` true；out-of-scope diff → `violations` 含 path/reason + `ok` false（monkeypatch `compute_changed_paths`）（`gate` 模組尚不存在 → RED）
- [ ] 1.4 同檔 `GateExitCodeTests`：越界 diff shadow `main` 回 0、`--enforce` 回 1；in-scope 兩模式回 0
- [ ] 1.5 跑測試確認 RED 為「預期原因」（缺模組／缺屬性），捕捉輸出為證據

## 2. 實作 handoff.py（manifest 讀寫，read fail-closed）

- [ ] 2.1 新增 `paulshaclaw/persona/handoff.py`：`write_manifest(path, payload: dict)`（`mkdir -p` 父目錄、`json.dump`）、`read_manifest(path)`（缺檔 raise；讀 JSON；委派 `contract.validate_handoff_message`，非法 raise `ValueError`）
- [ ] 2.2 RED → GREEN（`HandoffManifestTests`）

## 3. 實作 render.py（① contract 注入）

- [ ] 3.1 新增 `paulshaclaw/persona/render.py`：`render_contract_prompt(role, catalog=None, overlay=None) -> str`，reuse `context.build_persona_context`，組確定性多行前言（role / allowed_phases / write_paths / effective_tools）；未知 role 由 `build_persona_context` 冒泡 `ValueError`
- [ ] 3.2 RED → GREEN（`RenderContractPromptTests`）

## 4. 實作 gate.py（② shadow diff-gate CLI）

- [ ] 4.1 新增 `paulshaclaw/persona/gate.py`：純函式 `compute_changed_paths(base, head, repo=None)`（`git diff --name-only base...head`，非零 returncode fail-closed）、`evaluate_diff(role, changed_paths, catalog)`、`load_manifest_ok(role, manifest_path, catalog)`、`build_verdict(...)`
- [ ] 4.2 `main(argv=None)` 薄殼：argparse（`--role/--base/--head/--manifest/--enforce`）、`load_catalog()`、組 verdict、`print(json.dumps(verdict))`；shadow 恆 return 0、`--enforce` 時 `0 if ok else 1`；`__main__` 呼 `sys.exit(main())`
- [ ] 4.3 RED → GREEN（`GateVerdictTests`、`GateExitCodeTests`）

## 5. 匯出與不回歸

- [ ] 5.1 `paulshaclaw/persona/__init__.py` 匯出 `handoff`、`render`、`gate`
- [ ] 5.2 既有 `tests.test_stage4_persona_contract`、`tests.test_persona_config_loader` 全綠（行為不變）
- [ ] 5.3 全套件 `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 綠（忽略 2 個既知 stage11 textual 環境失敗）

## 6. 驗證

- [ ] 6.1 `openspec validate persona-phase1-shadow-gate --strict` 通過
- [ ] 6.2 對一個真 PR/分支跑 `python -m paulshaclaw.persona.gate ...`，確認輸出 verdict 且 shadow 恆 exit 0（設計 §11 Phase 1 獨立驗收）
