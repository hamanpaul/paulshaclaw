---
dispatch: hold
slice_id: persona-manager-phase-d
plan: null
depends_on: [persona-manager-phase-c]
---

# Persona Manager Phase D — canary（#123）設計

> 日期：2026-06-23 ｜ 狀態：草案（待覆審）｜ 分支：`feature/123-phase-d-canary`
> 上游：umbrella §7 Phase D；Phase C(#122, merged)、完成側 tick(#121, merged)。
> Issue：#123（umbrella #14；依賴 #122/#121/#120）。

## 1. 背景與校正

還沒有任何真實 `dispatch:auto` slice 經 manager 端到端跑過。目標：放一個 **trivial、有界** 的真 slice，用 headless executor 真的跑一輪，觀察 dispatch → headless 啟動 → 完成偵測 → manifest → 釋放 全鏈在 shadow 下走通。

校正（動工前發現的兩個阻擋）：
1. **CLI 無法觸發 headless 自主**：`coordinator tick`/`fanout` 建 `SubprocessLauncher(allow_unsafe=False)` → claude 走 `acceptEdits`、codex 不帶 sandbox/hook-trust bypass。依 launcher smoke 註記，headless agent 無 bypass 會**卡在核可/hook trust 等輸入**而 timeout。故 live 自主 canary 須先能設 `allow_unsafe=True`。
2. **無 model 選擇**：`build_copilot_argv` 無 `--model`，無法「copilot 走 haiku4.5」。

## 2. 目標與非目標

**目標**
- Unit 1：CLI `tick`/`fanout` 加 `--allow-unsafe`（→ launcher allow_unsafe）與 `--model`（per-executor passthrough）。
- Unit 2：trivial 有界 canary slice fixture + 專用 canary specs dir + runbook。
- Unit 3：live 跑一輪，依序 **claude → codex → copilot(`--model` haiku-4.5)**，蒐證 dispatch→complete 全鏈。

**非目標**
- ❌ relay→Telegram 觀測（#120 未做）——本票以**本機 log/JSONL** 觀測。
- ❌ enforce 翻牌(#124)、retry/requeue(#132)、F2 baseline(#131)。
- ❌ 把 canary slice 設成有實質任務——必須 trivial（見 §5 安全）。

## 3. Unit 1 — enabling flags

- `--allow-unsafe`（store_true）：`tick`/`fanout` 建 `SubprocessLauncher(executor=..., allow_unsafe=True)`。預設 False（最小放權）。
- `--model <m>`：傳入 launcher → 各 `build_*_argv` 接受 `model` 參數：
  - copilot：`--model <m>`（本票主要用途：haiku-4.5）。
  - claude：`--model <m>`（未設則不帶）。
  - codex：`--model <m>`（codex exec 接 `--model`/`-m`；未設則不帶）。
- `SubprocessLauncher.__init__` 加 `model: str | None = None`，`launch` 傳給 argv builder。argv builder 簽名加 `model: str | None = None`，僅在非 None 時 append。

## 4. Unit 2 — canary slice + 有界任務

- 專用目錄 `docs/canary/`（或 `runtime/canary/specs/`）放單一 canary spec，frontmatter `dispatch: auto`、`slice_id: canary-pong`、`plan` 指向同檔/小 plan。
- **plan 內容（有界）**：指示 agent 僅「在其 worktree 內建立 `canary/PONG.md`，內容一行 `pong canary-pong`，不動任何其他檔、完成即停」。
- canary specs dir 與真實 specs 隔離，timer/真實 fanout 不會掃到它。

## 5. 安全（live 自主 agent 的護欄）

- **有界任務**：因 `--allow-unsafe` 旁路沙箱/核可，canary 任務 MUST trivial（建一個小檔），prompt 明確「不動其他檔」。
- **worktree 隔離**：agent 跑在 `feature/canary-pong` worktree（`ScriptWorktreeCreator` 建），不碰主工作樹/主分支。
- **可觀測 + 可中止**：watch log/JSONL + sentinel；記錄 pid，必要時 `kill`；跑完移除 worktree。
- **逐家依序、非並行**：claude→codex→copilot 一次一個，各自獨立 slice_id（避免 worktree/job 撞號）。
- **成本意識**：claude/codex 用預設 model；copilot 用 haiku-4.5（便宜）作測試。

## 6. Unit 3 — live run 程序

對每個 executor（claude→codex→copilot）：
1. 確認 CLI 可用（`command -v`）。
2. `python -m paulshaclaw.coordinator tick --specs-dir <canary> --executor <e> --allow-unsafe [--model haiku-4.5(copilot)]`（不帶 `--require-idle`，受控同步觀察）。
3. 觀察：worktree 建立 → headless 啟動（pid/log）→ `poll_headless_done` 讀 sentinel/JSONL → `classify_completion` → `complete_tick` 寫 `runtime/handoff/canary-<e>.json` → （無下游則）釋放 N/A。
4. 蒐證：貼出 manifest + 末筆 JSONL + exit code；記錄成功/失敗與耗時。
5. 清理：移除該輪 worktree、canary 產物（或保留於 record）。

## 7. 驗收（Phase D，shadow）

- 至少 claude 一輪端到端走通（dispatch→headless→done→manifest `gate_status=passed`）。
- codex、copilot(haiku4.5) 各記錄結果（通過或具體失敗原因，作 executor 相容性實證）。
- 全程 bot/主工作樹無感（worktree 隔離、shadow）。
- 產出：canary 執行 record（docs 或 PR body）；不真動 main。

## 8. 測試與影響

| 檔案 | 動作 |
|---|---|
| `paulshaclaw/coordinator/launcher.py` | Modify（argv builders + SubprocessLauncher 加 `model`） |
| `paulshaclaw/coordinator/cli.py` | Modify（`tick`/`fanout` 加 `--allow-unsafe`/`--model`） |
| `tests/test_coordinator_launcher.py` | Modify（model passthrough / allow_unsafe argv 斷言） |
| `tests/test_coordinator_cli_*.py` | Modify（flag → launcher 接線，注入 fake launcher 驗證） |
| `docs/canary/...` + runbook | Create（canary slice + 程序） |

Unit 1 走 TDD（hermetic，注入 fake launcher，不啟真 agent）；Unit 3 為 live 動作（蒐證，非單元測試）。
