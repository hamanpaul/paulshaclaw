## 1. TDD RED（先寫失敗測試）

- [x] 1.1 寫失敗測試：`load_catalog()` 載入預設 `personas.yaml` → 含三角色且通過 `validate_persona_schema`（loader／yaml 尚不存在 → RED）
- [x] 1.2 寫失敗測試：缺檔／解析失敗／schema 不過 → loader raise（fail-closed），不回傳空／部分 catalog
- [x] 1.3 寫失敗測試：v2 scope 斷言——`manager` 可寫 `openspec/**`、`builder` 可寫 `openspec/changes/archive/**` 且 `allowed_tools` 無 `git push`、`reviewer` 僅可寫 `reports/review/**`
- [x] 1.4 跑測試確認 RED 為「預期原因」（缺模組／缺檔），捕捉輸出為證據

## 2. 實作 personas.yaml + loader

- [x] 2.1 新增 `paulshaclaw/persona/personas.yaml`：`manager`／`builder`／`reviewer` 三角色 v2 契約（欄位沿用 `PersonaContract`：`role`/`version`/`summary`/`allowed_phases`/`write_paths`/`allowed_tools`）
- [x] 2.2 新增 `paulshaclaw/persona/loader.py`：`load_catalog(path=None) -> dict[str, PersonaContract]`，reuse `validate_persona_schema`，缺檔／非法 fail-closed（raise）
- [x] 2.3 `contract.py`：`PERSONA_CATALOG` 改為 import 時由預設 `personas.yaml` 載入，保持模組級匯出介面不變（`guardrail`/`context`/`shadow` consumer 無感）
- [x] 2.4 RED → GREEN

## 3. 不回歸 + 驗證

- [x] 3.1 既有 `tests.test_stage4_persona_contract` 全綠（reviewer guardrail 行為不變）
- [x] 3.2 全套件 `pytest tests/ paulshaclaw/memory/tests/ -q` 綠（沿用 CI 指令）
- [x] 3.3 `openspec validate persona-phase0-config-loader --strict` 通過、status apply-complete
