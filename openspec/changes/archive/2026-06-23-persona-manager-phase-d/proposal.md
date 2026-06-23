## Why

「persona 通電」epic（#14）至今無任何真實 `dispatch:auto` slice 經 manager 端到端跑過。Phase D(#123) 要放一個 trivial 有界的真 slice、用 headless executor 真跑一輪，觀察 dispatch→headless→完成偵測→manifest→釋放 全鏈在 shadow 下走通。動工前發現兩個阻擋：CLI 無法觸發 headless 自主（`allow_unsafe`，否則 agent 卡核可/hook-trust），且無 model 選擇（無法 copilot→haiku4.5）。本票先補這兩個 enabling flag，再 live 跑 canary。

## What Changes

- `coordinator` CLI `tick`/`fanout` 新增 `--allow-unsafe`（→ `SubprocessLauncher(allow_unsafe=True)`，headless 自主必需）與 `--model <m>`（per-executor passthrough）。
- `SubprocessLauncher.__init__` 加 `model: str | None = None`，`launch` 傳給 argv builder；`build_copilot_argv`/`build_claude_argv`/`build_codex_argv` 加 `model` 參數（非 None 才 append `--model`）。
- 新增 trivial 有界 canary slice fixture（`dispatch:auto`，任務僅「建一個小檔即停」）於專用 canary specs dir + runbook。
- live 跑：依序 **claude → codex → copilot(`--model` haiku-4.5)** 各一輪，蒐證全鏈（本機 log/JSONL 觀測；relay→Telegram 留 #120）。

## Capabilities

### Modified Capabilities

- `coordinator-cli`: `tick`/`fanout` 加 `--allow-unsafe` 與 `--model`，接線到注入/建立的 `SubprocessLauncher`。
- `coordinator-headless-dispatch`: `SubprocessLauncher` 與三家 argv builder 支援 `model` passthrough；`allow_unsafe` 經 CLI 可達（headless 自主完成不掛）。

## Impact

- 代碼：修改 `paulshaclaw/coordinator/{launcher.py,cli.py}`；新增 canary slice fixture + runbook；修改對應 tests。
- 設計依據：`docs/superpowers/specs/2026-06-23-persona-manager-phase-d-canary-design.md`。
- 安全：`--allow-unsafe` 旁路沙箱/核可——canary 任務 MUST trivial 有界，agent 跑在 `feature/<slice>` worktree 隔離，可觀測可中止；逐家依序非並行。
- live 動作為 Phase D 驗收（蒐證），非單元測試；Unit 1 flag 走 hermetic TDD（注入 fake launcher，不啟真 agent）。
- relay→Telegram 觀測留 #120；不動 `route_to_agent`。
