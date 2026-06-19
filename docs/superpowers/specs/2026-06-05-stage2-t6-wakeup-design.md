# Stage 2 — Topic 6：wake-up（session 起手記憶注入 + PreCompact 擷取）設計

- 日期：2026-06-05
- 範圍：T6 = 記憶系統的**讀取/注入側**(T2 importer 擷取的鏡像)。session 啟動時依當前 project 從 `~/.agents/memory/knowledge/` 撈相關記憶,注入給 agent;另含 **PreCompact 擷取觸發**——壓縮前先把當下 session 快照保存,避免細節被壓縮摘要掉。
- 命名:`paulsha-memory` = Stage 2 整體;本層是 code module（`paulshaclaw/memory/wakeup/`），非 skill。
- 前置（皆完成）:T1 substrate、T2 importer（`project_resolver`、session-end hook、`capture_scope`/idempotency）、T3/T3.2 atomizer、T4 ledger（`lifecycle`/`retrieval_set`）、T5 dream、T7 moc（`knowledge/<project>-moc.md` + 搜尋索引）、T8 governance。
- 與 T9 區分:T9 sync-back gate 是「把調校過的 `paulsha-memory` skill 回寫 `custom-skills` repo」的治理關卡,與本層無關。「session 總結/蒸餾」屬 T3 atomizer;本層只負責**注入**與**壓縮前擷取**,不做即時蒸餾。

---

## 0. 邊界（headline）

T6 **零重複**既有能力,只讀其輸出 / 觸發既有 pipeline:

| 能力 | 擁有者 | T6 怎麼用 |
|---|---|---|
| project 解析（cwd / git / remote → slug，含跨 folder 同專案） | importer/`project_resolver` | session-start 讀 payload `cwd` → 解析,**不重做** |
| recency（`last_event_ts`）/ active 過濾 | `ledger/lifecycle` + `ledger/retrieval_set` | 取最近 K active slice,**不重算** |
| 專案地圖（MOC） | moc/`moc_builder`（T7） | 直接讀 `knowledge/<project>-moc.md` |
| session 擷取 → inbox + idempotency | importer（T2） | PreCompact hook 觸發既有 importer，`capture_scope="pre_compact"` |
| hook 安裝/薄殼/fail-open 慣例 | hooks/`install.sh`（T2） | 沿用,新增 SessionStart / PreCompact 段 |

**新增僅**:`memory/wakeup/`（builder + cli）、session-start hook（claude/copilot）、precompact hook（claude/copilot）、`install.sh` 增兩段、`importer/pipeline._SCOPE_RANK` 增一個 key。

---

## 1. 範圍

### In scope
- `memory/wakeup/builder.py`:`build_brief(memory_root, project, *, now, k=8, char_budget=8000) -> str` — 產出「MOC primer + 最近 K 指標」brief。
- `memory/wakeup/cli.py`:`psc memory wakeup --project X [--cwd P] [--memory-root R]` — 印 brief。
- `hooks/claude_session_start.py`、`hooks/copilot_session_start.py`:讀 cwd → 解 project → 呼叫 builder → 各 CLI 的 `additionalContext` 管道輸出。Codex 共用 Claude 的 SessionStart hook。
- `hooks/claude_precompact.py`、`hooks/copilot_precompact.py`:壓縮前觸發既有 importer 擷取,`capture_scope="pre_compact"`。
- `install.sh`:新增 Claude `SessionStart`/`PreCompact`、Copilot `sessionStart`/`preCompact` 設定段;`uninstall.sh` 對稱移除。
- `importer/pipeline._SCOPE_RANK`:加 `"pre_compact": 0`（等同 turn 快照層級）。

### Out of scope
- ❌ 即時 atomize/蒸餾（壓縮前只擷取,蒸餾交 dream/T3）。
- ❌ query 式 mid-session 檢索（wake-up 是起手定向;深讀走既有 `moc.search` on-demand，非本 change）。
- ❌ 改 importer/atomizer/moc 既有行為（只讀輸出 / 觸發 / 加一個 scope key）。
- ❌ T9 sync-back。

### 約束
- **fail-open**:wake-up / precompact 任一失敗**絕不**阻擋 session 啟動或壓縮;輸出空 + 記 `log/hooks.log` + exit 0。
- **決定性**:builder 對固定輸入為純函式,`now` 注入(不取牆鐘);測試以 fixtures 驗。
- **唯讀**:wake-up 不寫 knowledge / 不改 ledger（MVP 不記 retrieval 事件）。

---

## 2. 架構與元件

```
paulshaclaw/memory/wakeup/
├── __init__.py
├── builder.py     # build_brief()：MOC primer + 最近 K 指標，預算截斷
└── cli.py         # psc memory wakeup --project X

paulshaclaw/memory/hooks/   （新增 4 個薄殼 + install.sh 增段）
├── claude_session_start.py     # SessionStart → additionalContext
├── copilot_session_start.py    # sessionStart → {additionalContext}
├── claude_precompact.py        # PreCompact → 觸發 importer 擷取
└── copilot_precompact.py       # preCompact → 觸發 importer 擷取
```

| 元件 | 職責 | 依賴 | 介面 |
|---|---|---|---|
| `builder.py` | 組 brief（MOC + 最近 K，預算內） | lifecycle/retrieval_set、moc 輸出檔 | `build_brief(memory_root, project, *, now, k=8, char_budget=8000) -> str` |
| `cli.py` | CLI 入口 | builder、project_resolver | `psc memory wakeup --project X [--cwd P]` |
| `*_session_start.py` | 讀 cwd→project→builder→注入 | builder、project_resolver | hook（薄殼，fail-open） |
| `*_precompact.py` | 觸發 importer 擷取 | importer cli/queue | hook（薄殼，fail-open） |

### 注入管道（已查證）
- **Claude** `SessionStart`：hook 輸出 `hookSpecificOutput.additionalContext`（或 stdout）注入。
- **Copilot** `sessionStart`：payload `{sessionId, timestamp, cwd, source, initialPrompt}`；hook 回傳 `{"additionalContext": "..."}`（或 exit 2 + stdout）。
- **Codex**：接 Claude 的 SessionStart/PreCompact hook（實作時驗證）。

---

## 3. 資料模型

### Brief 格式（注入為 markdown 字串）
```
# Memory wake-up — <project>

## Map
<knowledge/<project>-moc.md 內容；超預算則尾部截斷並標 "…(truncated)">

## Recent
- [[<title>--<slice_id>]] — <一行摘要> (<last_event_ts>)
  …（最近 K 筆，依 last_event_ts 由新到舊，active only）
```
- **一行摘要** = slice `title` ＋ body 首個非空行（截至 ~120 字元）。
- **連結** = Obsidian wikilink `[[<title>--<slice_id>]]`（對齊 T7 檔名），agent 可 on-demand 開啟。
- **Recent 來源**:`lifecycle.read_events` fold 出每 record 的 `last_event_ts` → 過 `retrieval_set` active → 取當前 project、依 ts 由新到舊前 K。
- **預算**:總字元上限 `char_budget`。優先保 `## Recent`（連續性）＋ `## Map` 開頭;超量先截 Map 尾部。

### project 解析
- CLI:`--project` 直給;或 `--cwd P` → `project_resolver.resolve_project(cwd=P, ...)`。
- hook:payload `cwd` → `resolve_project`;解不出 → `_unknown`。
- `project == _unknown` 或該 project 無 active slice → brief 為空字串。

### PreCompact 擷取
- hook 取得當下 session（Claude PreCompact 提供 transcript 路徑;Copilot preCompact payload）→ 寫 queue payload（`capture_scope="pre_compact"`）→ 觸發既有 importer。
- `_SCOPE_RANK["pre_compact"] = 0`：與 turn 同級;之後更完整的 `session_end`(rank 1)/`watcher_final`(rank 2) 會經既有 idempotency 蓋過,無重複、無 schema 變更。

---

## 4. 資料流

**Wake-up（session 起手）**
```
session start → hook 讀 payload.cwd
  → project = resolve_project(cwd)
  → brief = build_brief(memory_root, project, now=<hook 時間>)
       1. 讀 knowledge/<project>-moc.md（無則 Map 空）
       2. lifecycle fold → active(retrieval_set) → 當前 project → 依 ts 取前 K
       3. 組 Map + Recent，套 char_budget 截斷
  → 經 additionalContext 注入；空字串則不注入
  （任何例外 → 空輸出 + log + exit 0）
```

**PreCompact（壓縮前）**
```
壓縮觸發 → precompact hook
  → 取當下 session（transcript / payload）
  → 寫 queue payload(capture_scope="pre_compact") → 觸發 importer ingest
  （fire-and-forget；任何例外 → log + exit 0，絕不擋壓縮）
```

---

## 5. 錯誤處理 & Guardrails

| 失敗 | 處置（fail-open） |
|---|---|
| project 解不出 / 無 MOC / 無 slice | brief = 空字串;hook 不注入;exit 0 |
| lifecycle/retrieval_set 缺或損 | Recent 段省略,仍盡量出 Map;全失敗 → 空 brief |
| builder 例外 | 空輸出 + `log/hooks.log` + exit 0 |
| PreCompact 擷取失敗 | log + exit 0，**不阻擋壓縮** |
| Copilot/Claude 注入格式差異 | 各 hook 自負其輸出 schema;builder 回傳純 markdown 不綁 CLI |

| # | Guardrail | 保證 |
|---|---|---|
| W1 | fail-open | wake-up/precompact 永不阻擋 session 啟動或壓縮 |
| W2 | 零重複 | project/recency/MOC/擷取 全重用既有模組 |
| W3 | 唯讀 wake-up | 不寫 knowledge、不改 ledger |
| W4 | 決定性 | builder 純函式 + `now` 注入 |
| W5 | 預算上限 | brief 受 `char_budget` 約束,不灌爆 context |

---

## 6. 測試策略（TDD,注入 fixtures,不呼叫真 CLI/LLM）

| 測試檔 | 覆蓋 |
|---|---|
| `test_wakeup_builder.py` | MOC primer 納入;Recent-K 依 ts 由新到舊、active only、限 project;一行摘要格式;wikilink；預算截斷（先截 Map 尾、保 Recent）;空專案/無 MOC → 空 brief;`now` 注入決定性 |
| `test_wakeup_cli.py` | `--project X` 印 brief;`--cwd P` 經 resolver;未知 project → 空、rc 0 |
| `test_session_start_hooks.py` | 餵 claude/copilot sessionStart payload（含 cwd）→ additionalContext 格式正確;錯誤路徑 fail-open（exit 0 + log） |
| `test_precompact_hooks.py` | 餵 PreCompact/preCompact payload → 寫出 `capture_scope=pre_compact` queue payload;失敗 fail-open |
| `test_importer_scope_rank.py`（擴充既有） | `pre_compact` rank=0;session_end/watcher_final 經 idempotency 蓋過 pre_compact |

- 跑法:`python3 -m unittest discover -s paulshaclaw/memory/tests`。

---

## 7. 解鎖的後續（非本 change）
- query 式 mid-session 檢索（`moc.search` on-demand 注入）。
- wake-up 記 retrieval 事件供審計 / 回饋 ranking。
- PreCompact 後觸發輕量 atomize（若 dream 延遲過長）。
- 注入 ranking 納入 link_weight / 存取頻率（目前 recency-only）。
