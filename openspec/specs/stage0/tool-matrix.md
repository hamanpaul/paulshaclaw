# Stage 0 Tool Matrix（Baseline）

- 基準日期：2026-04-20
- 來源基準：`docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md` §8 Stage 0
- 參考 repo 清單：`openspec/specs/stage0/ref-manifest.yaml`

---

## A. 外部參考 Repo 盤點

| Repo | 本地路徑 | Stage 依賴 | Pin | 狀態 |
|---|---|---|---|---|
| `hamanpaul/custom-claw-tools` | `ref/custom-claw-tools` | 2, 6 | `8bd0f156606eb078f8979a7a40441ee0e9d96e34` | cloned |
| `hamanpaul/custom-skills` | `ref/custom-skills` | 0, 1, 2, 3, 4 | `056104aef3ac9b66c3dfe59495de37ada3909d14` | cloned |
| `hamanpaul/max` | `ref/max` | 1 | `9c2204cd0d531c303763f1735c6956117353cc0c` | cloned |
| `hamanpaul/serialwrap` | `ref/serialwrap` | 4 | `dc57a547ce5357c9d60cd7923e2b515770e98525` | cloned |
| `hamanpaul/testpilot` | `ref/testpilot` | 4 | `7963cff9037effb736ae2ef16660e6ae9867cc63` | cloned |

備註：
- `ref/` 只作開發閱讀/比對，不作 runtime 載入。
- `obs-note-cron` 已依 Stage 0 調校決策移除，不納入基線。

---

## B. Stage 0 refine 工具矩陣

| 工具/主題 | 舊名 | 目標名 | 來源 repo | 最終落點 | Claude Code 支援狀態 | refine PR / tracking |
|---|---|---|---|---|---|---|
| Security gate companion | `picoclaw-ops-companion` | `ops-companion` | `custom-claw-tools` | `custom-skills/ops-companion`（新子專案） | pending（命名與介面待調校） | 未開 PR；先完成 rename、介面對齊與 Stage 6 gate 驗證 |
| Stage 2 memory core | `obs-auto-moc` | `paulsha-memory` | `custom-claw-tools` | `custom-skills/paulsha-memory`（新子專案） | partial（已有 Decayed/record-agent-reference，待專案化） | 未開 PR；先完成 Stage 2 邊界聲明與專案化切分 |
| Session lesson | `codex-lesson` | `session-lesson`（暫定） | `custom-skills` | `custom-skills/session-lesson`（可同 repo evolve） | partial（以 codex 命名為主） | 未開 PR；先補 alias/rename 與 Claude Code session adapter |
| Cross-session insights | `codex-project-insights` | `project-insights`（暫定） | `custom-skills` | `custom-skills/project-insights`（可同 repo evolve） | partial（以 codex 命名為主） | 未開 PR；先補 alias/rename 與跨 session 查詢驗證 |
| Session health parser | `session-health` | `session-health`（暫維持） | `hamanpaul/session-health`（未納入 ref） | 依 Stage 0 決策後回寫 `custom-skills` | unknown（待補 clone + 驗證） | 未開 PR；先補 clone、Claude Code session parser 與輸出 schema 對齊 |
| Multi-agent coordinator | `coordinator` | `coordinator`（維持） | `custom-skills` | `custom-skills/coordinator` | partial（provider 預設偏 `codex`） | 未開 PR；先補 `claude` provider 預設與 delegate template |

---

## C. 本輪盤點結論

1. Stage 0 `ref/` 主清單現為 5 個 repo（`obs-note-cron` 已移除），本地可直接閱讀與比對。
2. `ops-companion` 與 `paulsha-memory` 已列為明確 rename 目標，且最終落點均為 `custom-skills` 新子專案。
3. Stage 0 的 rename/refine 尚未開 PR，現階段先以 tracking 欄位標示各項前置條件，待證據齊備後再送 PR。

---

## D. Sync 回 custom-skills 資格規範

1. 所有從 `ref/` 取得並經本專案調校的 skill，最終都必須回寫到 `hamanpaul/custom-skills`。
2. 回寫前必須先通過該 skill 所屬 stage 測試，且保存測試證據（測試報告/紀錄）。
3. 未通過 stage 測試的變更，不具備 sync 回 `custom-skills` 的資格。
