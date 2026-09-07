## 1. templates 與 artifact 可用性

- [x] RED：wheel、sdist、由 sdist 重建的 wheel 逐一驗 templates 相對路徑集合等於 source；source 集合非空且涵蓋 planner 所需資產，並保留 core commands.json、cockpit.tcss、entry points 與 launcher 檢查
- [x] 加 deploy package-data 規則；集合比較不硬編碼數量，並攔截缺檔、多餘錯路徑、空目錄與整個目錄缺失
- [ ] 兩個 release 入口共用 artifact checker，並在 PR CI 執行

## 2. deploy 失敗契約

- [ ] install／upgrade 預檢並 render templates 後才寫入；模板錯誤回 exit 1 單一 JSON，checksum 錯誤維持 exit 2
- [ ] plan-only install／upgrade 驗模板可讀；status／uninstall 不受不必要模板影響
- [ ] 最後一個 template 缺失時不部分寫入、不更新 install record、不碰 systemd；一般 I/O 失敗誠實回報已寫檔清單，upgrade 沿用 rollback

## 3. installed execution 與文件

- [ ] 乾淨 venv 從 wheel 執行 deploy install --apply --verify，驗證 JSON、檔案、權限、install record、模組載入位置
- [ ] 無 systemd 時測試回報 skip，不宣稱 service 啟動已驗證；說明 wheel Python 與 pip/pipx PATH 邊界
