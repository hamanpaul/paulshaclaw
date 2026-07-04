## Why

audit wf_2bd0b606-6e4（noise-filter-dead，PARTIAL 驗證修正版）查明 dream 生產路徑的 `noise_dropped` 恆 0 的結構性原因（issue #176，關聯 #100、#144、#147）：

- noise classifier 本身是活的——同套規則經離線 `prune-noise` 於 06-25 實刪 1112 筆；三條 body 規則（structural-echo / placeholder / empty）的目標已被 llm promoter 上游消除（skill 明令去贅詞、body 非空、不照抄），llm 時代 149 筆 slice 命中 0 屬正常。
- 但第四條 **doc-fragment 規則在 dream 生產路徑永遠 inert**：`paulshaclaw/memory/dream/cli.py:37-45` 的 `atomize_fn` 呼叫 `atomizer_pipeline.run` 未傳 `doc_corpus`；`paulshaclaw/memory/cli.py:81-89` 的 `dream run` parser 根本沒有 `--instruction-root` 可傳；`noise.py:143-144` 空 corpus 直接 `return False`。
- 影響：任何 identity fallback 或手動 backfill 都會無聲寫入 doc-fragment 噪音、`noise_dropped` 照樣報 0（假遙測）。存量 296 筆 knowledge 中 92 筆 doc-fragment（serialwrap 48 / testpilot 44）持續污染 wakeup brief（`wakeup/builder.py:104` 直接 rglob、無排噪）與 per-project MOC；retrieval index 自 #156 起已以 broad corpus 排噪（retrieval.db 與 92 筆交集 0），故本次收益在 brief/MOC 淨化與 dream 路徑防再犯。

## What Changes

- **`memory dream run` 加 `--instruction-root`（opt-in）**：`paulshaclaw/memory/cli.py` 的 dream run parser 新增 repeatable `--instruction-root`，完全沿用 `atomize` 子命令既有慣例（cli.py:72-75、atomizer/cli.py:104-107）：不傳＝空語料＝doc-fragment 規則維持關閉（行為契約，有測試鎖定）。
- **dream 路徑佈線**：`paulshaclaw/memory/dream/cli.py` 的 `atomize_fn` 以 `corpus_for_roots(args.instruction_root)` 組 `doc_corpus` 傳入 `atomizer_pipeline.run`，讓既有 doc-fragment 規則在 dream 產生端生效並計入 `noise_dropped`。
- **生產環境接上**：`scripts/start.sh` 的 dream loop 命令（start.sh:195-196）補上 `--instruction-root` 參數，語料來源比照 `instruction_corpus.default_roots()`（與 #156 moc/runner 的 index 端 broad corpus 同一組來源），使產生端 drop 與 index 端 pool-exclude 一致。
- **不含存量清理**：92 筆存量 doc-fragment 屬 ops、不入本 PR（見 design.md；勿對 serialwrap 全桶 prune——實測 manifest 會出 ~34 筆含真知識 echo，由 #177 的固定清單路徑處理）。

## Capabilities

### New Capabilities

None. 本 change 只是把既有 `stage2-noise-governance` 的 doc-fragment 判準接上 dream 生產路徑，非新邏輯。

### Modified Capabilities

- `stage2-noise-governance`: 「產生端與回溯 prune 共用 doc-fragment 判準」requirement 擴充至 dream 生產路徑——`memory dream run` SHALL 提供 opt-in `--instruction-root` 組裝語料下傳 atomize pass；不傳時規則惰性、行為不變；生產 dream loop（start.sh）SHALL 傳入語料。

## Impact

- 程式：改 `paulshaclaw/memory/cli.py`（僅 dream run parser 區塊，+1 個 argument；注意 #177 同檔新增其他 subcommand，diff 限縮在 dream run 區塊以降低 merge 衝突）、`paulshaclaw/memory/dream/cli.py`（import + doc_corpus 佈線）、`scripts/start.sh`（dream run 命令補 `--instruction-root` 參數）。
- 測試：新增 `paulshaclaw/memory/tests/test_dream_cli_instruction_root.py`（plumbing + e2e 行為契約）、`paulshaclaw/memory/tests/test_start_sh_dream_flags.py`（start.sh dream 命令旗標 guard）。
- 資料：本 PR 不刪任何 live 檔案；只影響「之後」的 dream run 產出（doc-fragment 新生被擋、`noise_dropped` 開始反映真實值）。
- 部署：start.sh 由 repo 直接執行（非 install.sh 複製路徑），git pull + 重啟 start.sh 即生效；dream loop 下個 tick 自動用新旗標。
- Non-Goals：存量 92 筆清理（ops，#177 相關）、`_shortlist_common` / wakeup builder 排噪（另案）、promote 失敗快取治理（#174/promotion-backlog 範圍）。
