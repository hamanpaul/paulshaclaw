## ADDED Requirements

### Requirement: tracked 檔零識別資訊
公開 repo 的 tracked 檔（排除 `ref/` 與明示宣告的測試 fixture）SHALL NOT 含內網主機 FQDN、雇主/供應商字面名、個人工作樹絕對路徑或其目錄名硬編碼；歷史遺留 SHALL 以中性佔位（如 `vendor-a`、`git.example.com`、`prj_ext`）替換。

#### Scenario: Stage A 清理後全樹歸零
- **WHEN** 以安全驗證器對 HEAD tracked 檔執行結構+字面掃描
- **THEN** 命中數為 0，且驗證器輸出不含任何命中行原文

#### Scenario: corpus root 不再硬編碼
- **WHEN** `PSC_EXTRA_CORPUS_ROOT` 未設定
- **THEN** instruction corpus 探索與 dream loop 啟動參數皆不含第 2 工作樹 root，行為等同該 root 不存在

### Requirement: 安全驗證器輸出遮蔽
de-ident 驗收與例行掃描所用驗證器 SHALL 自 secret 來源（本機 secret 空間或 CI secret env）載入字面表，輸出僅含計數、遮蔽後 marker 代號與檔案路徑；不得將命中行文字寫入 stdout、PR、CI log。

#### Scenario: 命中時不洩漏
- **WHEN** 驗證器在某 tracked 檔命中字面 marker
- **THEN** 輸出僅含「marker 代號＋檔案路徑＋計數」，無該行內容

#### Scenario: 字面表缺席降級
- **WHEN** secret 字面表不可用
- **THEN** 驗證器降級為僅結構樣式掃描並明示降級狀態，不報錯中止

### Requirement: 上游 R-21 gate 生效
policy-check pin SHALL 升至含 #45 修復（PUBLIC repo 一律掃描、輸出遮蔽）的引擎版本；bump 前須以目標版本本機 dry-run 零 fail。

#### Scenario: pin bump 後 gate 實掃
- **WHEN** PR 觸發 Policy Check（引擎為修復版）
- **THEN** R-21 對本 repo 實際執行掃描（結果非 not-applicable PASS）

### Requirement: authoring-time 警告 hook
PostToolUse(Write|Edit) hook SHALL 對寫入內容執行結構樣式＋本機字面表比對，命中時發出警告；hook 為 warn-only，不得阻塞寫入，字面表檔案不入版控。

#### Scenario: 寫入含結構樣式內容
- **WHEN** agent 寫入含個人絕對路徑樣式的內容
- **THEN** hook 發出警告且寫入照常完成
