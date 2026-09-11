---
work_item: bro-canonical-source
---

# bro 功能整合與單一來源

對應 hamanpaul/paulshaclaw#296。

repo 為 canonical；先保留兩側功能並測試，再提供版本化 snapshot 安裝、receipt、drift check 與回滾。外部 bro 只讀，可由 operator 提供去識別化輸入；worker 不直接改 runtime symlink。

## Current Sprint

- [ ] 依本 work item 的 accepted spec/design/plan 實作並提交 scope 內變更。
- [ ] 完成 focused tests、完整 preflight、獨立 review 與 PR。
- [ ] 核對合併、正式 artifacts 與適用的 installed/runtime evidence 後結案。

## Handoff

工作 D：#296 bro 單一來源

建議 branch：`feature/296-bro-canonical-source`。

- [ ] 盤點 repo／runtime／外部 checkout 的逐檔相對路徑、hash、symlink target 與 inode，保留原始副本；列出所有呼叫入口（含 gemma4 hook 與 notify 使用者）。不收集 secret 值。
- [ ] 以 repo 為 canonical，將外部 `notify.py`、測試與必要 SKILL 說明先作功能及機敏檢查，再整合進 repo；保留 repo 的 MessagePaneMap／source-pane 行為。用 fixtures 與 fake sender 驗 gateway-first、direct fallback、dry-run、message-id→pane 追溯，不對外發 Telegram。
- [ ] 新增有 `--check`／dry-run／apply 的 scoped 安裝工具；source 與 runtime target 都可參數化。建議以版本化 snapshot 複製部署並記錄 source commit + 內容 hash，runtime symlink 指向該 snapshot，避免 runtime 隨開發 branch 即時改動；開發環境可明示選 checkout symlink 模式。
- [ ] 兩種模式都禁止 hardlink。先在 temp roots 演練：既有實體目錄有差異時拒絕覆寫、broken symlink、有增刪檔、重跑冪等、失敗回復、舊 snapshot 可回滾。排除 cache，但不得排除 SKILL／scripts／tests 等功能資產來掩蓋漂移。
- [ ] CI 比較暫存部署與 canonical 檔案集合／hash，並對刻意漂移反例 FAIL；現場 `--check` 比較 runtime 與部署 receipt，分辨內容遭改與新版本尚未部署。CI 不依賴作者機器的外部 custom-skills 路徑。
- [ ] 完成測試後才做現場切換，先可回復備份舊 target／副本；驗 runtime resolve 路徑與內容、依賴 import、dry-run 與 hook 解析。外部舊副本退役保留備份，不再作可編輯來源；回滾只切回既有已驗版本。

驗收：兩側功能整合測試綠；canonical／部署內容一致且 provenance 可查；原子式編輯任一普通副本都不能靠 hardlink 偷渡同步；drift 能被偵測；runtime dry-run 綠。僅修 repo 而未切換 runtime，記為「實作完成、部署待完成」。
