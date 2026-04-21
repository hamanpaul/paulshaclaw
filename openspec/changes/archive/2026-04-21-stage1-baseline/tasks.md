> Stage 1 baseline 為 reverse-record change：Stage 1 本體已於 commit `49d2739` 以 `--no-ff` 合併至 main。以下任務均為對照已落地工作驗證 spec 成立的反向檢核。

## 1. Daemon runtime baseline

- [x] 1.1 確認 `paulshaclaw/core/daemon.py` 的 `/status` 回傳五欄位（ok/daemon/project/pane_count/allowed_user_count）
- [x] 1.2 確認 `/dispatch <task_id>` 回傳四欄位（ok/job_id/phase/scope）且傳給 coordinator 的 payload 含 `task_id`
- [x] 1.3 確認 `/dispatch` 缺 task_id 會拋驗證錯誤且未呼叫 coordinator
- [x] 1.4 確認 `CoordinatorClient` Protocol 存在且支援注入（`LocalCoordinator` 為預設實作）

## 2. Config & CLI baseline

- [x] 2.1 確認 `load_config` 以 `--config` > `PSC_STAGE1_CONFIG` > 失敗 的順序解析路徑
- [x] 2.2 確認缺必填欄位（例如 `pane_assignments`）時錯誤訊息包含完整欄位路徑
- [x] 2.3 確認 CLI 成功輸出 JSON 到 stdout 且 exit 0；失敗輸出乾淨錯誤到 stderr 且 exit 1、無 traceback
- [x] 2.4 確認 `config/paulshaclaw-stage1.sample.json` 可被 `load_config` 直接載入

## 3. TUI & Telegram baseline

- [x] 3.1 確認 TUI 渲染列出所有 pane id / title / task / status 且順序穩定
- [x] 3.2 確認 Telegram router 拒絕非白名單 user_id 且不呼叫 daemon
- [x] 3.3 確認 Telegram router 對授權 user_id 正確呼叫 daemon 並回傳結果

## 4. Smoke test baseline

- [x] 4.1 `python -m unittest discover -s tests -v` 全部 12 條 PASS（證據：`docs/superpowers/workstreams/stage1-core-daemon-tui-bot/evidence/20260420-final-unittest.txt` 與本輪 merge 後重跑）
- [x] 4.2 code review 7/7 contract 項目 PASS（`docs/superpowers/workstreams/stage1-core-daemon-tui-bot/review.md`）

## 5. Archive readiness

- [x] 5.1 `openspec validate stage1-baseline --strict` 通過
- [x] 5.2 `openspec archive stage1-baseline --yes` 同步 delta 至 `openspec/specs/stage1-core-runtime/spec.md`
