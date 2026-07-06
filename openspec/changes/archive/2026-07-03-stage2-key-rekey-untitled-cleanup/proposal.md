## Why

audit `untitled-and-orphan-dirs`（verdict=PARTIAL，VERIFY corrections 已納入）確認 Stage 2 knowledge 層兩個獨立根因與一組殘留：

1. **project key 碎裂**：`paulshaclaw/memory/importer/project_resolver.py:114` 對未登錄 `projects.yaml` 的 repo fallback 回傳 raw remote（如 `github.com/hamanpaul/testpilot`）。2026-06-18 hardening 前產生的 8 筆真筆記（testpilot 4 + vendor-b 4）因 recall 兩條路徑都以 project 嚴格相等過濾（`moc/search.py:100` `AND m.project = ?`；`wakeup/builder.py:88-112` sanitize 目錄掃描＋frontmatter 相等），對新 slug session 永久不可見。目前 repo 沒有任何 rekey 遷移工具。
2. **untitled 殘留**：13 筆 `title: untitled` 全在 `knowledge/serialwrap/`（#151 修復前舊檔）；retitle 是 one-shot 且只跑過 `--project paulshaclaw`，dream loop 只有 atomize/janitor/moc 三個 pass，沒有常駐機制會發現或撿走殘留。
3. **清理工具缺口**：VERIFY 實測推翻「拿現行 serialwrap AGENTS.md 當 corpus 對 serialwrap 全桶 prune」的修法——manifest 會出 ~34 列（僅含 8/13 untitled，另掃進 26 筆有標題真筆記）；且 5/13 untitled 因 body 僅 heading+1 行、低於 `noise.py:92` `_DOC_FRAGMENT_MIN_CONTENT_HITS=2`，設計上永遠不會被判 doc-fragment。清理 13 筆需要「固定清單」刪除模式，而 prune-noise 目前只有 corpus 掃描模式。

本 change 只做「工具就緒」＋「防再發告警」；對 live 記憶的 ops 執行（13 筆 untitled 刪除、8 筆 rekey、12 空目錄＋孤兒 `-moc.md`）不在 PR 內、另議執行。

## What Changes

- 新增 `paulshaclaw/memory/rekey.py`：仿 `retitle.py` 的一次性 rekey 遷移（dry-run 產 manifest 不動檔；apply 改 frontmatter `project` + 搬檔到 `knowledge/<slug>/` + 觸發 `run_moc` 重建 MOC 與 retrieval index；嚴禁手改 `retrieval.db`）。
- `paulshaclaw/memory/cli.py` 新增 `memory knowledge rekey --from <old-key> --to <slug>` 子命令。
- `memory knowledge prune-noise` 新增 `--paths <file>` 固定清單模式：只刪清單內檔案、fail-closed（任一路徑不存在／超出 knowledge root／非 knowledge slice → 整批中止、零刪除）；與 `--instruction-root`／`--project` 互斥。
- janitor 新增 read-only lint：掃到 `title: untitled` 或 `project` 含 `/`（raw-remote key）→ counts 進 janitor summary（經 dream orchestrator 落 dream ledger）＋逐筆 warnings；不自動改。

## Capabilities

### New Capabilities

無。延伸既有 `stage2-memory-governance` capability。

### Modified Capabilities

- `stage2-memory-governance`：新增 rekey 遷移工具、prune-noise 固定清單模式、janitor untitled/raw-remote-key lint 三項 requirement。

## Impact

- Affected runtime code：`paulshaclaw/memory/rekey.py`（新）、`paulshaclaw/memory/cli.py`、`paulshaclaw/memory/janitor/{record_source,rules,scanner}.py`。
- Affected tests：`paulshaclaw/memory/tests/test_rekey.py`（新）、擴充 `test_prune_noise.py`、`test_janitor_rules.py`、`test_janitor_scanner.py`。
- 不動：`importer/project_resolver.py`（raw-remote fallback 行為是否改為告警屬政策決定，留 open question）、`retitle.py`、`noise.py` classifier 規則本體、`.github/workflows/**`、hooks。
- Non-Goals：live 記憶 ops 執行（固定清單刪 13 筆、rekey 8 筆、12 空目錄清理——見 design.md Migration/Ops）、retrieval.db 手動操作、resolver fallback 政策變更。
