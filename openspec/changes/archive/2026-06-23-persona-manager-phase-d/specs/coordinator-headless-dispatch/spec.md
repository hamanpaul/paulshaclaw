## ADDED Requirements

### Requirement: argv builder 與 SubprocessLauncher 支援 model passthrough

三家 argv builder（`build_copilot_argv` / `build_claude_argv` / `build_codex_argv`）SHALL 接受選用參數 `model: str | None = None`；當 `model` 非 None 時 MUST 在 argv append `--model <model>`，為 None 時 MUST NOT 加入任何 model 旗標（維持各 executor 預設）。`SubprocessLauncher.__init__` SHALL 接受 `model: str | None = None` 並於 `launch` 時傳入對應 argv builder。

#### Scenario: copilot argv 帶 model

- **WHEN** 以 `model="haiku-4.5"` 呼叫 `build_copilot_argv(...)`
- **THEN** 回傳 argv MUST 含相鄰的 `--model` 與 `haiku-4.5`

#### Scenario: model 未設不加旗標

- **WHEN** 不帶 `model`（None）呼叫任一 argv builder
- **THEN** 回傳 argv MUST NOT 含 `--model`

#### Scenario: SubprocessLauncher 將 model 傳入 argv builder

- **WHEN** `SubprocessLauncher(executor="copilot", model="haiku-4.5")` 執行 `launch(...)`
- **THEN** 啟動的 inner argv MUST 含 `--model haiku-4.5`
