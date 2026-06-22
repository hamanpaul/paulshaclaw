## ADDED Requirements

### Requirement: 本地觀測 premium/AIU 歸屬為 config-driven

Stage 8 SHALL 將本地觀測（local_observed）的 premium-request 與 AIU 用量歸屬到「設定檔中對應 `kind` 的帳號 id」——premium-request → 第一個 `kind: personal` 帳號、AIU → 第一個 `kind: company` 帳號——且 MUST NOT 硬編碼任何帳號識別字。當設定檔缺對應 `kind` 的帳號時，該類本地觀測用量 SHALL 略過（不歸屬到不存在的帳號、不報錯）。

#### Scenario: AIU 歸屬到設定的公司帳號

- **WHEN** 設定檔含一個 `kind: company` 帳號 id `X`，且本地觀測 AIU > 0、無 fresh 來源
- **THEN** footer SHALL 把該 AIU 以 `source=local_observed` 歸屬到帳號 `X`（而非任何硬編碼常數）

#### Scenario: premium 歸屬到設定的個人帳號

- **WHEN** 設定檔含一個 `kind: personal` 帳號 id `Y`，且本地觀測 premium > 0、無 fresh 來源
- **THEN** footer SHALL 把該 premium 歸屬到帳號 `Y`

#### Scenario: 無對應 kind 帳號則略過

- **WHEN** 設定檔無 `kind: company` 帳號，且本地觀測 AIU > 0
- **THEN** 該 AIU SHALL 不被歸屬到任何帳號（略過，不報錯）
