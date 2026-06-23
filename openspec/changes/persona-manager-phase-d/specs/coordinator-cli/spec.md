## ADDED Requirements

### Requirement: tick/fanout 支援 --allow-unsafe 與 --model

`coordinator-cli` 的 `tick` 與 `fanout` 子命令 SHALL 支援 `--allow-unsafe`（store_true）與 `--model <m>`。`--allow-unsafe` 為真時，建立的 `SubprocessLauncher` MUST 以 `allow_unsafe=True` 構建（放開各 executor 全自動旗標，headless 自主完成不掛）；預設 False。`--model` 設定時 MUST 傳入 `SubprocessLauncher(model=...)`，未設則為 None（各 executor 用預設 model）。注入 launcher（測試）時 MUST 尊重注入物、不覆寫。

#### Scenario: --allow-unsafe 建 allow_unsafe launcher

- **WHEN** 執行 `fanout`/`tick` 帶 `--executor copilot --allow-unsafe`（未注入 launcher）
- **THEN** 建立的 `SubprocessLauncher` MUST `allow_unsafe=True`

#### Scenario: --model 傳入 launcher

- **WHEN** 執行 `fanout`/`tick` 帶 `--executor copilot --model haiku-4.5`（未注入 launcher）
- **THEN** 建立的 `SubprocessLauncher` MUST 帶 `model="haiku-4.5"`
