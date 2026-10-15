# Historical oracle fixture

`historical-report.json` 來自 2026-10-15 真實 Docker 報告，僅移除與 oracle 無關的 apt/pip stdout、stderr 與命令時間欄位。它只用於 oracle 單元測試；實際 Docker gates 永遠讀當次新產生的 report。
