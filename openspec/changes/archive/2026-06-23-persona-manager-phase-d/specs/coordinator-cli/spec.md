## ADDED Requirements

### Requirement: tick/fanout 支援 --allow-unsafe 與 --model

`coordinator-cli` 的 `tick` 與 `fanout` 子命令 SHALL 支援 `--allow-unsafe`（store_true）與 `--model <m>`。`--allow-unsafe` 為真時，建立的 `SubprocessLauncher` MUST 以 `allow_unsafe=True` 構建（放開各 executor 全自動旗標，headless 自主完成不掛）；預設 False。`--model` 設定時 MUST 傳入 `SubprocessLauncher(model=...)`，未設則為 None（各 executor 用預設 model）。注入 launcher（測試）時 MUST 尊重注入物、不覆寫。

#### Scenario: --allow-unsafe 建 allow_unsafe launcher

- **WHEN** 執行 `fanout`/`tick` 帶 `--executor copilot --allow-unsafe`（未注入 launcher）
- **THEN** 建立的 `SubprocessLauncher` MUST `allow_unsafe=True`

#### Scenario: --model 傳入 launcher

- **WHEN** 執行 `fanout`/`tick` 帶 `--executor copilot --model haiku-4.5`（未注入 launcher）
- **THEN** 建立的 `SubprocessLauncher` MUST 帶 `model="haiku-4.5"`

### Requirement: --allow-unsafe fail-closed 綁定就緒集大小

因 `--allow-unsafe` 旁路各 executor 的沙箱/核可，`tick`/`fanout` 在 `--allow-unsafe` 為真時 MUST fail-closed：就緒集（`ready_units`）大於 1 個 slice 時 MUST 拒絕派工並以非零退出（avoid 一次對多個 slice 大量自主越權派工，例如誤指 specs-dir 或真實 specs 含多個 `dispatch:auto`）。`--allow-unsafe` 未設時不施此限。

#### Scenario: unsafe + 多就緒 slice 拒絕

- **WHEN** `--allow-unsafe` 為真且就緒集含 ≥2 個 slice
- **THEN** MUST 以錯誤退出（exit 1），MUST NOT 派工任何 slice

#### Scenario: unsafe + 單一就緒 slice 放行

- **WHEN** `--allow-unsafe` 為真且就緒集恰為 1 個 slice（canary）
- **THEN** MUST 正常派工該 slice
