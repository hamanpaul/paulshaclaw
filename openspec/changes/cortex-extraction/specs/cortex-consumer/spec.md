## ADDED Requirements

### Requirement: SHA pin 依賴
主 repo pyproject MUST 以 `paulsha-cortex @ git+https://github.com/hamanpaul/paulsha-cortex@<commit-sha>`（完整 40 字元 commit SHA）宣告依賴；MUST NOT 以 branch 或 tag 作為 pin 來源（tag 僅作人讀標記，cortex repo MUST 設 protected tags）。PyPI 上線後 MUST 轉為 version pin + hash。

#### Scenario: 可重現安裝
- **WHEN** CI 於乾淨環境依 pyproject 安裝依賴
- **THEN** 解析到的 paulsha-cortex 內容 MUST 與 pinned SHA 完全一致，且重跑結果相同

### Requirement: 允許 import 面限定
主 repo 對 paulsha-cortex 的 Python import MUST 限定於 `paulsha_cortex.control.client`（bot/listener、cockpit/app、core/daemon）與 `psc` CLI shim 對 cortex CLI 入口的 lazy import；MUST NOT import 其他 cortex internals（coordinator、persona 內部模組）。

#### Scenario: import 面 CI 檢查
- **WHEN** CI 掃描主 repo 對 `paulsha_cortex` 的 import
- **THEN** 出現允許清單以外的 import MUST 使檢查失敗

### Requirement: cortex 零 hippo 依賴
paulsha-cortex 的依賴解析 MUST NOT 含 paulsha-hippo——persona 可單獨安裝是本拆分的核心要求，不得被記憶產品綁架。

#### Scenario: 乾淨環境單獨安裝
- **WHEN** 於乾淨環境 `pip install paulsha-cortex` 並列出解析後的依賴集合
- **THEN** 依賴集合 MUST NOT 出現 paulsha-hippo

### Requirement: 對齊測試以主 repo 為契約交會點
主 repo 測試套件 MUST 同裝 hippo 與 cortex 並驗證三項跨包契約：（1）cortex 自帶 PHASES 與 `paulsha_hippo.lib.lifecycle.schema.PHASES` 相等；（2）cortex paths 模組與主 repo `config.paths` facade 在相同 env 下解析出相同路徑（`control_root`／`coordinator_root`／`repo_root`／`specs_root`／`worktree_root`）；（3）deck 卡片 `persona_binding` 與 cortex personas.yaml 的 role 對齊。

#### Scenario: PHASES 漂移被攔截
- **WHEN** cortex 或 hippo 任一方的 PHASES 內容或順序變動且主 repo bump 該方 pin
- **THEN** 主 repo 對齊測試 MUST 失敗

#### Scenario: paths 等價
- **WHEN** 以相同 `PSC_*` env 覆寫組合分別呼叫 cortex paths 模組與主 repo facade
- **THEN** 兩者對五個 root 函式 MUST 回傳相同路徑

#### Scenario: deck↔persona 對齊
- **WHEN** deck cards.yaml 的 `persona_binding` 引用了 cortex personas.yaml 不存在的 role
- **THEN** 主 repo 對齊測試 MUST 失敗

### Requirement: path-split 相容與零資料遷移
拆包後 cortex 各表面（daemon、CLI、control client）解析之 control root MUST 與主 repo 既有 `~/.agents/control` 契約一致：預設值相同、`PSC_*` env 覆寫 MUST 仍被讀取。既有 runtime 資料（control 檔案、job registry）MUST 零遷移可用。persona loader 對 `paulshaclaw.deck.schema` 的 lazy import MUST 維持 fail-open：deck 缺席時靜默跳過 skills shadow 驗證（warning 級 lint，非 enforcement），MUST NOT 進入 cortex install_requires。

#### Scenario: control 檔案零遷移
- **WHEN** 主 repo 舊 manager 寫入的 control root 檔案存在，cutover 後 cortex daemon 以預設 config 啟動
- **THEN** cortex daemon MUST 讀到同一 control root 的既有狀態，不得分家

#### Scenario: standalone 安裝 deck 缺席
- **WHEN** 僅安裝 paulsha-cortex（無主 repo）並載入 persona catalog
- **THEN** 載入 MUST 成功，skills shadow 驗證靜默跳過，schema 硬驗證（raise 級）行為不變

### Requirement: systemd cutover 協議
manager systemd 單元 MUST 改由 cortex `install service` 出貨。cutover MUST 依序：停用（stop + disable）舊 manager 單元 → enable cortex 單元；`install service` MUST 冪等（重跑不留半套狀態）；rollback 路徑 = revert 主 repo pin + 重 enable 舊單元。單寫者不變量（manager daemon 以 flock 持 `control_root()/manager.lock`）MUST 隨包平移並保留測試。

#### Scenario: 雙 daemon 鎖競爭
- **WHEN** 舊 manager daemon 未停止時啟動 cortex manager daemon（或反之）
- **THEN** 第二個實例 MUST 因拿不到 `manager.lock` 而退出，不得對同一 control root 併行寫入

#### Scenario: install 冪等
- **WHEN** `cortex install service` 連續執行兩次
- **THEN** 第二次執行 MUST 成功且系統狀態與第一次執行後相同
