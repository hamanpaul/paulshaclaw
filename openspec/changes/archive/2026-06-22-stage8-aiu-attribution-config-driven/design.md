## Context

`paulshaclaw/cost/providers.py` 以模組常數 `_COPILOT_PREMIUM_ACCOUNT="hamanpaul"`、`_COPILOT_AIU_ACCOUNT="org-a"`（去識別化後）作為本地觀測用量的歸屬 key。`_collect_local_observed_usage(allowed_accounts)`（L810）把 premium/AIU 分別 key 到這兩個常數，再於呼叫點（L884 `collect_copilot`）以 `allowed_account_ids = {a.account_id for a in config.copilot_accounts}` 過濾。常數 `"org-a"` 是去識別化佔位，與線上真實公司帳號不符 → 公司 local-AIU 被濾掉。`CopilotAccountConfig` 有 `kind ∈ {personal, company}`。

## Goals / Non-Goals

**Goals:**
- 本地觀測 premium/AIU 歸屬改為 config-driven（premium→personal 帳號、AIU→company 帳號），移除硬編碼帳號常數。
- 公開碼不含真實 org/帳號名；runtime 由 config 取真值。
- 既有 Stage 8 測試維持綠；無對外行為/格式變更（除修正歸屬正確性）。

**Non-Goals:**
- 不改 config schema、不改 fetcher / 配額端點邏輯、不動其他 provider（cdx/cc）。
- 不處理「多個 personal/company 帳號」的複雜分配（取第一個對應 kind 即可，符合現行單公司/單個人假設）。

## Decisions

- **D1 — 解析來源**：新增 helper `_resolve_attribution_accounts(config) -> (premium_id|None, aiu_id|None)`：premium = 第一個 `kind=="personal"` 帳號 id；aiu = 第一個 `kind=="company"` 帳號 id。理由：沿用既有 `kind` 語義（premium-request↔personal、AIU↔company），零新 config 欄位。
- **D2 — 函式簽名**：`_collect_local_observed_usage(premium_account, aiu_account, allowed_accounts=None)`；`premium/aiu_account` 為 `None` 時該類用量略過（不 key 到不存在帳號）。呼叫點 L884 先 `_resolve_attribution_accounts(config)` 再帶入。
- **D3 — 移除常數**：刪 `_COPILOT_PREMIUM_ACCOUNT` / `_COPILOT_AIU_ACCOUNT`，更新註解（attribution 規則改述為「premium→personal、AIU→company，由 config 決定」）。

## Risks / Trade-offs

- [既有測試直接斷言常數行為] → 既有 `test_stage8_cost.py` 多以 config 帳號（含一個 company）+ observed 驗證，config-driven 後歸屬到該 company 帳號 id，行為一致；逐項更新並補新測試。
- [多帳號同 kind] → 取第一個；現行單公司/單個人假設下無歧義；以註解標明。
- [缺對應 kind 帳號] → 略過該類本地觀測（fail-safe，不歸屬到不存在帳號、不報錯）。
