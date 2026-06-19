---
description: 建立功能工作流骨架（plan/task/todo + worktree 對照）
---

建立指定功能（workstream）的初始資料夾與文件骨架，用於進入平行開發前的規劃。

## 輸入

`/opsx:new <workstream>`

例如：`/opsx:new stage3-lifecycle-mvp`

## 執行內容

1. 建立 `docs/superpowers/workstreams/<workstream>/`
2. 建立三份文件：`plan.md`、`task.md`、`todo.md`
3. 若 `config/worktrees/stage-worktrees.tsv` 無對應項目，提示補齊 branch/worktree 對照
4. 回報此 workstream 的：
    - 先決依賴
    - 寫入邊界
    - 測試 gate
    - 證據路徑（預設 `docs/superpowers/workstreams/<workstream>/evidence/`）

## Guardrails

- 不得自動建立程式碼實作，只建立規劃骨架
- 必須要求寫入邊界，避免與其他 workstream 衝突
- 必須要求證據路徑，避免驗證輸出無處落地
- 所有文檔預設使用 zh-tw
