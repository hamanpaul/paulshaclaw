## 1. TDD RED

- [ ] 1.1 寫失敗測試：config 含 `kind: company` 帳號 id 為任意值（如 `acme-co`）+ 注入本地觀測 AIU>0、無 fetcher → 斷言該 AIU 以 `source=local_observed` 歸屬到 `acme-co`（現硬編碼 `"org-a"` → RED：被過濾掉、無此帳號用量）
- [ ] 1.2 寫失敗測試：config 含 `kind: personal` 帳號 `me` + 本地觀測 premium>0 → 歸屬到 `me`
- [ ] 1.3 寫失敗測試：config 無 `company` 帳號 + AIU>0 → 不歸屬、不報錯
- [ ] 1.4 跑測試確認 RED 為預期原因

## 2. 實作 config-driven 歸屬

- [ ] 2.1 新增 `_resolve_attribution_accounts(config) -> tuple[str|None,str|None]`（premium=第一個 personal id、aiu=第一個 company id）
- [ ] 2.2 改 `_collect_local_observed_usage(premium_account, aiu_account, allowed_accounts=None)`：依參數 key，`None` 則略過該類
- [ ] 2.3 呼叫點（`collect_copilot` L884）先 `_resolve_attribution_accounts(config)` 再帶入
- [ ] 2.4 移除 `_COPILOT_PREMIUM_ACCOUNT` / `_COPILOT_AIU_ACCOUNT` 常數、更新註解
- [ ] 2.5 RED→GREEN

## 3. 不回歸 + 驗證

- [ ] 3.1 既有 `tests/test_stage8_cost.py` 全綠（必要時更新為 config-driven 預期）
- [ ] 3.2 全套件 `pytest tests/ paulshaclaw/memory/tests/ -q` 綠（除既有 cockpit env 2 例）
- [ ] 3.3 `openspec validate stage8-aiu-attribution-config-driven --strict` 通過
- [ ] 3.4 確認公開碼無真實 org/帳號名（grep 無硬編碼帳號常數）
