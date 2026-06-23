# Canary 任務（trivial 有界）

你是 Phase D canary 驗證 agent。**只做這一件事**：在當前 worktree 內建立檔案
`tests/canary_pong.md`（此路徑在 builder 契約 `write_paths` 內），內容單一行
`pong`。完成後立即停止。

嚴格限制：
- 不要修改或刪除任何其他檔案。
- 不要 `git commit` / `git push`。
- 不要安裝套件、不要執行與上述無關的任何指令。

這是純粹的「通電」驗證，目的只是證明 dispatch→headless→完成偵測→manifest 全鏈走通。
