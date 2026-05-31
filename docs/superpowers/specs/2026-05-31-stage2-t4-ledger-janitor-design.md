# Stage 2 — Topic 4：Lifecycle Ledger + 最小 Janitor 設計

- 日期：2026-05-31
- 範圍：Stage 2 Topic 4（Ledger schema/IO + decayed/reactivation 治理）
- 前置：Topic 1（記憶基底樹）✅、Topic 2（Importer）✅、Topic 8（治理層 policy）✅
- 後續解鎖：Topic 7（Retrieval 消費 active-set）、Topic 5（Dream service 接手 janitor 服務化與 replay）
- 依據：`openspec/specs/stage2-memory-governance/spec.md`、`paulshaclaw/janitor/service.md`、`paulshaclaw/memory/routing.md`

---

## 1. 範圍與邊界

### In scope
1. **啟用 knowledge 層為架構**：定義 janitor 讀取的 knowledge record 讀取契約與路徑。`knowledge/` 已是 tree placeholder，T4 讓它成為可被治理的對象。
2. **Lifecycle ledger**：新增 `~/.agents/memory/runtime/ledger/lifecycle.jsonl`，append-only + flock，事件型別 `decayed` / `reactivation`，以 record id 為 key。
3. **最小 janitor（含 decay 判斷行為）**：確定性規則 — TTL 過期、來源失效、被 supersedes 取代；reactivation 由 reimport 觸發。
4. **高信任集合 read API**：fold `lifecycle.jsonl` 算出當前 active 集合，供 Topic 7 retrieval 消費。
5. **E2E 測試**：用 fixture knowledge records 驗 active → decayed → reactivated 全流程。

### Out of scope（明確劃走）
- inbox → work-centric → knowledge 升級 / atomize（**Topic 3**）。T4 不填充 knowledge，只讀。
- replay bundle（**Topic 5**）。
- dream orchestration、janitor 的 systemd 服務化（**Topic 5**）；T4 只給一次性 CLI / callable。
- materialized index 效能優化（未來 Topic 7 需要時再加）。
- embedding / vector / graph。

### 硬約束（來自 governance）
Stage 2 **不得擴充 Stage 3 frontmatter schema**（`slice_id / artifact_kind / supersedes / checksum` 歸 Stage 3）。janitor **只能讀既有欄位 + 設定檔**，不得為 TTL / 來源失效新增 per-record 欄位：

| janitor 需求 | 既有來源 |
|---|---|
| record id | `slice_id`（Stage 3） |
| 取代偵測 | `supersedes`（Stage 3） |
| 來源失效 | 既有 `provenance.{repo,commit,path}` 是否可解析 |
| TTL | **設定檔驅動的衰減年齡門檻**，套在既有 `captured_at` 上（非 per-record 欄位） |

---

## 2. 架構與元件

核心原則：**純決策邏輯（rules）與 IO/orchestration（scanner/ledger）分離**，讓決策核心可完全單元測試，IO 層保持薄。

```
paulshaclaw/memory/
├── ledger/
│   ├── lifecycle.py        # lifecycle 事件 schema + append/read IO + flock（純 IO）
│   ├── retrieval_set.py    # fold lifecycle.jsonl → 高信任 active 集合（Topic 7 read API）
│   └── import_log.py       # 讀取既有 import.jsonl 的 read API（reactivation 訊號來源）
└── janitor/
    ├── record_source.py    # layer-agnostic：列舉 knowledge/ 記錄 + 抽出 janitor 需要的欄位
    ├── rules.py            # 純決策邏輯：decay / reactivation 判斷（無 IO，可測核心）
    ├── scanner.py          # orchestrator：接 record_source + ledger → rules → 寫事件
    ├── cli.py              # `psc memory janitor scan [--dry-run]`（一次性；服務化留 Topic 5）
    ├── config.py           # TTL 門檻 / 來源檢查開關 loader（沿用 policy loader 模式）
    └── lifecycle.yaml      # 預設設定（可被 ~/.config override）
```

### 元件職責與依賴

| 元件 | 職責 | 依賴 | 主要介面 |
|---|---|---|---|
| `ledger/lifecycle.py` | 寫/讀 lifecycle 事件，flock 並發 | stdlib | `append_event()` / `read_events()` |
| `ledger/retrieval_set.py` | fold 事件 → active 集合 | lifecycle.py | `active_records(candidate_ids)` / `record_state(id)` |
| `ledger/import_log.py` | 讀 import.jsonl（只讀） | stdlib | `iter_import_events()` / `events_for_session(sid)` |
| `janitor/record_source.py` | 列舉 knowledge 記錄，抽 `slice_id` / `supersedes` / source_key / `captured_at` / provenance | frontmatter 解析 | `iter_records(knowledge_root)` |
| `janitor/rules.py` | **純函式**：給定（records, import 事件, lifecycle 狀態, config, now）→ 要 emit 的事件清單 | 無 | `plan_scan(...)` / `decide_decay()` / `decide_reactivation()` |
| `janitor/scanner.py` | 一輪掃描：讀齊輸入 → 呼叫 rules → 寫事件 | 上列全部 | `run_scan(memory_root, config, now)` |
| `janitor/cli.py` | 一次性入口 | scanner, config | `scan` subcommand |

### 身份接合（影響 reactivation）
- `import.jsonl` 以 `idempotency_key = <agent>:<session>` 為 key；knowledge 記錄以 `slice_id` 為 key——兩套身份空間，連接兩者的「session → knowledge」對應屬 Topic 3，尚未實作。
- T4 解法（不新增欄位）：knowledge 記錄本來就帶 provenance / source refs。`record_source` 從既有 `source_agent` + `source_session` 組出 `source_key = <agent>:<session>`，**正好等於 import.jsonl 的 idempotency_key**。
  - **reactivation**：某已 decayed 記錄的 source_key 在 decay 事件後又出現新的 import `written/updated` → reactivate。
  - **source 失效 decay**：`provenance.path` 不再能解析 → 判 decay。

---

## 3. 資料模型

### A. Knowledge record 讀取契約（`record_source` 抽取，全用既有欄位）

| janitor 用途 | 來源欄位 | 既有歸屬 |
|---|---|---|
| record id | `slice_id` | Stage 3 |
| 取代偵測 | `supersedes`（list） | Stage 3 |
| 層過濾 | `memory_layer == "knowledge"` | importer |
| 接 import ledger | `source_agent` + `source_session` → `<agent>:<session>` | importer |
| TTL 基準時間 | `captured_at` | importer |
| 來源失效檢查 | `provenance.{repo,commit,path}` | importer |

In-memory view：
```
KnowledgeRecord(record_id, supersedes[], source_key, captured_at, provenance{repo,commit,path}, path)
```
> Topic 3 未來產生的 knowledge 記錄須符合此讀取契約，但不擴充 Stage 3 必填集。

### B. `lifecycle.jsonl` 事件 schema（`schema_version: "1"`）

共同欄位：`schema_version` / `event_type`（decayed|reactivation）/ `record_id`（=slice_id）/ `ts`（ISO8601，注入，測試可固定）/ `reason` / `janitor_config_hash`（effective config 的決定性 hash，對齊 `effective_policy_hash` 精神，使每次判斷可復現）。

**decayed** 另含（governance：須保留原始引用）：
- `original_ref`：`{slice_id, source_key, provenance}` 快照
- `reason`：`ttl_expired` | `source_invalid` | `superseded`
- `detail`：依 reason → `{superseded_by}` / `{source_check, ref}` / `{age_days, threshold_days}`

**reactivation** 另含（governance：須 append record-agent-reference）：
- `agent_ref`：重新支持它的 `<agent>:<session>`
- `reason`：`reimport`；`detail`：`{import_status, import_ts}`

```json
{"schema_version":"1","event_type":"decayed","record_id":"sl-001","ts":"2026-05-31T02:30:00Z",
 "reason":"superseded","detail":{"superseded_by":"sl-007"},
 "original_ref":{"slice_id":"sl-001","source_key":"claude:sess-abc","provenance":{"repo":"paulshaclaw","commit":"deadbeef","path":"docs/x.md"}},
 "janitor_config_hash":"a1b2c3"}
{"schema_version":"1","event_type":"reactivation","record_id":"sl-001","ts":"2026-05-31T03:00:00Z",
 "reason":"reimport","agent_ref":"claude:sess-def","detail":{"import_status":"updated","import_ts":"2026-05-31T01:00:00Z"},
 "janitor_config_hash":"a1b2c3"}
```

### C. `lifecycle.yaml` 設定（預設 + `~/.config/paulshaclaw/janitor.override.yaml` 合併）

```yaml
schema_version: 1
ttl:
  default_decay_age_days: 90        # captured_at + N < now → ttl_expired
  by_artifact_kind: {}              # 可選：依 Stage 3 artifact_kind 覆寫
source_checks:
  check_provenance_path: true       # provenance.path 無法解析 → source_invalid
  check_provenance_commit: false    # 預設關（需 git context）
supersede:
  decay_superseded: true            # 被別人 supersedes 指到 → decay
```
`janitor_config_hash = sha256(canonical_json(effective_config))`。

### D. Active-set fold 語意（`retrieval_set`）
- 每個 record_id 取**最新 ts** 的事件；`decayed` → 排除、`reactivation` → 納入。
- 無任何 lifecycle 事件的 record → **預設 active**。
- `active_records(candidates)` 回傳仍 active 的子集（Topic 7 消費）。

---

## 4. 資料流

### `scanner.run_scan(memory_root, config, now)` 一輪掃描
```
1. 載入輸入
   - records      = record_source.iter_records(knowledge/)        # memory_layer==knowledge
   - import_index = import_log：每個 source_key 的 written/updated 事件（含 ts）
   - lc_state     = lifecycle.read_events() → fold 成每個 record_id 的當前狀態
   - config + janitor_config_hash
2. rules.plan_scan(records, import_index, lc_state, config, now) → [events]   # 純函式
3. scanner 依序 lifecycle.append_event(flock) 落盤（dry-run 則只回傳 plan）
4. 回傳 summary: {decayed, reactivated, unchanged, scanned, skipped, config_hash}
```

### 每筆 record 的決策狀態機（`rules` 純邏輯）
```
[*] --(無 lifecycle 事件，預設)--> active
active --(decay 規則命中，優先序)--> decayed
decayed --(reactivation: reimport)--> active

decay 規則（第一個命中即止）：
  1. superseded     — record_id 出現在他人 supersedes
  2. source_invalid — provenance.path 不可解析
  3. ttl_expired    — now - TTL基準 > 門檻
reactivation：
  source_key 在「decay 事件 ts 之後」有新的 import written/updated
```
- 當前 active → 跑 decay 規則（superseded → source_invalid → ttl，第一個命中即 emit `decayed`）；全不中 → 不動。
- 當前 decayed → 只跑 reactivation；命中 → emit `reactivation`；否則維持 decayed。
- 同一輪一筆 record 只會有一種轉移。

### 三個關鍵正確性設計
1. **冪等（重跑安全）**：事件 emit 與否由 folded 狀態把關。已 decayed 的 record 下輪不再跑 decay 規則（只評估 reactivation），重跑同輸入不會產生重複 decayed。reactivation 同理。
2. **防 flap：TTL 基準時間 = `max(captured_at, 最近一次 reactivation 的 import_ts)`**。reimport 是新證據，讓它重置衰減時鐘，否則 captured_at 很舊的記錄被 reactivate 後會立刻又 TTL-decay，造成抖動。
3. **supersede 鏈反轉明確 out of scope**：A 被 B 取代而 decay 後，即使 B 自己後來 decay，A 不會自動 reactivate；只有 reimport 能救回。

### 邊界處理
- `source_session == _unknown`（importer fallback）：無法可靠對應 import ledger → 該 record 無法經 reimport reactivate，維持 decayed，記一筆 WARN。
- **單一 source_key**：現行 importer frontmatter 的 source 是純量，T4 實作單一 source_key；未來 Topic 3 若產生多來源記錄，讀取契約再擴成 `source_keys[]`（forward-compat，現在 YAGNI）。

---

## 5. 錯誤處理 & Guardrails

### 失敗模式與處置
原則：**核心狀態（lifecycle 自身）出錯 → fail-closed 中止；輔助訊號（import / 單筆 record）出錯 → 降級續做**。

| 失敗 | 風險 | 處置 |
|---|---|---|
| `lifecycle.yaml`/override 載入失敗、不支援的 `schema_version` | 用未知設定掃描會誤判 | **fail-closed**：中止、exit≠0、不寫任何事件 |
| `lifecycle.jsonl` 讀取有壞行 | 核心狀態汙染 | **fail-closed**：中止，WARN 標行號 |
| `lifecycle.append_event` 失敗（磁碟滿/flock timeout） | 落盤不全 | **fail-closed**：停止後續 append、回報 partial、exit≠0。已寫的行仍有效（append-only），靠冪等重跑續做 |
| flock 競用 | 並發 | lifecycle 用獨立鎖 `runtime/locks/lifecycle-ledger.lock`，逾時 WARN + exit≠0 |
| 單筆 record 缺 `slice_id` / frontmatter 壞 | 局部 | 跳過該筆 + WARN，計入 summary `skipped`，不中止整輪 |
| `import.jsonl` 缺失 / 壞行 | 輔助訊號（只影響 reactivation） | 缺失→無 reimport 證據（decay 照常）；壞行→跳行 WARN 續做 |
| `provenance.path` 無法判定（repo 未 checkout） | 可能誤 decay | **fail-safe：不確定就不 decay**——只有能明確判定路徑已消失才判 source_invalid |

WARN/error 寫入 `~/.agents/memory/log/janitor.log`（對齊 `hooks.log` / `policy.log`），不輸出任何記錄內文。

### Guardrails

| # | 規則 | T4 如何保證 |
|---|---|---|
| G1 | janitor 不修改 raw artifact | 對 `knowledge/` 記錄唯讀，只 append `lifecycle.jsonl` |
| G2 | 不定義/擴充 Stage 3 frontmatter | 只讀既有欄位（§3 契約） |
| G3 | reactivation 須可追證據來源 | 事件強制帶 `agent_ref` + `import_ts` |
| G4 | ledger 不含機敏原文 | 事件只存 id/ref/hash，不存記錄內文（讀的已是 redacted 的 knowledge） |
| G5 | append-only，不改寫歷史 | 修正以新事件覆蓋（reactivation 蓋過先前 decay），永不編輯/刪行 |
| G6 | 決定性 | `now` 注入、無隨機；同輸入→同 plan，由 `janitor_config_hash` 可追溯 |

### 與 policy 層的關係
lifecycle 事件只帶 `janitor_config_hash`（治理 janitor 決策的設定），不冒充 policy 層、不帶 `effective_policy_hash`，避免過度耦合。

---

## 6. 測試策略（TDD，fixture E2E 為主目標）

依 repo 慣例先寫失敗測試再實作；`now` / `ts` 全注入，場景可復現。

### 單元測試（決策核心優先）

| 測試檔 | 覆蓋 |
|---|---|
| `test_janitor_rules.py`（核心） | decay：superseded/source_invalid/ttl 各命中、優先序（superseded > ttl）、全不中維持 active；reactivation：decay ts 之後 reimport→觸發、之前→不觸發、無 import→不觸發、`_unknown` source_key→不觸發；anti-flap：TTL 基準=max(captured_at, reactivation import_ts)；冪等：已 decayed 狀態餵入→decay 規則跳過；決定性：同輸入→同 plan |
| `test_lifecycle_ledger.py` | append/read round-trip、schema 欄位齊全、flock 並發不壞、fold 語意（latest-wins、decayed 排除/reactivation 納入/無事件預設 active）、`active_records()`、壞行→fail-closed raise |
| `test_import_log.py` | `events_for_session`、缺檔→空、壞行→跳行+warn |
| `test_janitor_source_config.py` | record_source 抽欄位、缺 `slice_id`→跳過+warn、`memory_layer` 過濾；config 預設/override 合併、`janitor_config_hash` 決定性、不支援 schema_version→fail-closed |

### E2E（經 CLI 跑 scanner 過 fixtures）

`test_janitor_e2e.py`，每場景建臨時 memory root + fixture knowledge 記錄 + seeded `import.jsonl`：

| 場景 | 斷言 |
|---|---|
| A decay-TTL | 過期記錄→1 筆 `decayed(ttl_expired)`；`active_records` 排除它 |
| B decay-superseded | sl-007 `supersedes:[sl-001]`→sl-001 `decayed(superseded, superseded_by=sl-007)` |
| C decay-source | `provenance.path` 不存在→`decayed(source_invalid)` |
| D reactivation 全循環 | run1 decay → 為其 source_key seed decay 後的新 import → run2 出 `reactivation`；active 重新納入 |
| E 冪等重跑 | 連跑兩次，第二次 emit 0 新事件 |
| F anti-flap | 舊 captured_at→decay→reimport reactivate→再掃不立即重 decay |
| G dry-run | `--dry-run` 印 plan，`lifecycle.jsonl` 零寫入 |
| 安全 | `lifecycle.jsonl` 內無記錄內文/機敏原文（G4） |

### Fixtures & 整合
- `paulshaclaw/memory/tests/fixtures/knowledge/<case>/*.md` — 手寫符合讀取契約的 knowledge 記錄 + seeded `import.jsonl`。
- 擴充 `stage2_integration_check.sh`：加一條 janitor dry-run over fixtures（比照 importer dry-run）。
- 回歸：`unittest discover -s paulshaclaw/memory/tests` 與 `tests/` 全綠。

---

## 7. 解鎖的後續（非本 change 範圍）
- **Topic 7 Retrieval**：消費 `retrieval_set.active_records()` 作為 lexical+relation 檢索的可見集合。
- **Topic 5 Dream service**：把一次性 `janitor scan` 服務化（systemd timer）、接 replay bundle、引入非確定性的 reactivation 觸發（人工確認 / replay 驗證）。
- **Topic 3 Atomizer/Linker**：真正填充 knowledge 層並建立 session→slice 對應，讓 janitor 從 fixtures 轉為實資料。
