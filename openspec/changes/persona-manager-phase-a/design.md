## Context

完整架構設計見 `docs/superpowers/specs/2026-06-22-persona-manager-daemon-design.md`（manager daemon 整體）。本 change 只實作其 §7 Phase A：補上 coordinator→persona 的契約拼裝（Gap A）。現狀：`coordinator.autonomy.dispatch_ready` 送出佔位 `command`、persona 模組在 production 0 命中；`personas.yaml` 缺設計 §4 的全域 `enforcement` 旗標。

## Goals / Non-Goals

**Goals:**
- 新增 `build_dispatch_command` 純函式，把 persona 契約 render 進派工指令（強制點 ①）。
- `dispatch_ready` 改用之，fan-out 產出真 copilot 指令。
- `personas.yaml` 顯式化全域 `enforcement: shadow`，提供 `load_enforcement` reader。
- 零行為改變、零 live 接觸（不碰 daemon／systemd／tmux／真 copilot）。

**Non-Goals:**
- pane 配置（`PaneAllocator`）、manager tick poll 段、systemd unit、canary —— 屬 Phase B/C/D。
- handoff manifest 驗證 —— 屬 ② gate（Phase C），fan-out 派工當下尚無 manifest。
- 翻 `enforce` 或設 required check。

## Decisions

- **`build_dispatch_command` 為純字串函式、零 I/O**（只嵌 `plan_path` 參照，copilot 於 worktree 內自讀計畫）。
  - 理由：避免讀檔 → 不破壞既有 fanout 測試（plan 路徑多為不存在的 fixture）；plan 可能很大，pointer 優於 inline；保持可 TDD 的純度。
  - 替代方案：讀 plan 內容嵌入 prompt → 否決（I/O、測試耦合、體積）。
- **reuse `render.render_contract_prompt`，不自寫 render 邏輯**。未知 role 由其冒泡 `ValueError`，fail-closed。
- **`dispatch_ready` 直接 import `build_dispatch_command`，不另設注入 seam**（YAGNI）。
  - 理由：`render_contract_prompt` 輸出確定性，測試可直接斷言指令內容，無須注入 fake builder。
- **`load_enforcement` fail-safe 退 `shadow`**（缺檔／壞 YAML／非法值），永不誤翻 `enforce`。`load_catalog` 維持只讀 `roles`，與新 key 正交。

## Risks / Trade-offs

- [既有 fanout 測試可能依賴 `command` 內容] → 已查證：phase4 測試僅斷言 `task`/`persona`，不碰 `command`，故安全。本 change 另加一條斷言契約指令的測試。
- [`enforcement` 旗標目前無人消費，可能被誤認為 dead code] → 設計 §4 明列為全域旗標，Phase C gate 會消費；本 change 顯式註明「僅顯式化、零行為改變」。
- [import 循環風險：coordinator→persona] → 已查證 persona 不 import coordinator（persona 僅依賴 lifecycle），無循環。
