## ADDED Requirements

### Requirement: Agent 命令 argv 來源為 daemon 自有 config
`/agent start`／`/agent startf` 啟動之 agent 命令 argv MUST 由 daemon 自有 config 區段解析（沿 P2 env-path facade），MUST NOT 讀取 `paulsha_hippo.atomizer.config`（拆包後其 `resolve_command_argv` 之 `base_dir` 為 site-packages，相對路徑解析必壞）。config 中之 wrapper 路徑 MUST 為絕對路徑或 PATH 可解析之命令名；預設值維持 claude-gemma4 wrapper 之遷移後絕對位置。

#### Scenario: 拆包後 agent start 正常
- **WHEN** paulsha-hippo 以套件安裝、`paulshaclaw.memory` 已移除，操作者送出 `/agent start`
- **THEN** daemon MUST 以自有 config 解析出的 argv 建立 tmux pane 並啟動 agent，回覆新 pane ID

#### Scenario: config 缺 agent 命令
- **WHEN** daemon config 未設定 agent 命令且預設 wrapper 不存在
- **THEN** `/agent start` MUST 回覆明確錯誤（含應設定之 config 鍵名），MUST NOT 靜默 fallback 到套件內相對路徑
