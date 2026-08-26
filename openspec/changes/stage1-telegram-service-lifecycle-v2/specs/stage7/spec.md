## MODIFIED Requirements

### Requirement: Template 檔清單與 rename 規則

Stage 7 MUST 維護三分部署 template 清單，至少覆蓋：
- core systemd unit
- core env
- Telegram systemd unit
- Telegram runtime env
- state config
- secret bootstrap env
- Telegram secret env

Template rename 規則 MUST 支援 `__INSTANCE__` 取代為實例名，且 MUST 移除 `.tmpl` 後綴，讓目標檔名可直接落到部署目錄。Telegram systemd unit 的目標檔名 MUST 使用 `<instance>-telegram.service`，以便獨立 restart bot listener 而不重啟 core service。

#### Scenario: template 資產涵蓋 core/state/secret 與 Telegram service

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage7_deploy_three_plane.TemplateMappingTests -v`
- **THEN** 測試 MUST 驗證 template 清單至少含七個檔案、plane 集合為 `core/state/secret`，且每個 template 實體檔案存在

#### Scenario: rename 規則可產生最終目標檔名

- **WHEN** 操作者以 `core/systemd/__INSTANCE__.service.tmpl` 套用 instance `demo-agent`
- **THEN** 目標路徑 MUST 轉成 `core/systemd/demo-agent.service`

#### Scenario: Telegram unit rename 規則產生獨立 service 名稱

- **WHEN** 操作者以 `core/systemd/__INSTANCE__-telegram.service.tmpl` 套用 instance `demo-agent`
- **THEN** 目標路徑 MUST 轉成 `core/systemd/demo-agent-telegram.service`
