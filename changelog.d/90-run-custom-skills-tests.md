### Fixed
- CI 與 `scripts/preflight-tests.sh` 補跑 `custom-skills/bro/tests/`（#90）：該目錄是 repo 內唯一不在 `tests/` 底下的測試，兩處 gate 都只跑 `tests/`，導致 reply_bridge 與 facade 的路徑漂移把關雖然寫了卻從未執行——測試綠燈只代表它沒被跑到。
