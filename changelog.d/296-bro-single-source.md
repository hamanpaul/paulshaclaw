---
type: change
scope: bro
issue: 296
---
`custom-skills/bro` 收斂為單一真相源：本 repo 目錄為 canonical（CI 跑 `custom-skills/bro/tests/`），runtime 載入點 `~/.agents/skills/bro` 改為指向 repo checkout 的 symlink，不再維護第二份實體副本或靠 hardlink 同步。把先前只存在於 runtime 副本的 `scripts/notify.py`（單向通知：max gateway 優先、直打 Telegram fallback）、`tests/test_notify.py` 與 SKILL.md 的 notify 段併回 repo，讓 runtime 同時取得 repo 側 #90 之後的 reply_bridge 修正（檔案鎖、`send_message`、message-pane-map 預設路徑）。新增 `tests/test_runtime_copy_drift.py`：本機若 `~/.agents/skills/bro` 指向另一份實體副本且與 repo 不一致即紅燈並列出漂移檔，CI／乾淨 clone 無該路徑時跳過。
