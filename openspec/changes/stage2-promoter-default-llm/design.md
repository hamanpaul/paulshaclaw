## Context

Stage 2 atomizer 的 promoter 決策鏈：

1. `paulshaclaw/memory/cli.py:70`（`memory atomize --promoter`，`default=None`）與 `:87`（`memory dream run --promoter`，`default=None`）。
2. `paulshaclaw/memory/atomizer/cli.py:73` `_build_promoter`：`promoter_name = args.promoter or config.default_promoter`；`:74-75` 非 `"llm"` 一律回 `IdentityPromoter()`。`dream/cli.py:34` 直接複用 `_build_promoter`。
3. `paulshaclaw/memory/atomizer/config.py:297-302` `load_config` 讀 yaml key `promoter`（`config_data.get("promoter", "identity")`，僅允許 `identity|llm`）；`config.py:41` dataclass 欄位預設 `default_promoter: str = "identity"`。
4. 出貨 config `paulshaclaw/memory/atomizer/atomizer.yaml:30` 目前為 `promoter: identity` —— 這是唯一實際生效的預設來源（packaged yaml 永遠帶此 key，config.py 的兩個 "identity" fallback 對 packaged config 永遠不觸發）。

audit（slices-cap-7，CONFIRMED）已證明 identity 1:1 恆等映射把 importer 7-heading 樣板原封升格成 knowledge slices（1246 條，5/7 為零價值樣板），且 `scripts/start.sh:196` 生產 dream loop 早已顯式 `--promoter llm`——預設 identity 只剩「意外入口」功能。

## Goals / Non-Goals

**Goals:**

- 未帶 `--promoter` 的 CLI 路徑（`memory atomize`、`memory dream run`）預設建構 `LLMPromoter`，不再落 `IdentityPromoter`。
- identity 保留為顯式 `--promoter identity` 選項（測試/離線 deterministic 用途）。
- systemd 排程範本（wrapper + service）與生產路徑一致 pin `--promoter llm`，並以註解記錄 identity 的樣板輸出風險。
- 測試鎖定以上三點，防止回歸。

**Non-Goals:**

- 不動 splitter、不加 slices cap（7 從來不是 cap，內容無截斷損失）。
- 不改 `_build_promoter` / `load_config` 的程式邏輯——只翻 yaml 值。
- 不改 `pipeline.run(promoter=None)` 內部參數預設（`pipeline.py:505` `promoter or IdentityPromoter()`）：內部 API，兩個生產呼叫者（`atomizer/cli.py:114`、`dream/cli.py:34→44`）皆顯式傳入 `_build_promoter` 產物，測試直呼 `pipeline.run` 也依賴此預設做 deterministic 測試。
- 不清理歷史殘留（untitled、雙 key、空目錄），屬其他 issue。

## Decisions

### D1: 只翻 atomizer.yaml，config.py 不改

`atomizer.yaml:30` `promoter: identity` → `promoter: llm`。`config.py:41` 的 dataclass 預設與 `:297` 的 `get("promoter", "identity")` fallback **刻意維持 identity**：這兩個 fallback 只在「config 檔缺 `promoter` key」時觸發（packaged yaml 永遠有 key），維持 identity 是 fail-safe——精簡/殘缺 config 不會隱性升級成會外呼 LLM 的行為。此決策以測試鎖定（缺 key 的最小 config → identity）。

### D2: identity 保留為顯式選項

`memory/cli.py:70,:87` 的 `choices=["identity", "llm"]` 不變。測試與 `stage2_integration_check.sh` 需要 deterministic、無外部依賴的 promoter；多個既有測試（`test_dream_e2e.py:148`、`test_moc_e2e.py:37-38` 等）已顯式傳 identity。

### D3: 假設「預設 identity」的既有消費者同步改顯式

盤點結果（2026-07-02 基線：769 passed, 1 skipped）只有兩處未帶 `--promoter` 而依賴預設 identity：

- `paulshaclaw/memory/tests/test_atomizer_cli.py:35-49` `test_dry_run_prints_summary_and_writes_nothing`——dry-run 路徑仍會呼叫 `promoter.promote`（`pipeline.py:344-347` `_promote_fragments`），預設翻轉後會嘗試真跑 `scripts/claude-gemma4`（CI 無此 backend → PromoteError → slices=0 → 斷言失敗）。改為顯式 `--promoter identity`（該測試標的是 dry-run 摘要行為，非 promoter 選擇）。
- `paulshaclaw/memory/tests/stage2_integration_check.sh:133-134` 的 atomize dry-run 同理，補 `--promoter identity`（同檔 `:155-160` 的 llm stub 呼叫本已顯式）。

其餘出現 `default_promoter="identity"` 的測試（`test_dream_cli.py:46,:78`、`test_dream_cli_moc_warnings.py:62`）是 mock `load_config` 回傳值，不受 yaml 影響，不改。

### D4: systemd 兩個範本一起改（含 boundary 延伸一檔）

Issue 與原 boundary 只點名 `dream-idle-wrapper.sh:6`，但 `dream/systemd/paulsha-memory-dream.service:9` 的 `ExecStart` **不經 wrapper**、直接硬 pin `--promoter identity`——只改 wrapper 無法關閉「systemd path 啟用即重演」這個 issue 明載的殘餘風險入口，且 `test_dream_systemd_template.py:19,:28` 同時鎖兩檔。故 boundary 延伸納入 `.service` 一檔（單 token 修改 + 註解更新）。兩檔註解改為：pin llm 與生產（`scripts/start.sh:196`）一致；identity 僅為顯式測試選項，會把 importer 樣板 fragments 1:1 複製成 knowledge slices，noise gate 只擋部分樣板（#175）。

### D5: 測試一律 `load_config(override_path=None)`

`load_config` 預設 sentinel 會讀 `~/.config/paulshaclaw/atomizer.override.yaml`（`config.py:116-117`）；新測試必須傳 `override_path=None` 停用 override，只驗 repo 內建 yaml，避免開發機本地 override 汙染測試結果。

## Risks / Trade-offs

- **未帶旗標的手動 atomize 會真打 gemma4**：這正是意圖。若 backend 離線，`AgentExecClient` 失敗 → `PromoteError` → session left in split（fail-closed，`pipeline.py:407-409`），下輪可重試，不寫壞資料。Trade-off 記錄於 wrapper/service 註解。
- **config_hash 改變**：yaml 內容變動使 `load_config` 回傳的 hash 改變（`config.py:332-333`）。hash 僅寫入 ledger events 供追溯，promote 路徑無 hash gating，無遷移需求。
- **wrapper 原註解的成本防護消失**：原註解「keep ... identity so a local atomizer override cannot silently flip it into spawning a full Claude CLI」。改 pin llm 後，`agent_exec.command` 仍由 config 控制（預設 `scripts/claude-gemma4`，本地 vLLM 非計費 Claude CLI）；顯式 pin `--promoter llm` 同樣阻斷 override 翻轉 promoter，command 面向的 override 風險與生產 start.sh 路徑等價，不新增暴露。
- **R-18 docs 對齊**：`paulshaclaw/memory/routing.md:58` 描述的是顯式 `--promoter llm` 路徑，翻轉預設後仍正確，無需同步；若 Policy Check 出 WARN 可上 `policy-exempt:docs-sync`。

## Migration Plan

| Step | Action |
|---|---|
| 1 | 新增 `test_promoter_default.py`（RED：預設仍 identity 時 2 個測試失敗）。 |
| 2 | 翻轉 `atomizer.yaml:30` + 同 commit 修正 D3 兩個既有消費者（GREEN）。 |
| 3 | 更新 `test_dream_systemd_template.py` 斷言為 `--promoter llm`（RED）→ 改 wrapper + service（GREEN）。 |
| 4 | 全套回歸：`PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q`（基線 769 passed, 1 skipped）。 |

Rollback：revert 單一 PR 即回復預設 identity；無資料遷移、無部署動作（systemd timer 未安裝、生產 start.sh 不受影響）。

## Open Questions

1. 積壓/毒快取問題（未帶旗標重試打 LLM 的頻率上限）屬 promotion-backlog 待辦（另案），本 change 不處理。
2. `.service` 的 `ExecStart` 是否改為經 wrapper 呼叫以單點維護 promoter 旗標——超出最小 diff，留給 dream service 後續整併。
