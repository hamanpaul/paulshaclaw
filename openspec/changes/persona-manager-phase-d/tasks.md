# Tasks

> 詳細 TDD 見 `docs/superpowers/plans/2026-06-23-persona-manager-phase-d.md`。

## 1. Unit 1 — enabling flags（hermetic TDD）

- [ ] 1.1 `tests/test_coordinator_launcher.py` 加 model passthrough failing tests（copilot/claude/codex 帶 model → argv 含 `--model`；None → 不含）（RED）
- [ ] 1.2 `launcher.py`：三家 argv builder + `SubprocessLauncher` 加 `model` 參數，GREEN
- [ ] 1.3 CLI flag failing test（`--allow-unsafe`/`--model` → 建出的 SubprocessLauncher 帶對應值；以可檢視方式驗證）（RED）
- [ ] 1.4 `cli.py`：`tick`/`fanout` 加 `--allow-unsafe`/`--model`，接線到 SubprocessLauncher，GREEN
- [ ] 1.5 commit

## 2. Unit 2 — canary slice fixture + runbook

- [ ] 2.1 建 committed canary slice（`dispatch:auto`、trivial 有界 plan「建 canary/PONG.md 一行即停」）於專用 canary specs dir
- [ ] 2.2 runbook（docs）：live 跑程序、觀測點、清理
- [ ] 2.3 commit

## 3. Unit 3 — live run（蒐證，依序三家）

- [ ] 3.1 claude：`tick --specs-dir <canary> --executor claude --allow-unsafe` → 觀察 dispatch→headless→done→manifest，貼證
- [ ] 3.2 codex：同上 `--executor codex --allow-unsafe`，記錄結果
- [ ] 3.3 copilot：`--executor copilot --allow-unsafe --model haiku-4.5`，記錄結果
- [ ] 3.4 蒐證彙整成 canary record（manifest + 末筆 JSONL + exit code + 耗時）；清理 worktree/產物
- [ ] 3.5 全程確認主工作樹/bot 無感

## 4. 驗證與收尾

- [ ] 4.1 Unit 1 hermetic 套件 + 全 suite 無回歸
- [ ] 4.2 code review + `/codex:adversarial-review`
- [ ] 4.3 canary record 寫入 PR；archive + PR
