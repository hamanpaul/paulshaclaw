## 1. handler 例外隔離（TDD）

- [ ] 1.1 RED：測試 fake handler 拋 `ValueError`／任意 `Exception` → listener 應續 poll＋回覆錯誤（現行會死，先看它 fail）
- [ ] 1.2 dispatch 外圈 broad `except Exception`：檔案 log 完整 traceback＋Telegram 單行錯誤回覆＋continue；`KeyboardInterrupt`/`SystemExit` 放行
- [ ] 1.3 GREEN＋既有 telegram listener 測試零回歸（含 fail-closed dispatch 守門）

## 2. start.sh respawn

- [ ] 2.1 RED：stub script 模擬 bot 進程非零退出 → 應依 backoff 重拉（避免 SIGKILL 情境，繞開 #195 坑）
- [ ] 2.2 start.sh bot supervisor：backoff 5s→30s→120s cap、重生計數入 log、cleanup 正確收尾
- [ ] 2.3 GREEN＋手動驗證：kill bot 進程 → 自動重生、其他 loop 不受影響

## 3. 收尾

- [ ] 3.1 全套件測試綠
- [ ] 3.2 PR body `Closes #196`
