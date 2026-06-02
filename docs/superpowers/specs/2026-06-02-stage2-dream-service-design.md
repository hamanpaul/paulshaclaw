# Stage 2 — Topic 5：Dream Service（編排 + Replay bundle）設計

- 日期：2026-06-02
- 範圍：T5 MVP = **A. Dream 編排服務** + **D. Replay bundle**;B/C 文件化為後續
- 前置：T2/T3/T3.2/T4 ✅(atomize + janitor + ledgers 皆已落地)、Stage 3 schema ✅
- 後續解鎖：Topic 6(wake-up bundle 消費 dream status)、Topic 7(retrieval)
- 依據：`openspec/specs/stage2-memory-governance/spec.md`、`paulshaclaw/janitor/service.md`、research doc 02 Phase 3、`monitor/service.py` 模式、`custom-claw-tools/obs-auto-moc`(proposal-first/status/runner 模式參考)

---

## 1. 範圍與邊界

### In scope（MVP = A + D）

**A. Dream 編排服務**
- `psc memory dream run [--dry-run] [--require-idle]`:依序跑 **atomize(T3/T3.2)→ janitor(T4)** over backlog,寫 **dream run ledger**(`runtime/ledger/dream.jsonl`)。
- `psc memory dream status`:回最後一次 run 摘要 + backlog 深度。
- **idle-check wrapper** + **systemd user unit/timer 範本**(OnCalendar Mon..Fri 05:00 → wrapper → `dream run --require-idle`)。
- **proposal-first 空框架**(`runtime/proposals/`):輸出位置 + human-review gate 契約;MVP 不產內容。
- 後端走 T3.2 既有 `agent_exec.command`(WSL 測試 Copilot CLI / prod gemma4-GB10,純 config)。

**D. Replay bundle**
- `psc memory bundle --project/--tag/--entity [--include-decayed] --out <dir>`:facet 組合 + active-set 選 slices → bundle(slices + ledger 事件),**絕不含 raw**。

### 文件化但不實作（A/B/C/D checklist，避免遺忘）
- **A. 編排服務** — 本 change。
- **B. 跨 session 演進脈絡**(supersede/演進鏈)— 後續;作為 dream task 插入,產 `supersede`/`merge` proposals 走 review gate。
- **C. 全域實體圖**(MTK/BRCM/kernel/OpenWrt/prplOS/DDR 聚合 T3.2 `mentions` 邊 + 正規化)— 後續 dream task。
- **D. Replay bundle** — 本 change。

### 不做 / 邊界
- ❌ B、C 實作;free-text 檢索(T7);wake-up bundle(T6);vector/graph backend。
- ❌ **不 base 在 `custom-skills/paulsha-memory`**(那是 T9 sync-back scaffold,非 dream);**不耦合 `obs-auto-moc`**(只借其 proposal-first/status/runner 模式)。
- ❌ MVP 無跨 session 自動改寫 — 遵 governance **proposal-first、canonical write gated**。

### 硬約束
- replay 只讀 distilled + ledger,**永不讀 raw prompts**(governance)。
- janitor/dream 是**獨立服務**(非 pipeline tail;由 timer 觸發,非 importer)。
- 不動 T2/T3/T3.2/T4 既有行為(只「編排」它們);沿用既有 ledger + `retrieval_set`。
- 注入 `now`、append-only + flock、log 無 raw。

---

## 2. 架構與元件

```
paulshaclaw/memory/
├── dream/
│   ├── orchestrator.py   # run_dream():建 promoter → atomizer.pipeline.run → janitor.scanner.run_scan → 寫 dream.jsonl
│   ├── idle.py           # is_idle(max_load) → bool（os.getloadavg）
│   ├── proposals.py      # Proposal + append/pending/requires_approval（MVP 空框架）
│   ├── cli.py            # dream run / dream status
│   ├── systemd/paulsha-memory-dream.{service,timer}   # 範本（OnCalendar Mon..Fri 05:00）
│   └── scripts/dream-idle-wrapper.sh                  # timer → dream run --require-idle
├── ledger/dream.py       # dream.jsonl run-record writer + last_run + backlog 深度
└── replay/
    ├── selector.py       # select(memory_root, project, tags, entity, include_decayed) → [slice paths]
    ├── bundle.py         # build(memory_root, slices, out_dir) → bundle（slices + ledger 事件，無 raw）
    └── cli.py            # bundle subcommand
```
+ 在 `memory/cli.py` 接 `dream`(run/status)與 `bundle` subparser。**命名**:`bundle` 而非 `replay`(後者已被 T8 policy replay 佔用)。

| 元件 | 職責 | 依賴 | 介面 |
|---|---|---|---|
| `dream/orchestrator.py` | 一輪 dream:atomize→janitor,寫 run record | atomizer.pipeline、janitor.scanner、ledger/dream | `run_dream(memory_root, *, atom_cfg, atom_hash, jan_cfg, jan_hash, promoter, now, dry_run)->dict` |
| `dream/idle.py` | 系統 idle 判斷 | os.getloadavg | `is_idle(max_load=...)->bool` |
| `dream/proposals.py` | proposal 輸出 + gate（MVP 空） | stdlib | `append/pending/requires_approval` |
| `ledger/dream.py` | dream.jsonl 寫/讀 + backlog | stdlib + flock | `append_run/last_run/backlog_depth` |
| `replay/selector.py` | facet + active-set 選 slice | retrieval_set、relations、knowledge fs | `select(...)->list[Path]` |
| `replay/bundle.py` | 組 bundle | lifecycle/relations/processing reader | `build(...)->Path` |

**重用(不重寫):** orchestrator 用 `atomizer.pipeline.run(..., now=, dry_run=, promoter=)`(line 438 keyword 入口)與 `janitor.scanner.run_scan(...)`;promoter 由 config 建(提取/重用 atomizer 的 promoter-building helper)。bundle 用 `retrieval_set.active_records()`、`relations.neighbors()`、既有 ledger reader。

**proposal 框架(MVP 僅骨架):** `runtime/proposals/<id>.json` + `requires_approval(kind)`;orchestrator 不產 proposal(B/C 填)。

---

## 3. 資料模型

> ledger `ts` 用注入 `now`;append-only + flock。

### A. `runtime/ledger/dream.jsonl`（每次 run 一筆）
```json
{"ts":"<now>","run_id":"dream-<now>","status":"ok|partial|failed",
 "passes":{"atomize":{"split_sessions":3,"slices":5,"skipped":0,"warnings":[]},
           "janitor":{"scanned":12,"decayed":2,"reactivated":1,"skipped":0}},
 "errors":[],"dream_config_hash":"<h>","dry_run":false}
```
- `status`:`ok`(兩 pass 乾淨)/`partial`(warning 或單 pass 降級)/`failed`(某 pass raise)。
- `dream status` = `last_run()` + backlog 深度(數 raw 區未處理 session)。

### B. `runtime/proposals/<proposal_id>.json`（MVP 骨架）
```json
{"proposal_id":"<id>","kind":"merge|supersede|decay|contradiction",
 "status":"pending|approved|rejected","created_ts":"<now>",
 "subject_slice_ids":[],"detail":{},"source":"dream-lineage|dream-entity","config_hash":"<h>"}
```
- API:`append(proposal)` / `pending()` / `requires_approval(kind)`(canonical 變更類 → True)。MVP orchestrator 不產;骨架供 B/C 填。

### C. Replay bundle 佈局
```
<out_dir>/
├── manifest.json     # selection facet、slice_ids、counts、generated_ts、raw_excluded:true
├── slices/<slice_id>.md   # 選中 distilled slice 副本（絕不 raw）
└── ledger.jsonl      # 觸及 slice 的 lifecycle/relations/processing 事件
```
```json
// manifest.json
{"generated_ts":"<now>","selection":{"project":"prplos-core","tags":["pwhm"],"entity":"MTK","include_decayed":false},
 "slice_ids":[...],"counts":{"slices":4,"ledger_events":11},"raw_excluded":true}
```

### D. Selector facet 語意
`select(memory_root, *, project=None, tags=None, entity=None, include_decayed=False) -> list[Path]`
- 起點:所有 `knowledge/**/*.md`,解析 frontmatter。
- 過濾(**facet 間 AND**,各可選):`project`==;`tags` ∩(**any-match**);`entity` via `relations.neighbors("entity:NAME")`。
- **active-set**:預設只留 `retrieval_set.active_records()`;`--include-decayed` 納入並標註 manifest。
- **至少一個 facet**;全空 → 報錯。

---

## 4. 資料流

### A. Dream run（`orchestrator.run_dream`）
```
1. now 注入;run_id = "dream-" + now
2. atomize pass: try atomizer.pipeline.run(..., now=now, dry_run=, promoter=) except → 記 error、降級
3. janitor pass: try janitor.scanner.run_scan(..., now=now, dry_run=) except → 記 error、降級
4. status = ok / partial / failed
5. 非 dry_run → ledger/dream.append_run(...)
6. 回 summary
```
- **順序** atomize → janitor;**pass 互不阻斷**(各自 try);**dry_run 不寫 dream.jsonl**。

### Idle gating
```
systemd timer (Mon..Fri 05:00) → dream-idle-wrapper.sh → psc memory dream run --require-idle
  └ --require-idle: is_idle() → 非 idle 則 log "skipped: busy" + exit 0(不跑);idle/判不出 → 跑
```
- idle 判斷在 Python(`--require-idle`,**可注入 is_idle 測試**);wrapper 薄殼;orchestrator 本體不自帶 idle。

### B. Bundle 組裝（`bundle build`）
```
1. slices = selector.select(...)（無 facet → 報錯）
2. 建 out_dir/slices/;複製選中 slice → slices/<slice_id>.md
3. 組 ledger.jsonl:每 slice 的 lifecycle(by record_id)+ relations(觸及 slice/session/entity 節點)+ processing(by distilled_from session)
4. 寫 manifest.json(raw_excluded:true)
5. 回 out_dir
```
- **只讀 `knowledge/` + `runtime/ledger/`**;不碰 raw 來源;決定性(slice 依 slice_id 排序)。

---

## 5. 錯誤處理 & Guardrails

| 失敗 | 處置 |
|---|---|
| 某 pass raise | per-pass try 接住,記 errors + status 降級,**另一 pass 照跑**,不 crash |
| LLM/agent_exec 不可用 | T3.2 per-session fail-closed → session 留 split + warning,atomize partial,**隔日重試** |
| `dream.jsonl` append 失敗 | exit≠0 + stderr;pass 產物已記各自 ledger(權威),重跑安全 |
| idle 判不出 | **fail-safe-to-run**(5am 本是 idle 窗) |
| `bundle` 無 facet | 報錯 exit≠0 |
| `bundle` 選 0 slice | 寫空 bundle + manifest(0)+ warn,非錯 |
| 組 bundle 時 ledger 壞行 | ledger reader fail-closed → 傳播,build 失敗 loud |

log → `~/.agents/memory/log/dream.log`,不含 slice 內文/raw。

| # | Guardrail | 保證 |
|---|---|---|
| G1 | replay/bundle 永不讀 raw | 只讀 `knowledge/` + `runtime/ledger/`;test 斷言無 raw |
| G2 | proposal-first、canonical write gated | MVP 只跑已 gate 的 atomize/janitor;新跨 session 變更走 `proposals.py`,無 auto-apply |
| G3 | dream 獨立服務 | 與 ingestion pipeline 分離,timer 觸發 |
| G4 | pass 隔離 | 一 pass 失敗不擋另一、不 crash |
| G5 | idle advisory + fail-safe-to-run | busy 才跳過 |
| G6 | 決定性 / log 無 raw | now 注入 |
| G7 | dry_run 不變更狀態 | 不寫 dream.jsonl |
| G8 | 重用不重寫 | 呼叫既有 pass 入口 |

---

## 6. 測試策略

注入 fake/stub 保確定性;systemd 範本這台 WSL(`systemctl --user` running)可實裝測,CI 不依賴。

### 單元
| 測試檔 | 覆蓋 |
|---|---|
| `test_dream_orchestrator.py` | 注入 fake atomize/janitor runner:順序 atomize→janitor、status(ok/partial/failed)、pass 隔離(一個 raise 另一仍跑)、dry_run 不寫 dream.jsonl |
| `test_dream_idle.py` | `is_idle` 對注入 loadavg 的判斷;判不出 → True(fail-safe) |
| `test_ledger_dream.py` | append/last_run/backlog_depth、flock、壞行 fail-closed、ts 注入 |
| `test_dream_proposals.py` | append/pending/requires_approval(canonical 類 True) |
| `test_replay_selector.py` | facet AND、tags any-match、entity via relations、active-set 預設排除 decayed、`--include-decayed`、無 facet 報錯 |
| `test_replay_bundle.py` | bundle 三件式、ledger 事件齊、**無 raw 內容**、空選取空 bundle、manifest raw_excluded |

### E2E / 整合
| 場景 | 斷言 |
|---|---|
| dream run(identity/fake promoter) | dream.jsonl status=ok、atomize+janitor 都跑、status 反映;再跑冪等(atomize/janitor 各自冪等) |
| `--require-idle` busy | 注入 busy → skipped、exit 0、不寫 dream.jsonl |
| bundle 全流程 | dream 產 knowledge 後 `bundle --project X` → bundle 有 slices+ledger、無 raw、過 manifest 檢查 |
| systemd 範本 | 範本檔存在、含 `OnCalendar=Mon..Fri 05:00`、ExecStart 指 `dream run --require-idle`(解析測試;實裝 opt-in) |
| 整合 | `stage2_integration_check.sh` 加 `dream run --dry-run` + `bundle`(over fixtures) |
| 回歸 | `unittest discover -s paulshaclaw/memory/tests` 與 `tests/` 全綠 |

> systemd 實裝(`loginctl enable-linger` + `systemctl --user enable --now`)為 opt-in 手動驗(文件化);CI 只驗範本內容。

---

## 7. 解鎖的後續（非本 change）
- **B 跨 session 演進脈絡**:dream task,偵測 supersede/演進鏈 → `supersede`/`merge` proposals 走 review gate。
- **C 全域實體圖**:dream task,聚合 `mentions` 邊 + 實體正規化 → entity graph 視圖。
- **Topic 6 wake-up**:消費 dream status + active-set 組 wake-up bundle。
- **Topic 7 retrieval**:lexical+relation 檢索,bundle 之後可加 free-text facet。
