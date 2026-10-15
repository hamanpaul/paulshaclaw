## ADDED Requirements

### Requirement: 獨立 TestPilot 安裝回歸子專案

系統 SHALL 將 deployment regression plugin 包裝成獨立子專案，不加入 operator runtime dependencies。

#### Scenario: 安裝後 discovery

- **WHEN** 在獨立 Python 環境安裝 plugin wheel 與固定 TestPilot Core
- **THEN** list-plugins SHALL 顯示 paulshaclaw_deploy，list-cases SHALL 發現 TC-1、TC-1c、TC-1g、TC-1p

### Requirement: 歷史故障與成功控制組

系統 SHALL 固定 v0.2.7 README commit、wheel SHA 和 Ubuntu image digest，並以完整觀測驗收歷史故障。

#### Scenario: 缺 git 的歷史安裝

- **WHEN** TC-1 與 TC-1p 在無 git 的非 root 環境執行
- **THEN** 原始報告 SHALL 保留 FAIL，安裝 exit 1 與缺 git stderr、版本命令 exit 127 SHALL 均存在

#### Scenario: 成功控制組

- **WHEN** TC-1c 以 no-deps 安裝，TC-1g 在 Ubuntu 22.04 與 24.04 明確加上 git
- **THEN** entry points、精確版本與適用的安裝/status/help/usage gates SHALL PASS

### Requirement: 完整證據與清理

每個 case SHALL 逐步收集 exit code、stdout、stderr、timeout、輸入 provenance 與 container cleanup。

#### Scenario: 步驟失敗

- **WHEN** 安裝或其他步驟回傳非零
- **THEN** SHALL 繼續收集後續診斷，並只回收本次建立的容器

#### Scenario: 基礎設施故障

- **WHEN** Docker、網路、artifact/checksum、timeout、缺步驟或 cleanup 出現故障
- **THEN** historical oracle SHALL 拒絕該報告，CI SHALL 失敗
