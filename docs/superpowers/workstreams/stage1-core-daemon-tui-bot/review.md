# stage1-core-daemon-tui-bot / review

## Scope

- `paulshaclaw/core/config.py`
- `paulshaclaw/core/daemon.py`
- `paulshaclaw/tui/view.py`
- `paulshaclaw/bot/telegram.py`
- `tests/test_stage1_smoke.py`
- `config/paulshaclaw-stage1.sample.json`
- workstream 文件與 evidence

## 規格符合度

| 項目 | 結果 | 備註 |
|---|---|---|
| daemon 啟動入口與設定載入 | 通過 | CLI 支援 `--config` 與 `PSC_STAGE1_CONFIG` |
| TUI pane/任務映射視圖 | 通過 | `render_pane_task_view()` 直接輸出純文字表格 |
| Telegram 指令入口（最小集） | 通過 | 授權檢查 + `/status` + `/dispatch` + 未知指令明確錯誤 |
| coordinator 派工入口 | 通過 | 以 `CoordinatorClient` 契約接到 daemon dispatch，不含 Stage 3 gate |
| stage1 smoke test | 通過 | `tests/test_stage1_smoke.py` 共 8 個 smoke tests |

## Strengths

1. `core` / `tui` / `bot` 邊界清楚，Stage 3 後續可直接 consume `status/dispatch` 入口。
2. 設定載入契約完整，CLI flag 與環境變數 fallback 都有測試覆蓋。
3. Telegram 入口已處理未授權使用者與未知指令，避免最小 bot surface 直接炸掉。
4. smoke tests 直接打真實模組與 CLI，沒有落入 mock-only 驗證。

## Issues

### Critical

- 無

### Important

- 無

### Minor

1. `paulshaclaw/core/daemon.py`
   - 目前 coordinator 仍是最小契約 / local fallback，這輪驗證的是 Stage 1 dispatch 介面，不是實際外部 coordinator transport。
   - 影響：當後續要接真實 coordinator runtime 時，仍需補 transport adapter 與整合測試。

## 測試完整性

- 已覆蓋：設定載入、env fallback、daemon status、coordinator dispatch、TUI 視圖、Telegram 授權、Telegram 未知指令、CLI 啟動。
- 未覆蓋：真實 coordinator 外部程序整合、Telegram 平台 API round-trip、TUI 互動式 redraw。

## Review 結論

- Verdict: `approve`
- 結論：本切片已符合 Stage 1 最小可跑版與 workstream task/todo 要求，回歸風險低；保留的風險主要是下一階段接真實 coordinator transport 時的整合工作。
