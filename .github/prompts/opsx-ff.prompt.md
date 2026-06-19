---
description: Fleet-friendly 平行切分檢查與分支啟動
---

`/opsx:ff` 用於把單一功能切成可平行執行、互不影響的任務包，並驗證是否可進入 worktree 開發。

## 輸入

`/opsx:ff <workstream>`

例如：`/opsx:ff stage2-paulsha-memory`

## 執行內容

1. 讀取 `docs/superpowers/workstreams/<workstream>/{plan,task,todo}.md`
2. 驗證三項條件：
   - 已宣告寫入邊界
   - 已宣告跨 stage 依賴
   - 已宣告測試 gate 與證據路徑
   - `config/worktrees/stage-worktrees.tsv` 與 `origin/<branch>` remote 追蹤一致
3. 驗證後輸出 fleet 切分清單：
   - 可平行任務
   - 不可平行任務（需串行）
4. 準備進入實作前指令：
   - `scripts/using-git-worktrees.sh`
   - `git push -u origin <branch>`

## 固定輸出格式（必須遵循）

輸出必須固定包含以下段落，且順序不可更動：

```md
# /opsx:ff <workstream> 檢查結果

## 1) Preflight
- workstream: <name>
- branch: <branch>
- worktree: <path>
- 來源文件: plan/task/todo

## 2) 規範檢查
- 寫入邊界: PASS | FAIL（證據路徑）
- 跨 stage 依賴: PASS | FAIL（證據路徑）
- 測試 gate + 證據路徑: PASS | FAIL（證據路徑）
- remote tracking 一致性: PASS | FAIL（證據路徑）

## 3) Fleet 切分
- 可平行:
  1. <task>
- 需串行:
  1. <task>（blocker 原因）

## 4) 實作前命令
- scripts/using-git-worktrees.sh <map> <wt-root> <base-ref>
- git push -u origin <branch>

## 5) Guardrails
- custom-skills sync-back 需先通過 stage 測試: YES | NO

## 6) 結論
- READY | BLOCKED
- 下一步: <action>
```

## Guardrails

- 若缺任一條件（邊界/依賴/測試 gate），不得宣告可平行開發
- 若目標涉及 sync 回 `custom-skills`，必須再次提醒「先過 stage 測試」
