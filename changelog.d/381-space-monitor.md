---
type: feat
scope: bot
issue: 381
---

新增 WSL 磁碟容量監控：listener 每 20 分鐘量測、三級 Telegram 遲滯告警、原子 JSON 狀態與有界目錄掃描；輸出四類唯讀回收建議，保守排除 busy／未知行程與不完整 Git 證據。支援環境變數設定，預設且永遠不執行自動刪除。
