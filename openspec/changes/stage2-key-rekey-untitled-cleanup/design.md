## Context

issue #177（audit wf_2bd0b606 `untitled-and-orphan-dirs`，PARTIAL 驗證後修正版）。關聯 #100、#151、#147。

live 現況（2026-07-02）：
- 8 筆真筆記卡在舊 raw-remote key：`github.com/hamanpaul/testpilot` 4 筆（06-17 06:49 UTC）、`vcs-sw2.arcadyan.com.tw/airoha/airoha_openwrt_feed` 4 筆（06-17 06:27 UTC）；retrieval.db 同時存在新 slug（testpilot=33、airoha=6）與舊 key（各 4）。
- 13 筆 `title: untitled` 全在 `knowledge/serialwrap/`（4 筆 created_at=2026-06-22、9 筆=2026-06-25，皆在 #151 修復前；9 個 distinct checksum、4 對跨 session 重複）。
- 12 個空目錄 + 對應孤兒 `<key>-moc.md` 殘留在 knowledge root。

本 change 交付三個工具（rekey CLI、固定清單 prune、janitor lint），ops 執行另議。

## Goals / Non-Goals

**Goals:**

- 提供帶 manifest、dry-run/apply 雙態的一次性 rekey 遷移工具，讓舊 raw-remote key 筆記可安全併入短 slug 桶並立即恢復 recall 可見性。
- 提供 prune-noise 固定清單模式，讓「人工核定的明確清單」成為刪除權威，取代不可靠的 corpus 全桶掃描。
- janitor 對 `title: untitled` 與 raw-remote key 常駐告警（dream ledger 可見），消除「靠人工 audit 才發現」的盲點。

**Non-Goals:**

- 不執行 live 記憶的任何刪除／搬移（ops 依 Migration/Ops 段另議）。
- 不改 `project_resolver.py:114` 的 raw-remote fallback（政策決定，見 Open Questions）。
- 不改 `noise.py` classifier 規則、不加長度閾值。
- 不做 janitor 自動修復（lint 只告警；修復工具是 rekey/retitle/prune）。

## Decisions

### 1. 固定清單是刪除權威，不是 corpus（VERIFY correction C）

原 audit recommendation「`prune-noise --project serialwrap --instruction-root .../serialwrap/AGENTS.md`、核 manifest 恰 13 列」已被驗證者實測推翻：現行 AGENTS.md 當 corpus 會出 ~34 列 manifest——僅含 8/13 筆 untitled，另掃進 26 筆有標題真筆記（`mcu-flash-55-dev-ttymcu-pr-66--` 等疑為筆記先併入 AGENTS.md 的真知識 echo）；且 5/13 筆 body 僅 heading+1 行，低於 `noise.py:92` `_DOC_FRAGMENT_MIN_CONTENT_HITS=2`，設計上永遠不會被判 doc-fragment。**因此嚴禁以現行 serialwrap AGENTS.md 當 corpus 全桶 prune。**

`--paths <file>` 模式的契約：清單即權威（不需 classify_noise 同意，manifest reason=`listed`）；驗證 fail-closed——任一路徑不存在、resolve 後不在 `<memory-root>/knowledge/` 之下、是 `-moc.md`、或 frontmatter 非 `memory_layer: knowledge`，整批以 exit code 2 中止且零刪除。與 `--instruction-root`／`--project` 互斥（混用語義不明，直接拒絕）。沿用既有 #139 finding 2 慣例：任何 unlink 之前 manifest 先落盤。

### 2. rekey = 改 frontmatter + 搬檔 + run_moc，嚴禁手改 retrieval.db

recall 兩條路徑都以 project 嚴格相等（`moc/search.py:100` `AND m.project = ?`；`wakeup/builder.py:88-112` 先 `sanitize_project_component` 掃 `knowledge/<safe>/` 目錄、再驗 frontmatter project 相等），所以遷移必須**同時**改 frontmatter `project` 與搬檔到 `knowledge/<sanitize(new_slug)>/`，缺一都會產生撕裂狀態。index 一律由 `moc/runner.py::run_moc`（reconcile → linker → build_mocs → faceout → search.build_index）重建，不直接碰 `runtime/indexes/retrieval.db`。

模式仿 `retitle.py`：dry-run 產 manifest（`runtime/ledger/rekey-<now>.jsonl`，原子寫入）不動檔；apply 逐筆處理後有成功筆數才觸發 run_moc。`--to` 必須通過 `atomizer/config.py::is_safe_path_component`（不得含 `/`），否則 CLI 以 exit code 2 拒絕。

### 3. conflict fail-safe：目標檔已存在 → 整筆跳過、frontmatter 不 stamp

與 retitle 的「stamped（改 frontmatter 但不 rename）」不同：rekey 若只 stamp 不搬檔，檔案 frontmatter 指向新 project 卻躺在舊 key 目錄——wakeup 目錄掃描看不到、moc_builder（按 frontmatter 分組）又看得到，形成撕裂。因此 target 已存在時該筆記 `conflict`、source 完全不動，留給人工裁決。

### 4. rekey apply 順手收尾自己清空的舊 key 目錄與孤兒 moc

apply 成功搬走全部檔案後，若 `knowledge/<sanitize(old_key)>/` 已空則 rmdir、`knowledge/<sanitize(old_key)>-moc.md` 存在則 unlink（run_moc 重建只寫現存 project 的 moc，不會清 stale moc 檔）。這是遷移語義的一部分且可測；**既有的 12 個空目錄與其孤兒 moc 不在此範圍**（屬 ops 清單化刪除）。

### 5. lint 落點：counts 進 janitor summary，逐筆進 warnings

dream orchestrator `_run_pass`（`dream/orchestrator.py:36-49`）只把每個 pass 的 `summary` 寫進 dream ledger、warnings 文字全數丟棄（audit promotion-backlog 已證實此靜默）。因此 lint counts 必須放 `run_scan` 回傳的 `summary["lint"] = {"untitled": N, "raw_remote_key": M}` 才會出現在 `dream.jsonl` 的 `passes.janitor`。同時每筆 finding 以 `lint:<rule>: <path> (project=<key>)` append 到 warnings：CLI 直跑可見，且 warnings 非空會把 janitor pass 標為 not-clean → dream status=`partial`——這是刻意的持續告警語義，ops 清理完成後自動回綠。

lint 規則落在 `janitor/rules.py` 新純函式 `plan_lint(records)`（與 `plan_scan` 同風格：純函式、determinstic、按 record_id 排序），`KnowledgeRecord` 擴 `title`/`project` 兩欄（dataclass 尾端帶預設值 `""`，既有建構呼叫不破）。lint 只讀：不寫 lifecycle 事件、不動檔案。

## Risks / Trade-offs

- **run_moc 的 naming.reconcile 可能再調整檔名**：rekey 後 reconcile 依 `<slugify(title)>--<slice_id>.md` 規則重命名；slice_id 不變、MOC/relations 以 slice_id 索引，安全。manifest 記錄的是 rekey 當下的 target 路徑。
- **lint 讓 dream status 長期 partial**：直到 ops 清完 13+8 筆為止。這是預期告警；若日後嫌吵再議 threshold／抑制清單，不在本 change。
- **固定清單 prune 後 retrieval index 延遲**：listed 模式沿用既有 prune-noise 行為（apply 後 `build_mocs`，index 等下一輪 dream moc pass 重建）；rekey 因涉及可見性切換才用完整 run_moc。
- **`--from` 打錯 key**：dry-run 預設 + manifest 核對是防線；old_key 完全比對（嚴格相等），不做模糊匹配。

## Migration / Ops Plan（不在 PR 內，工具 merge 後另議執行）

| 步驟 | 動作 | 驗收 |
|---|---|---|
| 1 | 13 筆 untitled：`ls ~/.agents/memory/knowledge/serialwrap/untitled--*.md` 產固定清單檔 → `memory knowledge prune-noise --paths <file> --dry-run` | manifest 恰 13 列、reason 全 `listed`；超出即停 |
| 2 | 同命令 `--apply` | 13 筆刪除、serialwrap 其餘 71 筆不動 |
| 3 | `memory knowledge rekey --from github.com/hamanpaul/testpilot --to testpilot --dry-run` → 核 manifest 恰 4 列 → `--apply` | 4 筆入 `knowledge/testpilot/`、`memory search --project testpilot` 可召回 |
| 4 | `memory knowledge rekey --from vcs-sw2.arcadyan.com.tw/airoha/airoha_openwrt_feed --to airoha` 同上 | 4 筆入 `knowledge/airoha/` |
| 5 | 12 空目錄 + 孤兒 `-moc.md`：`find ~/.agents/memory/knowledge -maxdepth 1 -type d -empty` 核對清單後刪除（rekey 已自動清掉步驟 3/4 的兩組） | dream janitor lint counts 歸零、dream status 回 ok |

回滾：rekey/prune 的 manifest 是完整審計記錄；刪除為 hard delete，apply 前 dry-run 核對是唯一防線（與既有 prune-noise 一致）。

## Open Questions

1. `project_resolver.py:114` 對未登錄 remote 的 raw fallback 要不要改為「寫 projects.yaml 草稿／匯入時告警」？屬政策決定，本 change 先以 janitor lint 兜底。
2. lint 是否需要「已知待清單」抑制機制以免長期 partial 造成告警疲勞？等 ops 清完看殘量再議。
3. retrieval.db 只有 161 列 vs knowledge 296 檔的索引覆蓋缺口（audit open question）另開 audit，不在本 change。
