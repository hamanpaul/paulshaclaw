# hippo-consumer Specification

## Purpose
TBD - created by archiving change memory-extraction-hippo. Update Purpose after archive.
## Requirements
### Requirement: SHA pin 依賴
主 repo pyproject MUST 以 `paulsha-hippo @ git+https://github.com/hamanpaul/paulsha-hippo@<commit-sha>`（完整 40 字元 commit SHA）宣告依賴；MUST NOT 以 branch 或 tag 作為 pin 來源（tag 僅作人讀標記，hippo repo MUST 設 protected tags）。PyPI 上線後 MUST 轉為 version pin + hash。

#### Scenario: 可重現安裝
- **WHEN** CI 於乾淨環境依 pyproject 安裝依賴
- **THEN** 解析到的 paulsha-hippo 內容 MUST 與 pinned SHA 完全一致，且重跑結果相同

### Requirement: 允許 import 面限定
主 repo 對 paulsha-hippo 的 Python import MUST 限定於 `paulsha_hippo.lib.{lifecycle,idle,jsonl}`（persona.contract、coordinator.manager 等）；`core/daemon.py` MUST NOT import hippo internals（含 `paulsha_hippo.atomizer.config`），`/agent` 命令 argv MUST 來自 daemon 自有 config。

#### Scenario: import 面 CI 檢查
- **WHEN** CI 掃描主 repo 對 `paulsha_hippo` 的 import
- **THEN** 出現 `paulsha_hippo.lib.*` 以外的 import MUST 使檢查失敗

#### Scenario: daemon 不依賴 hippo 內部
- **WHEN** 安裝 paulsha-hippo 為套件且主 repo 移除 `paulshaclaw.memory` 後執行 `/agent start` 與 `/agent status`
- **THEN** 兩命令 MUST 正常運作（argv 來自 daemon config，不經 hippo 套件內相對路徑解析）

### Requirement: path-split 相容與零資料遷移
拆包後 hippo 各表面（CLI、hooks、服務）解析之 memory root MUST 與主 repo 既有 `~/.agents/memory` 契約一致：預設值相同、`PSC_MEMORY_ROOT` MUST 仍被讀取（deprecated 警告）。既有 runtime 資料 MUST 零遷移可用。

#### Scenario: 舊 PSC hooks 與 hippo 服務同 root
- **WHEN** G5 時代以 `PSC_MEMORY_ROOT` 安裝的 hooks 持續寫入，且 hippo dream 服務以預設 config 執行
- **THEN** 兩者解析之 memory root MUST 相同，ingestion 不得分家

#### Scenario: 雙 root 不一致偵測
- **WHEN** `PSC_MEMORY_ROOT` 與 `HIPPO_MEMORY_ROOT`（或 config）同時存在且指向不同路徑，操作者執行 `hippo doctor`
- **THEN** doctor MUST 以 FAIL（非警告）回報，並列出各表面實際解析結果

### Requirement: 非 systemd 主機 fallback
主 repo `scripts/start.sh` 之 dream 段 MUST 改為 PATH 偵測呼叫 `hippo dream supervise`；hippo 未安裝時 MUST 跳過並輸出警告，MUST NOT 殘留對 `python -m paulshaclaw.memory.cli` 的呼叫。

#### Scenario: systemd 不可用時服務仍在
- **WHEN** systemd user session 不可用（如受限 WSL）且已安裝 hippo，主機以 start.sh 啟動
- **THEN** dream 常駐 MUST 經 `hippo dream supervise` 提供，interval 與 require-idle 語意與拆包前等價

