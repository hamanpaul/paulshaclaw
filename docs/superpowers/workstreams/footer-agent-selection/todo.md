---
work_item: footer-agent-selection
---

# cost footer 新增 agy 與安裝時 agent／account 選擇

對應 hamanpaul/paulshaclaw#341。accepted spec／design／plan 見 `docs/superpowers/specs/footer-agent-selection-{spec,design}.md` 與 `docs/superpowers/plans/footer-agent-selection.md`。

## Current Sprint

- [ ] 依本 work item 的 accepted spec/design/plan 實作並提交 scope 內變更。
- [ ] 完成 focused tests、完整 preflight、獨立 review 與 PR。
- [ ] 核對合併、正式 artifacts 與適用的 installed/runtime evidence 後結案。

## Handoff

建議 branch：`feature/341-footer-agent-selection`。

- [ ] T1 agy 用量來源調查結論寫進 tasks.md（有可信來源 → `api`；無 → 本輪 `unknown`）。
- [ ] T2–T4 config `enabled`／`AgyProviderConfig`、`collect_agy()`＋formatter、`detect_agents()` 零讀取守衛。
- [ ] T5–T7 `--footer` 決策矩陣與 report 欄位、deep-merge 寫回＋備份、textual TUI（Pilot 三情境）。
- [ ] T8–T9 README／sample yaml／changelog 碎片；preflight 全綠、獨立 review、PR `Closes #341`。

驗收：spec Acceptance 四條；乾淨 venv e2e 無旗標無 TTY 仍綠且 `footer_selection.mode == "skipped"`；既有 config 載入後 footer 逐字元不變。
