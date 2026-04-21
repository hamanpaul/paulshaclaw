## Context

Stage 3 workstream 已有明確工作拆解：
- `docs/superpowers/workstreams/stage3-lifecycle-mvp/plan.md`：Phase 1~3（schema、gate、回歸驗證）
- `docs/superpowers/workstreams/stage3-lifecycle-mvp/task.md`：frontmatter / lifecycle template / static gate / events / golden slice
- `docs/superpowers/workstreams/stage3-lifecycle-mvp/todo.md`：要求先開 OpenSpec change，並確認 Stage 1/2 最小介面

研究文件 `docs/research/03.stage3-lifecycle-slash-commands-artifacts-phase-gating-research.md` 進一步收斂為 artifact-first、event-first，並指出 Stage 3 的 MVP 優先順序是：
1. frontmatter schema 與 `lifecycle.yaml` template；
2. static gate 與最小事件流；
3. golden slice 回歸。

目前 canonical `openspec/specs/stage3/README.md` 已有跨 stage 契約，但缺少可直接驗收的 Requirement/Scenario 條款，導致 Stage 3 實作與驗收命令無法在 spec 層落地。

## Goals / Non-Goals

**Goals:**
- 產出 apply-ready 的 Stage 3 OpenSpec 文件骨架（proposal/design/specs/tasks）。
- 以最小增量補齊 Stage 3 可驗收條款，覆蓋 schema/template/gate/events/golden slice。
- 明確 Stage 3 與 Stage 1 / Stage 2 的介面邊界，避免 runtime 職責混淆。
- 每個 tasks 條目都綁定驗證命令與 evidence 路徑。

**Non-Goals:**
- 不在本 change 內實作 Stage 3 runtime 程式碼。
- 不修改 Stage 1 與 Stage 2 canonical spec 內容。
- 不展開 Stage 4 persona contract、Stage 6 approval engine、Stage 7 deploy 細節。

## Decisions

### Decision 1：以 `stage3` 現有 capability 做「Modified」而非新增 capability

- **選擇**：在 change delta 新增 `specs/stage3/spec.md`，補上 Stage 3 MVP requirement。
- **替代方案**：新增 `stage3-lifecycle-mvp` capability。
- **理由**：repository 已存在 `openspec/specs/stage3/`，且本次是補強既有 Stage 3 契約，不是切出獨立 domain。

### Decision 2：MVP 驗收聚焦四個可測核心

- **選擇**：只納入 (a) frontmatter schema + lifecycle template、(b) static gate、(c) 最小事件流、(d) golden slice。
- **替代方案**：一次納入 hotfix/spike/doc-only/approval gate 全部細節。
- **理由**：與 workstream `plan/task/todo` 完全一致，保持最小可驗證交付。

### Decision 3：Stage 1 邊界固定為 daemon/coordinator seam

- **選擇**：Stage 3 只消費 Stage 1 `/status`、`/dispatch` 與 `create_job(*, phase, scope, payload)`。
- **替代方案**：在 Stage 3 直接擴寫 daemon 命令面或啟動流程。
- **理由**：符合 `openspec/specs/stage1-core-runtime/spec.md` 與 `openspec/specs/stage3/README.md` 的既有契約，避免跨 stage 反向耦合。

### Decision 4：Stage 2 邊界固定為 memory 路由與事件交握

- **選擇**：Stage 3 僅寫入 phase artifact pointer/copy 到 `inbox/*` 與 runtime `events.jsonl` / gate report；不直接寫 `knowledge/*`、不直接驅動 janitor。
- **替代方案**：Stage 3 直接升級資料到 `knowledge/*` 或直接控制 janitor decayed/reactivation。
- **理由**：符合 `openspec/specs/stage2-memory-governance/spec.md` 的 importer/classifier/janitor 邊界，維持責任分離。

## Risks / Trade-offs

- [風險] 目前 Stage 3 runtime 實作尚未完全落地，spec 條款可能先於程式。  
  [緩解] 任務條目綁定 `unittest` 與 `openspec validate` 命令，讓落地後可立即驗證。

- [風險] `README.md`（契約描述）與新增 `spec.md`（驗收條款）可能產生漂移。  
  [緩解] 在 `spec.md` 只放 MVP 可驗收條款；README 繼續承載跨 stage 背景與凍結規則。

- [風險] evidence 目錄目前尚未在 workstream 建立。  
  [緩解] `tasks.md` 先固定 evidence 路徑命名，後續實作階段按路徑輸出。

## Migration Plan

- 本 change 屬文件契約補強，無 runtime migration 步驟。
- 若後續 Stage 3 runtime 與本文件不一致，優先以 `openspec/changes/stage3-lifecycle-mvp/specs/stage3/spec.md` 做增量修正，再同步 canonical `openspec/specs/stage3/spec.md`。

## Open Questions

- Stage 3 phase artifact 對應 Stage 2 `inbox/*` bucket 的最終映射（例如 `inbox/plans/` vs `inbox/reports/`）是否需在 Stage 3 runtime 啟動前先凍結？
- golden slice 證據是否統一要求 `events.jsonl` 與 gate report 同時落地，或允許先以 test output 作 MVP 證據？
