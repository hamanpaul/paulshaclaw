## Why

去識別化把 `cost/providers.py` 硬編碼的 `_COPILOT_AIU_ACCOUNT`（原為真實公司 org）換成佔位 `"org-a"`，但**沒 config 化**。Stage 8 footer 的本地觀測 AIU 以此常數為 key（`_collect_local_observed_usage`），再被 `collect_copilot` 以「設定檔帳號 id」（`allowed_account_ids`）過濾——佔位 `"org-a"` ≠ 線上真實公司帳號 → **公司帳號的 local-observed AIU 被濾掉/掉資料**（去識別化造成的行為漂移）。Stage 8 spec 本就要求 MUST NOT hardcode 帳號。

## What Changes

- 移除硬編碼 `_COPILOT_PREMIUM_ACCOUNT` / `_COPILOT_AIU_ACCOUNT` 常數。
- 從 config 解析歸屬目標：premium → 第一個 `kind: personal` 帳號 id；AIU → 第一個 `kind: company` 帳號 id。
- `_collect_local_observed_usage` 改收 `premium_account` / `aiu_account` 參數（由呼叫點從 `CostConfig` 帶入）；缺對應 kind 帳號時該類用量略過。
- 行為：本地觀測 premium/AIU 歸屬到**設定檔實際帳號**；公開碼不再含任何真實 org/帳號名。

## Capabilities

### New Capabilities

<!-- 無 -->

### Modified Capabilities

- `stage8-cost-footer`: 本地觀測 premium/AIU 歸屬 SHALL 為 config-driven（依 `personal`/`company` kind 解析帳號 id），MUST NOT 硬編碼帳號識別字。

## Impact

- 代碼：`paulshaclaw/cost/providers.py`（移除常數、加 config 解析 helper、改 `_collect_local_observed_usage` 簽名 + 呼叫點 L884）、`tests/test_stage8_cost.py`（補 config-driven 歸屬測試）。
- 無對外 API 變更；修復去識別化造成的 local-AIU 歸屬漂移，並滿足既有「MUST NOT hardcode」要求。
