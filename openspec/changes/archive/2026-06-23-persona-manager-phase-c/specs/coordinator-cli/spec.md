## ADDED Requirements

### Requirement: CLI `tick` 子命令觸發完整 manager tick

`coordinator-cli` SHALL 提供 `tick` 子命令，建立 `Dispatcher`（reuse 注入或預設 seam）與（依 `--executor`）launcher → 呼叫 `manager.run_tick` → 以 JSON 印出 summary、exit `0`，與既有 `fanout`/`complete` 同構。MUST 支援 `--specs-dir`（必填，`scan_specs` 取 metas）、`--executor`、`--handoff-dir`、`--require-idle`、`--max-load`。

#### Scenario: tick 子命令 idle 未達時印 skipped

- **WHEN** 執行 `cli.main(["tick", "--specs-dir", <dir>, "--require-idle", "--max-load", "0"], registry=<reg>, ...)`（注入 fake seam 使 idle 判定為非 idle）
- **THEN** 回傳碼 MUST 為 `0`，stdout MUST 為合法 summary JSON 且 `skipped` 為 `'not-idle'`
