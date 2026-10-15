# Runtime evidence

完整原始報告由 `run_historical.py --report-dir <directory>` 產生：

- `deploy-report.json`：逐步 exit/stdout/stderr、provenance、container ID 與 cleanup。
- `deploy-report.md`：矩陣、逐步 gates 與原始 JSON 連結。

CI 上傳 `deploy-regression-reports` artifact。舊 Cortex summary 未包含逐步原件，
不作本次完成證據；本次重新執行歷史矩陣。
