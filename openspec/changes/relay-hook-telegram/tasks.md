## 1. Half 1 — manager 進度 → Telegram（psc-relay-hook.sh）

- [ ] 1.1 RED：`tests/test_coordinator_relay_hook.py` 擴充——`PSC_SLICE_ID` 設→呼叫 reply_bridge（PATH stub 記 argv）；未設/`unknown`→不呼叫；reply_bridge 缺檔/失敗→hook 仍 exit 0。先紅。
- [ ] 1.2 GREEN：`scripts/coordinator/psc-relay-hook.sh` 寫檔後，gate 於 `PSC_SLICE_ID`（非 unknown）才 best-effort `reply_bridge.py --text "$msg"`（無 `--source-user-id`），`|| true` 不影響 agent。
- [ ] 1.3 `bash -n scripts/coordinator/psc-relay-hook.sh` 通過，1.1 全綠。

## 2. Half 2 — codex/copilot 互動回程（psc-bro-return.py，turn-scoped）

- [ ] 2.1 RED：新 `tests/test_psc_bro_return.py`（注入 user_prompts/assistant、fake sender）——turn-scoped 四案：first-bro→local 不送、first-bro→別 user 送新 user、first-local→bro 送 bro、無 marker 不送。先紅。
- [ ] 2.2 RED：回覆來源案——copilot 經 read_copilot_history 送；codex 經 Stop payload last_assistant_message 送；**codex 缺 last_assistant_message（rollout 有 assistant）→ skip+log 不送 EMPTY_NOTICE**；讀得到但空→送 EMPTY_NOTICE；reader/sender 例外→exit 0+log。
- [ ] 2.3 GREEN：`scripts/gemma4-hooks/psc-bro-return.py`（`--platform codex|copilot`）——取本輪 `user_prompts[-1]` 的 `[bro:id]`（無→no-op）；copilot 回覆走 `read_copilot_history`、codex 回覆走 event payload `last_assistant_message`；讀不到→skip+log；`reply_bridge.py --source-user-id` 送出；hook always exit 0。
- [ ] 2.4 2.1/2.2 全綠。

## 3. 安裝接線（codex Stop / copilot agentStop）

- [ ] 3.1 hook 模板：codex `Stop` / copilot `agentStop` 加 `managedBy: psc-bro-return` entry（指向 package-aware venv 跑 psc-bro-return.py）。
- [ ] 3.2 install 腳本：nested merge 進三家既有 hook config，保留 `psc-coordinator-relay` / `paulsha-memory` 等既有 entry（不覆寫）。
- [ ] 3.3 install 腳本若有可測點（merge 函式）→ 補單元測試（保留既有 entry、冪等重裝）。

## 4. Verify / docs / 收尾

- [ ] 4.1 `PYTHONPATH=. pytest tests/test_coordinator_relay_hook.py tests/test_psc_bro_return.py tests/test_gemma4_bro_hooks.py tests/test_telegram_reply.py -q` 全綠（含既有不回歸）。
- [ ] 4.2 README / docs 對齊（R-18）：補 codex/copilot 回程與 manager 進度 Telegram 已接線。
- [ ] 4.3 openspec archive（phase 9）+ policy gate（policy_check）+ conventional-commit（phase 10，本地）。
