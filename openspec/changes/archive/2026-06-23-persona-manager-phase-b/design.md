## Context

完整設計見 `docs/superpowers/specs/2026-06-22-persona-manager-phase-b-headless-dispatch-design.md`。現狀：Phase A 的 `build_dispatch_command` 產 shlex shell 字串（為 pane send 設想）；`dispatch_ready` 以 `%{i}` 佔位 pane；`JobRegistry` 不記 executor/session/pid。

## Goals / Non-Goals

**Goals:**
- `AgentLauncher` seam + copilot/claude/codex 三 headless 真實作。
- `build_dispatch_prompt`（executor-agnostic 純文字 prompt）。
- registry 記 executor/session_name/pid/log_path/exit_code；完成偵測 = exit + 末筆 JSONL。
- 共用 relay hook（三家共有 `session_start`/`stop`）→ bro-bridge → PaulShiaBro。
- `dispatch_ready` 接 headless 啟動。

**Non-Goals:**
- 路徑 1（bot→pane）、PaneAllocator、systemd（Phase C）、② gate、per-tool 細粒度 relay。

## Decisions

- **headless subprocess argv（非 tmux）**：prompt 為單一 argv 元素，無 shell/send-keys → 多行問題消滅。
- **AgentLauncher pluggable seam**：三 executor 各自組 argv（per-executor 旗標表見 spec §3）；測試注入 fake，不啟真 subprocess。
- **完成偵測 = exit code + 末筆 JSONL result**，JSONL 不可解時 fallback exit code（取代 branch-commit/sentinel）。
- **relay 鎖三家共有事件** `session_start`+`stop`；env `PSC_SLICE_ID` 標記 task；一支 hook script 三家註冊；復用 bro-bridge。`postToolUse` 非共有 → 不進核心。
- **`build_dispatch_command`→`build_dispatch_prompt`**：移除 shell 包裝（Phase A 遞延的 transport），保留契約 render + plan ref。

## Risks / Trade-offs

- [copilot/codex hook 在 headless 是否 fire 未證實] → smoke test 核定；不 fire 者該家退 JSONL 監控由 manager 代 relay。
- [executor 旗標差異（claude autonomous mode、codex `--remote ADDR`、copilot session id 反查）] → 各 smoke test 核定；seam 隔離差異。
- [codex hook trust] → relay hook 需先信任或 `--dangerously-bypass-hook-trust`（自動化）。
- [argv 超長 prompt（ARG_MAX）] → plan 以路徑參照、不 inline 全文；超限改 stdin（codex 支援）。
- [relay 失敗影響派工] → relay 與 dispatch 解耦、fire-and-forget，失敗僅丟通知。
- [Phase B 重構 Phase A 的 build_dispatch_command] → 疊在未 merge 的 phase-a 上；depends_on 已標。
