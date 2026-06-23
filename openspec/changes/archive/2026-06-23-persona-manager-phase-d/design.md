## Context

Phase C(#122) 讓 manager 走 systemd timer 跑 `coordinator tick`，但 CLI 建 `SubprocessLauncher(allow_unsafe=False)` 且無 model 選擇，故 headless agent 會卡核可/設不了 haiku4.5。完整脈絡見 `docs/superpowers/specs/2026-06-23-persona-manager-phase-d-canary-design.md`。

## Goals / Non-Goals

**Goals:** CLI `--allow-unsafe`/`--model`；trivial 有界 canary slice；依序 claude→codex→copilot(haiku4.5) live 跑一輪蒐證。

**Non-Goals:** relay→Telegram 觀測(#120)；enforce(#124)；canary 任務有實質內容（必須 trivial）。

## Decisions

- **`--allow-unsafe` 預設 False、明確 opt-in**：沿用 launcher 既有 `allow_unsafe` 語意（claude bypassPermissions / codex bypass sandbox+hook-trust / copilot --allow-all）。headless 自主完成必需，但風險高 → canary 任務有界 + worktree 隔離緩解。
- **`--model` per-executor passthrough**：argv builder 僅在 model 非 None 時 append `--model <m>`；claude/codex 未設則用各自預設、copilot 用 haiku-4.5。
- **canary slice 隔離**：放專用 canary specs dir（committed fixture，可重現），與真實 specs 分離，timer/真實 fanout 不掃。
- **逐家依序非並行**：各 executor 用獨立 slice_id，避免 worktree/job 撞號。

## Risks / Trade-offs

- [allow_unsafe 旁路沙箱，agent 可任意動 worktree] → canary 任務 trivial 有界（建一小檔即停）+ `feature/<slice>` worktree 隔離 + 可觀測可中止。
- [headless agent 行為/旗標各家差異] → 逐家蒐證，失敗記具體原因作相容性實證，不阻其他家。
- [relay 觀測缺 #120] → 本機 log/JSONL 觀測，Telegram 留 #120。

## Open Questions

- canary specs fixture 落點（`docs/canary/` vs `tests/fixtures/canary/`）——plan 定為 committed、可重現即可。
