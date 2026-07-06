## ADDED Requirements

### Requirement: listener handler 例外隔離
Telegram listener 的 command dispatch SHALL 以最外圈 broad exception 邊界隔離每個 handler：handler 拋出任何 `Exception` 時記錄完整 traceback 至檔案 log、向使用者回覆單行錯誤訊息（不含 traceback 與內部路徑），並繼續 poll loop；`KeyboardInterrupt`/`SystemExit` 顯式放行。

#### Scenario: handler 拋未知例外
- **WHEN** 任一 command handler 拋出未被內層攔截的例外
- **THEN** listener 回覆「指令執行失敗：<例外類別>」並繼續處理後續訊息，進程不退出

#### Scenario: 既有窄型別語意不變
- **WHEN** telegram API 暫時性錯誤觸發既有內層重試邏輯
- **THEN** 行為與現行一致（外圈不提前吞掉）

### Requirement: bot 進程自動重生
start.sh SHALL 監督 bot 進程：poll loop 本體意外退出時依 backoff（5s→30s→120s 上限）自動重拉並記錄重生事件；重生僅涵蓋 bot，不影響其他常駐 loop。

#### Scenario: bot 進程非零退出
- **WHEN** bot 進程因未預期原因結束
- **THEN** start.sh 依 backoff 序列重新啟動 bot 並在 log 留下計數記錄
