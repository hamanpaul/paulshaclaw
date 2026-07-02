## Why

Audit wf_2bd0b606-6e4（slices-cap-7，驗證 CONFIRMED）證明「118/243 個 promoted session 恰好 7 slices」不是任何 cap，而是三件事相乘：importer 固定 7-heading 模板（`paulshaclaw/memory/importer/frontmatter.py:112-131`）× splitter `^#{1,6}\s` 切分（`atomizer.yaml:3-5`）× `IdentityPromoter` 1:1 恆等映射（`promoter.py:19-23`）。identity 路徑累計灌入 1246 條樣板 slices（llm 僅 138），每 7 條中至少 5 條是零價值樣板（空 H1、`## Source`、`## CWD`、兩個 `(none)` 清單），正是 06-25 prune 1112 筆與 untitled 殘留的源頭。

殘餘風險入口至今仍在：

1. `paulshaclaw/memory/atomizer/atomizer.yaml:30` 預設 `promoter: identity` —— `atomizer/cli.py:73` 的 `args.promoter or config.default_promoter` 使任何未帶 `--promoter` 的手動/backfill atomize 落入恆等複製（06-17/06-24 兩波即此入口）。
2. `paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh:6` 與 `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service:9` 硬 pin `--promoter identity`（systemd timer 現未安裝，但檔案仍在，啟用即重演）。

本 change 對應 issue #175。

## What Changes

- `atomizer.yaml` 預設 `promoter: identity` → `promoter: llm`；identity 保留為顯式 `--promoter identity` 選項（測試/離線用）。
- 新增測試 `paulshaclaw/memory/tests/test_promoter_default.py` 鎖定：(a) 內建 config 預設為 llm；(b) 未帶 `--promoter` 時 `_build_promoter` 回傳 `LLMPromoter` 而非 `IdentityPromoter`；(c) 顯式 identity 仍可用；(d) config 缺 `promoter` key 時 code-level fallback 維持 identity（fail-safe，不隱性外呼 LLM）。
- 同步修正兩處假設「預設 identity」的既有測試路徑：`test_atomizer_cli.py` 的 dry-run 測試與 `stage2_integration_check.sh` 的 atomize dry-run 改為顯式 `--promoter identity`（否則預設翻轉後會嘗試真打 gemma4）。
- `dream-idle-wrapper.sh` 與 `paulsha-memory-dream.service` 的 `--promoter identity` 改 `llm`，註解改為說明 identity 的樣板輸出風險；`test_dream_systemd_template.py` 斷言同步改 `--promoter llm`。
- `atomizer/config.py` 確認後**不修改**：yaml key 讀取路徑（config.py:297-302）與 dataclass 預設（config.py:41）維持現狀，理由見 design。

## Capabilities

### New Capabilities

None. 本 change 延伸既有 `stage2-memory-governance` capability。

### Modified Capabilities

- `stage2-memory-governance`: 新增「atomizer 預設 promoter 為 LLM 蒸餾」requirement——出貨 config 預設 llm、未帶旗標的 CLI 路徑不得落 IdentityPromoter、identity 僅限顯式選用、排程（systemd）路徑 pin llm。

## Impact

- Affected runtime config: `paulshaclaw/memory/atomizer/atomizer.yaml`（`promoter` key）。
- Affected schedule templates: `paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh`、`paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service`（皆為 repo 內範本；systemd timer 現未安裝，無部署動作）。
- Affected tests: 新增 `paulshaclaw/memory/tests/test_promoter_default.py`；修改 `test_atomizer_cli.py`、`test_dream_systemd_template.py`、`stage2_integration_check.sh`。
- 不改動：`atomizer/config.py`、`atomizer/cli.py`、`pipeline.py`、`memory/cli.py`、`dream/cli.py`、`scripts/start.sh`（生產 dream loop 本已 `--promoter llm`）、`.github/workflows/**`。
- 行為面：未帶 `--promoter` 的 `memory atomize` / `memory dream run` 現在會建構 LLMPromoter（`agent_exec.command` 預設 `scripts/claude-gemma4`）；若本機 gemma4 backend 不在線，promote 失敗走既有 fail-closed 路徑（session left in split），不會寫壞資料。
- Non-Goals: 不動 splitter、不加任何 slices cap（7 從來不是 cap）；不處理歷史殘留（untitled--、雙 key 屬 #176/#177 等其他待辦）；不改 `pipeline.run` 的函式參數預設（內部 API，呼叫者皆顯式傳入 promoter）。
