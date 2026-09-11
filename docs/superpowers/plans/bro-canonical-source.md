---
work_item: bro-canonical-source
status: accepted
---

# bro 功能整合與單一來源執行計畫

## Tasks

repo 為 canonical；先保留兩側功能並測試，再提供版本化 snapshot 安裝、receipt、drift check 與回滾。外部 bro 只讀，可由 operator 提供去識別化輸入；worker 不直接改 runtime symlink。

工作 D：#296 bro 單一來源

建議 branch：`feature/296-bro-canonical-source`。

- [ ] 盤點 repo／runtime／外部 checkout 的逐檔相對路徑、hash、symlink target 與 inode，保留原始副本；列出所有呼叫入口（含 gemma4 hook 與 notify 使用者）。不收集 secret 值。
- [ ] 以 repo 為 canonical，將外部 `notify.py`、測試與必要 SKILL 說明先作功能及機敏檢查，再整合進 repo；保留 repo 的 MessagePaneMap／source-pane 行為。用 fixtures 與 fake sender 驗 gateway-first、direct fallback、dry-run、message-id→pane 追溯，不對外發 Telegram。
- [ ] 新增有 `--check`／dry-run／apply 的 scoped 安裝工具；source 與 runtime target 都可參數化。建議以版本化 snapshot 複製部署並記錄 source commit + 內容 hash，runtime symlink 指向該 snapshot，避免 runtime 隨開發 branch 即時改動；開發環境可明示選 checkout symlink 模式。
- [ ] 兩種模式都禁止 hardlink。先在 temp roots 演練：既有實體目錄有差異時拒絕覆寫、broken symlink、有增刪檔、重跑冪等、失敗回復、舊 snapshot 可回滾。排除 cache，但不得排除 SKILL／scripts／tests 等功能資產來掩蓋漂移。
- [ ] CI 比較暫存部署與 canonical 檔案集合／hash，並對刻意漂移反例 FAIL；現場 `--check` 比較 runtime 與部署 receipt，分辨內容遭改與新版本尚未部署。CI 不依賴作者機器的外部 custom-skills 路徑。
- [ ] 完成測試後才做現場切換，先可回復備份舊 target／副本；驗 runtime resolve 路徑與內容、依賴 import、dry-run 與 hook 解析。外部舊副本退役保留備份，不再作可編輯來源；回滾只切回既有已驗版本。

驗收：兩側功能整合測試綠；canonical／部署內容一致且 provenance 可查；原子式編輯任一普通副本都不能靠 hardlink 偷渡同步；drift 能被偵測；runtime dry-run 綠。僅修 repo 而未切換 runtime，記為「實作完成、部署待完成」。


## Integration gates

本工作源自 2026-09-07 使用者核可的五件 issue 修正計畫與 Cortex 平行派工指令。accepted 僅表示規格可執行，不表示程式或驗收已完成。

使用 Cortex 管理的隔離 branch/worktree；不得清理、stage 或覆寫 operator checkout 的既有變更。只處理本件 issue；所有實作、測試、OpenSpec、文件及 changelog 限本件 scope。不同工作線的 pyproject／CI／README 等共用檔須在各自 branch 修改，交由整合者處理衝突，不跨 worker worktree 寫入。

採 RED → 最小修正 → GREEN → 獨立 review → policy/preflight → PR 的受治理流程；未處置缺陷為 FAIL，接受風險需明文、有界且可追溯。禁止跳 gate 或手改 Cortex registry。部署、發布與本機 skill target 切換由 operator 整合驗收後執行，不由本 worker 自行進行；不得對外送 Telegram、覆寫既有 release、變更共享 service/config。PR 可依 Cortex 既有授權 gate 交付；不得僅憑 worker exit 0 宣告完成。

只驗收本件：保留 base/final SHA、RED/GREEN、focused/full tests、review 與 PR 證據。最終五件整合、published release 下載驗證及 runtime 切換屬批次整合者，不由本 worker 跨 scope 執行。
