## 1. 契約層（control/contract.py）

- [ ] 1.1 RED：dispatch request build/validate 測試（型別合法、args schema、done 稽核欄）
- [ ] 1.2 `REQUEST_TYPES` 加 `"dispatch"`＋done 紀錄 helper；GREEN

## 2. executor（manager_daemon）

- [ ] 2.1 RED：五拒絕路徑＋force_hold 覆蓋＋正常派發測試（fake launcher/registry）
- [ ] 2.2 request executor 處理 dispatch（含 already-active 查 registry in-flight）；GREEN

## 3. status held 穿透

- [ ] 3.1 RED：status provider held 三分類、read_status 傳遞、舊格式相容、/manager status 顯示測試
- [ ] 3.2 build_runtime_status_provider 加 held；control/client.py read_status 正規化鍵加 held；core/daemon._format_manager_status 顯示；GREEN

## 4. bot 端 adapter 與 selection

- [ ] 4.1 RED：ControlPlaneCoordinator create_job/wait_done、backend selection 三態測試
- [ ] 4.2 control/client.py 加 ControlPlaneCoordinator；core/config.py CoordinatorSettings 加 backend；listener 注入依 selection；LocalCoordinator 標 test-only；GREEN（既有 fail-closed 測試零回歸）

## 5. 接線與 e2e

- [ ] 5.1 start.sh manager 啟動加 `--specs-dir "$REPO/docs/superpowers/specs"`（default 不變）＋既有 start.sh 測試同步
- [ ] 5.2 e2e：/dispatch → requests → done 真 job_id → worktree；同 slice 二連發第二發 already-active
- [ ] 5.3 全套件綠；PR body `Closes #23`、`Refs #14`（epic 由 owner 裁決關閉時點）
