# Tasks

> 詳細 TDD 見 `docs/superpowers/plans/2026-06-23-persona-manager-phase-d.md`。
> **Unit 3（live run）刻意排在 merge 之後**：agent worktree 從 `main` 切，需 fixtures+flags 已在 main。

## 1. Unit 1 — enabling flags（hermetic TDD）

- [x] 1.1 `tests/test_coordinator_launcher.py` 加 model passthrough failing tests（RED）
- [x] 1.2 `launcher.py`：三家 argv builder + `SubprocessLauncher` 加 `model`，GREEN
- [x] 1.3 CLI flag failing test（`--allow-unsafe`/`--model` → `_resolve_launcher` 帶對應值）（RED）
- [x] 1.4 `cli.py`：`tick`/`fanout` 加 `--allow-unsafe`/`--model` + `--allow-unsafe` fail-closed 守門，GREEN
- [x] 1.5 commit

## 2. Unit 2 — canary slice fixture + runbook

- [x] 2.1 committed canary slice（`dispatch:auto`、有界 plan「建 tests/canary_pong.md 一行即停」）三家各一
- [x] 2.2 runbook（`docs/canary/RUNBOOK.md`）：live 程序、觀測點、清理
- [x] 2.3 commit

## 3. Unit 3 — live run（蒐證，依序三家）— **merge 後對 main 執行**

- [ ] 3.1 claude：`tick --specs-dir docs/canary/claude --executor claude --allow-unsafe` → 觀察 dispatch→headless→done→manifest，貼證
- [ ] 3.2 codex：`--executor codex --allow-unsafe`，記錄結果
- [ ] 3.3 copilot：`--executor copilot --allow-unsafe --model haiku-4.5`，記錄結果
- [ ] 3.4 蒐證彙整成 canary record；清理 worktree/產物
- [ ] 3.5 全程確認主工作樹/bot 無感

## 4. 驗證與收尾

- [x] 4.1 Unit 1 hermetic 套件 + 全 suite 無回歸（1270 passed）
- [x] 4.2 code review + `/codex:adversarial-review`（G-A/G-B 已修）
- [ ] 4.3 canary record 寫入 PR；archive + PR（live run 後補 record）
