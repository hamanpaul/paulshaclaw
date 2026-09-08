## 1. templates 與 artifact 可用性

- [x] RED：wheel、sdist、由 sdist 重建的 wheel 逐一驗 templates 相對路徑集合等於 source；source 集合非空且涵蓋 planner 所需資產，並保留 core commands.json、cockpit.tcss、entry points 與 launcher 檢查
- [x] 加 deploy package-data 規則；集合比較不硬編碼數量，並攔截缺檔、多餘錯路徑、空目錄與整個目錄缺失
- [x] 兩個 release 入口共用 artifact checker，並在 PR CI 執行

## 2. deploy 失敗契約

- [x] install／upgrade 預檢並 render templates 後才寫入；模板錯誤回 exit 1 單一 JSON，checksum 錯誤維持 exit 2
- [x] plan-only install／upgrade 驗模板可讀；status／uninstall 不受不必要模板影響
- [x] 最後一個 template 缺失時不部分寫入、不更新 install record、不碰 systemd；一般 I/O 失敗誠實回報已寫檔清單，upgrade 沿用 rollback

## 3. installed execution 與文件

- [x] 乾淨 venv 從 wheel 執行 deploy install --apply --verify，驗證 JSON、檔案、權限、install record、模組載入位置
- [x] 無 systemd 時測試回報 skip，不宣稱 service 啟動已驗證；說明 wheel Python 與 pip/pipx PATH 邊界

## 4. pre-archive repair 與 gate 完整性

- [x] tests.yml 與 scripts/preflight-tests.sh 在 pytest 前於同一 operator runtime 安裝 build frontend，並清除跨 checkout 的 PSC_REPO_ROOT，補齊 wheel/sdist 與 installed-wheel acceptance 執行條件
- [x] build-system 固定 setuptools>=62.3，source checker 只把真正沒有任何檔案的 template 目錄視為 empty，並補回歸測試
- [x] plan-only failure report 重用 installer 共用 helper、installed-wheel 測試在 pip 安裝與執行階段清除 checkout PYTHONPATH，並由 planner 推導 applied_files，避免契約漂移
- [x] 補齊本 change 的 proposal、design 與 Stage 7 spec delta；本 active change 只記錄 archive 前的實作與驗證工作
