# workstreams

此目錄為 stage 功能分流骨架，每個 workstream 固定包含：

- `plan.md`：範圍、寫入邊界、依賴、驗收 gate
- `task.md`：可驗證任務（適合 fleet / multi-agent 切分）
- `todo.md`：短迭代執行清單

規範：

1. 沒有明確寫入邊界，不得啟動平行開發。
2. 需要 sync 回 `custom-skills` 的內容，先完成該 stage 測試並附證據。
3. 共用檔（`docs/research/05...`）只允許 Stage0 分支更新。
