## 1. TDD RED（先寫失敗測試）

- [ ] 1.1 新增 `tests/test_persona_phase3_scope_ci.py`，`NoManifestTests`：handoff 目錄為空 → `main(argv=[], env={...})` return 0 且輸出含 `skipped`（`scope_ci` 模組尚不存在 → RED）
- [ ] 1.2 同檔 `InScopeShadowTests`：寫合法 manifest（`from_role=builder`）+ monkeypatch `gate.compute_changed_paths` 回 in-scope 路徑（`paulshaclaw/...`）→ `main` 印 verdict `ok=true`、`violations=[]`、return 0
- [ ] 1.3 同檔 `OutOfScopeShadowTests`：合法 manifest + monkeypatch diff 回越界路徑（如 `docs/secret.md` 對 builder）→ verdict `ok=false`、`violations` 含該 path，但 shadow `main` **仍 return 0**
- [ ] 1.4 跑測試確認 RED 為「預期原因」（`ModuleNotFoundError: paulshaclaw.persona.scope_ci`），捕捉輸出為證據

## 2. 實作 scope_ci.py（CI runner，shadow 恆放行）

- [ ] 2.1 新增 `paulshaclaw/persona/scope_ci.py`：純函式 `resolve_base(env)`（`origin/{GITHUB_BASE_REF or 'main'}`）、`resolve_head(env)`（`GITHUB_SHA or 'HEAD'`）、`find_latest_manifest(repo_root)`（glob `runtime/handoff/*.json` 取 mtime 最新；空 → None）
- [ ] 2.2 `main(argv=None, env=None) -> int` 薄殼：解析 base/head/repo_root → `find_latest_manifest`；None → 印 `no manifest, skipped (shadow)` + return 0；否則 `handoff.read_manifest` 取 `from_role` → `gate.compute_changed_paths`（catch `RuntimeError` → `diff_error`）→ `gate.load_manifest_ok` + `gate.build_verdict` → `verdict['mode']='shadow'` → 印 JSON → **恆 return 0**
- [ ] 2.3 `__main__` 守衛呼 `sys.exit(main())`
- [ ] 2.4 RED → GREEN（三組測試全綠）

## 3. 實作 persona-scope.yml（shadow、non-blocking、非 required）

- [ ] 3.1 新增 `.github/workflows/persona-scope.yml`：`on: pull_request`；`permissions: contents: read`；`actions/checkout@v4` with `fetch-depth: 0`；`actions/setup-python@v5` `python-version: "3.12"`；`pip install --upgrade pip` + `pip install pytest -r requirements-stage9.txt`；run `python -m paulshaclaw.persona.scope_ci`
- [ ] 3.2 自我審查：workflow 恆 exit 0（runner 保證）、**未**宣告為 required、**未**含任何 branch-protection 變更；**未**改 `tests.yml`／`policy-check.yml`

## 4. 匯出與不回歸

- [ ] 4.1 `paulshaclaw/persona/__init__.py` 匯出 `scope_ci`
- [ ] 4.2 既有 `tests.test_stage4_persona_contract`、`tests.test_persona_config_loader`、`tests.test_persona_phase1_shadow_gate` 全綠（行為不變、純 reuse gate）
- [ ] 4.3 全套件 `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 綠（忽略既知 stage11 textual 環境失敗）

## 5. 驗證（設計 §11 Phase 3 獨立驗收 — shadow 部分）

- [ ] 5.1 `openspec validate persona-phase3-scope-gate --strict` 通過
- [ ] 5.2 本機模擬無 manifest PR：`runtime/handoff/` 為空時跑 `python -m paulshaclaw.persona.scope_ci`，確認印 `skipped (shadow)` 且 exit 0（最關鍵：無 manifest 必 pass）
- [ ] 5.3 本機模擬有 manifest PR：寫一份 manifest 後跑 runner，確認印 verdict JSON（`mode: shadow`）且**即使越界仍 exit 0**
- [ ] 5.4 確認 enforce 翻牌 + required check + `policy-exempt:persona-scope` label 皆**僅文件化於 proposal/design**，本 change 未啟用任何強制、未改 branch protection
