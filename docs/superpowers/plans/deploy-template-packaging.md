---
work_item: deploy-template-packaging
status: accepted
---

# deploy templates 打包與失敗契約執行計畫

## Tasks

先完整預檢並 render，才允許寫入；checksum 錯誤 exit 2 保留，模板錯誤 exit 1 JSON。兩個 release 入口共用 artifact checker。

工作 B：#326 templates 與 artifact 可用性

建議 branch：`feature/326-deploy-template-packaging`。

修改範圍：`pyproject.toml`、`paulshaclaw/deploy/{planner,installer,__main__}.py`、兩個 release 入口、新增共享 artifact 檢查器與測試、既有 deploy 測試、`docs/release-contract.md`。

- [ ] RED：wheel、sdist、由 sdist 重建的 wheel，逐一驗 templates 相對路徑集合等於 source；source 集合須非空且符合 planner 所需資產。另保留 core commands.json、cockpit.tcss、entry points 與 launcher 檢查，避免 #335 回歸。
- [ ] 加 deploy package-data 規則。集合比較不只比較數量，也不永久硬編碼 12；缺一檔、多一錯路徑、空目錄、整個目錄缺失皆須被 gate 擋住。
- [ ] 兩個 release 入口共用同一 checker：檢查 wheel／sdist 內容與禁用模板字串；archive 開啟錯誤、檔案不存在、讀取失敗均回非零。PR CI 即跑此 gate，不能只在 tag release 時跑。
- [ ] 在 install／upgrade 的任何寫入或 checkpoint 前，完整驗證並 render 所需 templates；缺失或讀取錯誤回 exit 1 + 單一 JSON，`status=failed`，帶 instance/root、失敗資產與可操作訊息。既有 artifact checksum 錯誤的 exit 2 契約維持。
- [ ] plan-only install／upgrade 也驗模板可讀，缺失回非零 JSON；純 status／uninstall 不因不需要的模板而失效。
- [ ] 缺模板反例以「最後一個 template 缺失」確認不會先寫入部分檔案、更新 install record 或碰 systemd。若預檢後發生一般 I/O 失敗，report 誠實保留已寫檔清單，不宣稱整體原子性；upgrade 沿用既有 rollback 契約。
- [ ] 在乾淨容器 venv 安裝 candidate wheel，從 checkout 外以該 venv python 跑 `deploy install --apply --verify`；驗 exit、JSON 欄位、applied_files、permissions、install record 的版本與 SHA。移除 PYTHONPATH 污染並記錄模組實際載入位置。
- [ ] 測試容器不接 host user bus；無 systemd 時報告 skip，不能冒稱 service 啟動已驗證。單純 `--home-dir` 只隔離檔案落點，不足以隔離 `loginctl`／`systemctl` 的副作用。
- [ ] 文件補「必須使用裝有 wheel 的 Python」，以及 deploy 寫 units/config、CLI PATH 由 pip/pipx 安裝處理的邊界。

驗收：issue S2-1／3／4／5／7／8 全部有對應證據；source tests 綠、artifact 內容與 installed execution 皆綠。正式新版容器重跑列入第 9 節收尾，不覆寫舊 v0.2.7 release。


## Integration gates

本工作源自 2026-09-07 使用者核可的五件 issue 修正計畫與 Cortex 平行派工指令。accepted 僅表示規格可執行，不表示程式或驗收已完成。

使用 Cortex 管理的隔離 branch/worktree；不得清理、stage 或覆寫 operator checkout 的既有變更。只處理本件 issue；所有實作、測試、OpenSpec、文件及 changelog 限本件 scope。不同工作線的 pyproject／CI／README 等共用檔須在各自 branch 修改，交由整合者處理衝突，不跨 worker worktree 寫入。

採 RED → 最小修正 → GREEN → 獨立 review → policy/preflight → PR 的受治理流程；未處置缺陷為 FAIL，接受風險需明文、有界且可追溯。禁止跳 gate 或手改 Cortex registry。部署、發布與本機 skill target 切換由 operator 整合驗收後執行，不由本 worker 自行進行；不得對外送 Telegram、覆寫既有 release、變更共享 service/config。PR 可依 Cortex 既有授權 gate 交付；不得僅憑 worker exit 0 宣告完成。

只驗收本件：保留 base/final SHA、RED/GREEN、focused/full tests、review 與 PR 證據。最終五件整合、published release 下載驗證及 runtime 切換屬批次整合者，不由本 worker 跨 scope 執行。
