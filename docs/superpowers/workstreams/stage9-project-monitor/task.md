# stage9-project-monitor / task

- [x] 建立 `paulshaclaw/monitor/` package layout（models / config / scanner / parser / watcher / api / __main__）
- [x] 實作全局 config loader 與 `paulshaclaw/config/paulshaclaw.sample.yaml`
- [x] 實作 workspace 列舉與 tracked-vs-legacy 分類
- [x] 實作 ProjectState 萃取（completed / in_progress / pending + processing_task / next_task / blockers）
- [x] 實作 `--once` CLI 模式（JSON snapshot 輸出）
- [x] 實作 service runtime 三 loop（scanner / watcher / Unix socket server）
- [x] 實作 read API 與 subscribe 契約
- [x] 撰寫 unit / integration / service / CLI 測試與 evidence
- [x] 依 Cortex extraction 後的 ownership 封存歷史 change；不將舊 capability 套回本 repo canonical specs
