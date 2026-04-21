## Context

`docs/superpowers/workstreams/stage4-persona-contract/{plan,task,todo}.md` 已定義 Stage4 目標：建立 persona contract、handoff schema、filesystem/tool guardrail 與 shadow-run 驗證。現況是 `openspec/specs/stage4/README.md` 只有 placeholder，尚未提供 Requirement/Scenario 可驗收條款；因此 Stage4 無法用 OpenSpec 流程形成可驗證交付。

同時，`todo.md` 明確指出 blocker：Stage3 必須提供穩定 phase 名稱與 gate 輸出格式。故本設計將 Stage4 對 Stage3 的依賴限定為 consume-only：只讀既有 canonical contract，不反向修改 Stage3 lifecycle/runtime。

## Goals / Non-Goals

**Goals:**
- 建立 `stage4-persona-contract` change 的 proposal/design/spec/tasks 四件套。
- 以最小增量補齊 Stage4 canonical spec 的 Requirement/Scenario。
- 定義三角色最小 contract（manager/builder/reviewer）與 `allowed_phases` 對應。
- 定義 handoff message schema 與 coordinator route 的最小相容欄位。
- 定義 filesystem/tool guardrail 最小規則與拒絕條件。
- 明確 Stage4 consume Stage3 phase/gate 的依賴邊界。

**Non-Goals:**
- 不在本 change 實作 `paulshaclaw/persona/` runtime 程式碼。
- 不修改 Stage3 canonical spec 與 Stage3 runtime 行為。
- 不擴充 Stage6 approval/redaction 安全治理。
- 不在本 change 內凍結 Stage5 觀測事件格式。

## Decisions

### Decision 1：沿用 `stage4` capability，補 Requirement/Scenario 而非新增能力名稱

- **選擇**：在 change delta 與 canonical spec 使用 `stage4` 路徑（`specs/stage4/spec.md`）。
- **替代方案**：新增 `stage4-persona-contract` capability。
- **理由**：Repo 已存在 `openspec/specs/stage4/`，本次是補強既有 Stage4 契約，不是分裂新 domain。

### Decision 2：persona contract 先收斂三角色最小集合

- **選擇**：MVP 只定義 `manager`、`builder`、`reviewer`。
- **替代方案**：一次納入更多角色（如 release-manager、auditor）。
- **理由**：與 workstream `plan/task/todo` 一致，可降低 schema 複雜度並先建立驗證基線。

### Decision 3：`allowed_phases` 僅 consume Stage3 正規 phase vocabulary

- **選擇**：Stage4 角色 phase 限制只引用 Stage3 既有 `/research → /ship` 集合與 gate 結果，不擴充或改名 phase。
- **替代方案**：Stage4 自行新增 phase alias 或覆寫 gate 狀態語義。
- **理由**：避免跨 stage 反向耦合，符合「Stage4 consume Stage3」邊界。

### Decision 4：handoff schema 採最小必填欄位，供 coordinator route 消費

- **選擇**：handoff 至少包含 `from_role`、`to_role`、`slice_id`、`phase`、`gate_status`、`artifact_refs`、`summary`、`created_at`。
- **替代方案**：直接綁定 coordinator 內部資料結構。
- **理由**：保持協定穩定、與 runtime 解耦，降低後續欄位演進成本。

### Decision 5：guardrail 採 fail-closed 最小策略（tool + filesystem）

- **選擇**：角色超出 `allowed_tools` 或 `allowed_paths` 必須拒絕並產生可審計理由。
- **替代方案**：先記錄告警，不阻擋執行。
- **理由**：Stage4 是 contract/gate 層，若不 fail-closed，驗收條款無法成立。

## Risks / Trade-offs

- [風險] Stage3 canonical phase 名稱或 gate report 欄位若後續調整，Stage4 條款可能漂移。  
  [緩解] 在 tasks 納入 cross-check 命令，固定比對 Stage3 spec 的 phase/gate 關鍵字。

- [風險] 目前 Stage4 runtime 尚未實作，部分條款僅能先由文件與 schema 驗證。  
  [緩解] 任務中區分「OpenSpec 驗證」與「行為驗證」證據路徑，避免混淆完成定義。

- [風險] guardrail 規則過嚴可能影響開發流暢度。  
  [緩解] 先以最小角色/最小工具集落地，後續再透過增量 change 擴充。

## Migration Plan

- 本 change 為 spec/doc 增量，不涉及資料 migration。
- 實作階段依序落地：persona schema → handoff schema → guardrail → shadow-run。
- 若 Stage3 契約變更，先提 Stage3 change 更新 canonical spec，再由 Stage4 follow-up consume 新版本；Stage4 不直接反向修改 Stage3。

## Open Questions

- user overlay 載入點是否固定於 `personas.yaml` 同目錄或由 config 指定？
- shadow-run 證據格式是否要求統一為 JSONL，或可接受文字報告 + command output？
- Stage5 讀取 persona 事件的最小欄位集合是否需在 Stage4 先凍結？
