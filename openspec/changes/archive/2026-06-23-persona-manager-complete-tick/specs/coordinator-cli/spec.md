## ADDED Requirements

### Requirement: CLI `complete` 子命令觸發完成側 tick

`coordinator-cli` SHALL 提供 `complete` 子命令，建立 `Dispatcher`（reuse 注入或預設 seam）→ 呼叫 `manager.complete_tick` → 以 JSON 印出 summary、exit `0`，與既有 `ready`/`fanout` 同構。MUST 支援 `--handoff-dir`（預設 `autonomy.DEFAULT_HANDOFF_DIR`）與可選 `--specs-dir`（設定後 `scan_specs` 取 metas，使 summary 附觀測用的 `released`）。`complete` 路徑 MUST NOT 觸發 pane 送字或 worktree 建立（完成側不派工）。

#### Scenario: complete 子命令補寫 manifest 並印 summary

- **WHEN** registry 中有一個已 `done` 但缺 manifest 的 job，執行 `cli.main(["complete", "--handoff-dir", <dir>], registry=<reg>, pane_sender=<fake>, worktree_creator=<fake>)`
- **THEN** 回傳碼 MUST 為 `0`，stdout MUST 為合法 summary JSON 且 `completed` 含該 slice，`<dir>/<slice>.json` MUST 被寫出，注入的 fake sender/creator MUST NOT 被呼叫
