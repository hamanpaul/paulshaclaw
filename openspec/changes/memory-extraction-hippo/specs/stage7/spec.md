## ADDED Requirements

### Requirement: dream 常駐部署移交 paulsha-hippo installer
拆包後 dream 常駐（service/timer 或 supervisor 模式）之安裝與生命週期 MUST 由 `hippo install service` 擁有：systemd user session 可用時產 `paulsha-hippo-dream.service/.timer` user units；不可用時指引 `hippo dream supervise` 前景模式。主 repo deploy planner MUST NOT 再產出 dream 相關 unit。

#### Scenario: 部署面不再擁有 dream unit
- **WHEN** 操作者列出主 repo `install` plan 的 template 資產
- **THEN** assets MUST NOT 含 dream 相關 service/timer 範本；dream 部署指引 MUST 指向 hippo installer

### Requirement: start.sh dream 段 cutover
`scripts/start.sh` 之 dream supervisor 段 MUST 改為：PATH 偵測 `hippo` 命令，存在則以等價 interval 與 require-idle 語意呼叫 `hippo dream supervise`，不存在則跳過並輸出警告。該段 MUST NOT 呼叫 `python -m paulshaclaw.memory.cli`。回滾 MUST 可藉還原 start.sh 該段 + revert 遷移 PR 達成。

#### Scenario: hippo 未安裝時安全跳過
- **WHEN** 主機未安裝 paulsha-hippo 且執行 start.sh
- **THEN** dream 段 MUST 輸出警告後跳過，其餘常駐啟動流程 MUST 不受影響
