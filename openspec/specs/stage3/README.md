# Stage 3 Canonical Contract — Lifecycle (artifact + phase gate)

> **版本**：v0.1 (凍結於 main branch，基於 Stage 1/2 worktree 現有實作證據)
> **定位**：本文為 Stage 3/4/5/6/7 共用的**最小共享契約**，凍結跨 stage 使用的介面、schema 及事件種類。
> 不包含 Stage 3 runtime 實作細節（由 `wt/stage3-lifecycle-mvp` 負責）。

---

## 0. 本文件範圍與不範圍

| 範圍（本文凍結） | 不在範圍（各 stage worktree 自理） |
|---|---|
| 七個正規 phase 名稱 | Stage 3 gate engine 實作 |
| Stage 1 daemon 最小介面（命令 + JSON 回傳欄位） | Stage 4 persona contract 細節 |
| Stage 2 memory 最小介面（路由、事件種類） | Stage 5 failover/recovery 邏輯 |
| artifact frontmatter 必填欄位 | Stage 6 approval gate 具體規則 |
| `lifecycle.yaml` 最小 shape | Stage 7 deploy 腳本 |
| gate report shape 及事件種類 | 任何 worktree 的 Python/YAML 程式檔 |
| 凍結後仍被阻塞的工作清單 | — |

---

## 1. 正規 Phase 名稱（所有 stage 通用）

```
/research → /define → /plan → /build → /verify → /review → /ship
```

| Phase | 中文標籤 | 主要產出 artifact |
|---|---|---|
| `research` | 研究 | `docs/research/<slug>.md` |
| `define` | 定義 | `docs/spec.md` |
| `plan` | 規劃 | `docs/roadmap.md` + `test.md` + `task.md` + `todo.md` + `plan.md` |
| `build` | 實作 | branch diff + `reports/build/<task-id>.md` |
| `verify` | 驗證 | `reports/verify/<run-id>/` bundle |
| `review` | 審查 | `reports/review/<run-id>.md` |
| `ship` | 交付 | `reports/ship/<version>.md` + commit + tag |

特殊 lifecycle（`hotfix`、`spike`、`doc-only`）在 Stage 3 worktree 定義；本文不展開。

---

## 2. Stage 1 最小 daemon 介面

> 證據來源：`wt/stage1-core-daemon-tui-bot` worktree 的
> `paulshaclaw/core/daemon.py`、`paulshaclaw/core/config.py`、
> `config/paulshaclaw-stage1.sample.json`、`tests/test_stage1_smoke.py`

### 2.1 支援命令

| 命令 | 語意 |
|---|---|
| `/status` | 回傳 daemon 現況 JSON |
| `/dispatch <task-id>` | 建立 coordinator job，回傳 job JSON |

Stage 3 lifecycle runtime 只消費這兩個端點，**不得**修改 daemon 啟動流程或新增其他命令（由 Stage 3 worktree 另行提案）。

### 2.2 `/status` 回傳 JSON 欄位（最小集合）

```jsonc
{
  "ok": true,
  "daemon": "<daemon_name>",      // 來自 config.daemon_name
  "project": "<default_project>", // 來自 config.default_project
  "pane_count": 0,                // pane_assignments 陣列長度
  "allowed_user_count": 0         // allowed_user_ids 陣列長度
}
```

### 2.3 `/dispatch <task-id>` 回傳 JSON 欄位（最小集合）

```jsonc
{
  "ok": true,
  "job_id": "<uuid>",
  "phase": "<phase>",   // 來自 config.coordinator.phase
  "scope": "<scope>"    // 來自 `/dispatch <task-id>` 的 task_id
}
```

### 2.4 Config 接縫（config seam）

- 載入優先順序：`--config <path>` flag → 環境變數 `PSC_STAGE1_CONFIG`；兩者皆未提供時拋出錯誤（無內建預設）。
- 必要欄位：`daemon_name`、`default_project`、`coordinator.phase`、`pane_assignments[]`（每項含 `pane_id / title / task_id / status`）。
- 選填欄位：`allowed_user_ids`（預設空陣列）、`coordinator.default_payload`（預設空物件）。
- Stage 3 lifecycle runtime 以相同 config 路徑讀取；不引入獨立 config 檔，除非另開 Stage 3 worktree proposal。

### 2.5 Coordinator 接縫（coordinator seam）

coordinator 為 protocol 介面，最小簽章：

```python
create_job(*, phase: str, scope: str, payload: dict) -> dict
# 回傳至少包含: job_id, phase, scope, payload
```

Stage 3 的 lifecycle runtime 呼叫此介面後，收齊 artifact 再跑 gate check；不直接執行 phase 邏輯。Stage 1 現有實作中的 `phase` 來源仍以 `config.coordinator.phase` 為準。

---

## 3. Stage 2 最小 memory 介面

> 證據來源：`wt/stage2-paulsha-memory` worktree 的
> `openspec/specs/stage2/scope.md`、`paulshaclaw/memory/routing.md`、
> `paulshaclaw/janitor/service.md`

### 3.1 Canonical 路由路徑

```
inbox → work-centric → knowledge
```

| 層 | 路徑（相對於 `~/.agents/memory/`） | 已文件化角色 |
|---|---|---|
| inbox | `inbox/sessions/`、`inbox/plans/`、`inbox/research/`、`inbox/reports/` | importer intake bucket（上游先放入對應 bucket） |
| work-centric | `work-centric/<project>/plan/`、`work-centric/<project>/experience/` | classifier |
| knowledge | `knowledge/concepts/`、`knowledge/methods/`、`knowledge/incidents/`、`knowledge/entities/` | classifier 升級；janitor 只做治理/降權/重新啟用 |

> 註：`runtime/lifecycle/` 為 **Stage 3 runtime storage**（events、gates、partial），屬本文後續 Stage 3 契約使用路徑，**不是**上述 Stage 2 `inbox → work-centric → knowledge` 證據鏈的一部分。

### 3.2 Importer / Classifier / Replay（第一等角色）

- **Importer**：接收已放入 `inbox/` bucket 的 artifact（至少涵蓋 session distilled output、plan/task/todo artifact、research、report）；不修改 raw artifact。
- **Classifier**：依文件化 routing table 路由：session distilled output 由 `inbox/sessions/` 升級到 `work-centric/<project>/experience/`；plan/task/todo artifact 由 `inbox/plans/` 升級到 `work-centric/<project>/plan/`；research/report 先留在 `inbox/research/` 或 `inbox/reports/`，僅在「可重用且具引用」時升級到 `knowledge/concepts/` 或 `knowledge/methods/`；已驗證事件摘要由 `inbox/reports/` 升級到 `knowledge/incidents/` 或 `knowledge/entities/`。本文**不額外宣稱**其他 `knowledge/*` writer 或未文件化的 artifact-kind 映射。
- **Replay**：從 `work-centric/` + ledger 組合 replay bundle；不直接掃描 raw prompt。Stage 3 lifecycle runtime 可用 replay bundle 重建 slice 狀態。

### 3.3 Decayed / Reactivation（第一等事件）

- `decayed`：由 classifier 或 janitor 偵測需降權時觸發；需記錄 trigger source，並把條目移出高信任檢索集合。
- `reactivation`：從 decayed 狀態恢復時觸發；需記錄 replay context 及 record-agent-reference。
- Stage 3 的 `rewind` 操作把下游 artifact 標 `stale`，由 Stage 2 janitor 處理後續 decayed 事件；**Stage 3 runtime 不直接操作 Stage 2 janitor**。

### 3.4 Janitor 邊界

- Janitor 為獨立服務，掃描 `inbox/`、`work-centric/`、ledger。
- Janitor **不得**修改 raw artifact，**不得**定義 Stage 3 frontmatter schema。
- Stage 3 lifecycle runtime 與 janitor 之間僅透過 event 溝通（見 §5）。

---

## 4. Artifact Frontmatter 必填欄位

所有 lifecycle-managed artifact（phase artifact + gate report）必須包含以下 YAML frontmatter：

```yaml
---
phase: research|define|plan|build|verify|review|ship
project: <project-slug>
slice_id: <uuid>
artifact_kind: research|spec|roadmap|test|task|todo|plan|report|review|ship-record|gate-report
version: <semver-ish>
supersedes: <prev-artifact-path>   # rework 時填；初版可省略
created_at: <ISO8601>
created_by: <persona-id>
source_session: <session-id>
gate_required: true|false
checksum: <sha256 of body>
---
```

**各欄位規則：**

| 欄位 | 必填 | 規則 |
|---|---|---|
| `phase` | ✓ | 七個正規 phase 之一 |
| `project` | ✓ | 對應 `lifecycle.yaml` 的 `project` 欄位 |
| `slice_id` | ✓ | 相同 slice 下所有 artifact 共用同一 UUID |
| `artifact_kind` | ✓ | 使用上列枚舉值 |
| `version` | ✓ | `v<N>` 或 semver；同一 slice 同一 kind 每次 rework 遞增 |
| `supersedes` | 否 | 若為 rework 版本，指向被取代 artifact 路徑 |
| `created_at` | ✓ | ISO 8601 UTC |
| `created_by` | ✓ | persona-id 或 `operator` |
| `source_session` | ✓ | session id（可為 `manual` 如為人工補填） |
| `gate_required` | ✓ | 明確標示此 artifact 是否需要通過 gate |
| `checksum` | ✓ | body（frontmatter 以下部分）的 SHA-256 hex |

---

## 5. `lifecycle.yaml` 最小 Shape

路徑：`~/.agents/memory/work-centric/<project>/lifecycle.yaml`（runtime，不進 git）

```yaml
project: <project-slug>
current_slice: <uuid>
current_phase: research|define|plan|build|verify|review|ship|blocked:<phase>
workflow_version: <semver>   # lifecycle runtime 版本
last_ship: <semver-tag>|null
open_rework: []              # list[str]，待 rework 的 artifact path
open_rewind: []              # list of {target_phase, reason, initiated_at}
stale_spikes: []             # list of spike slugs past expiry
gates:
  <phase>:
    last_check: <ISO8601>|null
    status: passed|failed|running|skipped|null
```

**使用規則：**

- 此檔為 lifecycle runtime 的主 state；所有 slash command 必須從此讀取 context，禁止從 agent memory 推斷。
- `current_phase` 為 `blocked:<phase>` 表示 gate 失敗或升級處理中且尚未 rewind / resolve。
- 不在此檔定義 persona 分配或 resource limits（由 Stage 4 `personas.yaml` 負責）。

---

## 6. Gate Report Shape

路徑：`runtime/lifecycle/gates/<slice_id>/<phase>/<timestamp>.md`（runtime，不進 git）

```yaml
---
artifact_kind: gate-report
phase: <phase>
slice_id: <uuid>
gate_type: entry|exit
result: passed|failed|override
checked_at: <ISO8601>
checked_by: <persona-id>|static-checker
overridden_by: <persona-id>|null
override_reason: <string>|null
---
```

**Body 必填 sections：**

1. `## Static Check` — frontmatter 欄位齊全性、checksum、schema 驗證結果
2. `## Health Check` — session-health score（適用時）；可為 `N/A`
3. `## Route Check` — problemmap 結果（適用時）；可為 `N/A`
4. `## Verdict` — `passed | failed | override`，含失敗原因或 override 理由

---

## 7. 事件種類（Event Kinds）

路徑：`~/.agents/memory/runtime/lifecycle/events.jsonl`（append-only）

`events.jsonl` 的權威寫入者為 Stage 3 lifecycle runtime；其他元件若需反映狀態，應透過 Stage 3 的 dispatch / gate 流程回拋事件，不直接多點 append。

每行為一個 JSON 物件：

```jsonc
{
  "kind": "<event-kind>",
  "slice_id": "<uuid>",
  "phase": "<phase>",
  "project": "<project-slug>",
  "actor": "<persona-id>|operator|system",
  "artifact_ref": "<path>|null",
  "ts": "<ISO8601>",
  "meta": {}   // kind-specific 額外欄位
}
```

### 7.1 核心事件種類表

| Kind | 觸發時機 | 主要消費方 / 後效 |
|---|---|---|
| `phase.requested` | slash command 派工前 | Stage 4 persona loader 決定允許哪個 persona 接工 |
| `phase.artifact_submitted` | artifact 寫入 inbox | Stage 2 importer 消費；Stage 4/5/6 不直接訂閱此事件 |
| `phase.gate_passed` | gate 三線通過 | Stage 5 health dashboard；lifecycle state 更新 |
| `phase.gate_failed` | gate 任一線未過 | Stage 5 alert；lifecycle state → `blocked:<phase>` |
| `gate.override` | `/gate override` 執行 | Stage 5 dashboard 需標示 override；Stage 6 audit trail；下次 `/ship` 附入 release note |
| `slice.rewound` | `/rewind <phase>` 執行 | Stage 2 classifier 把下游 artifact 標 `stale` |
| `slice.closed` | `/ship` 成功 | Stage 2 importer 把整 slice artifacts 歸檔 |
| `artifact.stale` | rewind 後下游 artifact | Stage 2 janitor 觸發 decayed 流程 |
| `artifact.rework` | reviewer/tester 要求修改 | artifact version++ |
| `phase.escalated` | persona 遇到超範圍阻塞 | Stage 5 通知；lifecycle 暫停 |

`gate.override` 為獨立終態事件，**不會**同時補發 `phase.gate_passed`；Stage 5 若要呈現 override 通關，必須同時監聽 `phase.gate_failed` 與 `gate.override`。

### 7.2 Stage 6 所需附加欄位

Stage 6 audit gate 消費 `gate.override` 及 `slice.closed` 事件時，期望 `meta` 包含：

```jsonc
{
  "actor": "<string>",
  "action": "<gate.override|slice.closed>",
  "target": "<artifact_ref>",
  "approved": true|false,
  "occurred_at": "<ISO8601>"
}
```

其中 `gate.override` 事件的 `approved` 固定為 `true`；`false` 僅保留給其他 approval/audit 類事件使用。

完整 audit entry 結構（含 `previous_hash` / `entry_hash`）由 Stage 6 worktree 定義；Stage 3 只需保證事件欄位齊全。

---

## 8. 凍結後仍被阻塞的工作

以下工作依賴本合約，但尚未解除阻塞：

| 工作 | 阻塞原因 | 解除條件 |
|---|---|---|
| Stage 3 gate engine 實作 | 需 Stage 1 `coordinator.create_job` 可呼叫 | Stage 1 worktree merge 至 main 並通過 smoke test |
| Stage 3 slash command 路由 | 需 Stage 1 PaulShiaBro daemon 可啟動 | 同上 |
| Stage 3 importer 通知 | 需 Stage 2 importer 運行 | Stage 2 worktree merge 至 main |
| Stage 4 persona loader | 需本文 §7 `phase.requested` 事件流 | Stage 3 events.jsonl 落地 |
| Stage 5 gate 監控 | 需本文 §6 gate report + §7 事件流 | Stage 3 gate engine 落地 |
| Stage 6 audit trail | 需本文 §7.2 `gate.override` meta 欄位 | Stage 3 events.jsonl 落地 |
| Stage 7 `psc install` lifecycle template | 需 `lifecycle.yaml` template 路徑確定 | 本文 §5 已確定；Stage 7 worktree 可啟動 |

---

## 9. 此合約的變更規則

1. 修改本文需在 `main` branch 建立 openspec change proposal（`openspec/changes/stage3-contract-*.md`）。
2. 任何欄位的**刪除或重命名**需經 Stage 4/5/6 worktree 確認不破壞消費方。
3. 新增欄位以 `optional` 為預設；升級為必填需 bump `workflow_version`。
4. Stage 3 worktree 的 runtime 實作細節不得覆蓋本文契約定義。
