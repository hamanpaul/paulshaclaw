## Why

Stage 2 dream 雖已端到端打通，但 knowledge 553 個 slice 中約 474（86%）是結構/空殼噪音——session-archive 的 `## CWD / ## Source / ## Prompts / ## Touched files / ## Referenced artifacts / ## Summary` 段落被各自原子化成 knowledge slice，洗版 wake-up MOC，使記憶中樞「水管通了卻產出無價值」。需在產生端阻斷新生、並回溯清掉既有噪音。

## What Changes

- 新增 noise classifier（純函式，**以 body 內容為準**）：body 第一行為 importer 結構 heading（structural-echo）、正文 < 40 字（empty）、或含 placeholder 字串者判為 noise；`untitled--` 等有真內容者保留。
- 產生端：atomize promote pass 在寫入前過濾 noise slice（不寫 knowledge、不建 relation、計入 `noise_dropped`）。
- 回溯端：新增 `psc memory knowledge prune-noise` CLI（預設 `--dry-run`，`--apply` hard delete 並重建 MOC，一律輸出稽核 manifest）。
- 不動 raw archive / inbox（source session 為真相源）。

## Capabilities

### New Capabilities
- `stage2-noise-governance`: knowledge 噪音的判準（classifier）、產生端過濾、回溯 prune CLI 與稽核 manifest。

### Modified Capabilities
<!-- 無 spec-level 行為變更：產生端過濾以新 capability 的 requirement 表達，不改既有 stage2-llm-distillation 契約。 -->

## Impact

- 程式：新增 `paulshaclaw/memory/noise.py`；改 `paulshaclaw/memory/atomizer/pipeline.py::_promote_pass`；`paulshaclaw/memory/cli.py` 加 `knowledge prune-noise` 子命令。
- 資料：live store `knowledge/**.md` 既有 474 噪音檔將被 hard delete（manifest 落 `runtime/ledger/prune-<ts>.jsonl`）；raw archive 不動。
- 部署：dream loop 下個 tick 自動用新碼；回溯清理為一次性人工 `--apply`。
