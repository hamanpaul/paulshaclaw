## ADDED Requirements

### Requirement: hooks 安裝冪等
install SHALL 以集中宣告之清單複製全部 hooks 並 reconcile 三家 agent settings；重複執行 SHALL 零變更且不重複註冊。

#### Scenario: 二次執行冪等
- **WHEN** 於已安裝環境重跑 install hooks 段
- **THEN** 檔案零變更、settings 無重複註冊項

### Requirement: 部署 verify 健檢
install SHALL 提供 verify 模式：hook 語法/import 健檢、settings 註冊存在性、必要 env/secret 檔存在性（值不印出）、repo 與部署副本之內容 hash 比對；任一不符 SHALL exit 非零並指名壞點；hash 不符 SHALL 列出 stale hook 清單。

#### Scenario: stale hook 被點名
- **WHEN** repo 內某 hook 已修改而部署副本未同步
- **THEN** verify exit 非零並列出該 hook 為 stale

#### Scenario: 完好部署通過
- **WHEN** 全部 hooks 同步、settings 註冊齊、env 檔在位
- **THEN** verify exit 0

### Requirement: hook 路徑零硬編碼
hooks SHALL 不含個人絕對路徑硬編碼：shell hooks 以 `${PSC_REPO_ROOT}` 取路徑、Python hooks 經路徑 facade；verify SHALL 內建 lint（hooks 範圍零 `/home/` 字面、零 facade 外 `Path.home()`）。

#### Scenario: 硬編碼被 lint 攔截
- **WHEN** 任一 hook 含 `/home/` 字面路徑
- **THEN** verify exit 非零並指名該檔
