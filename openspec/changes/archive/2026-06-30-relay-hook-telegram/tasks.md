## 1. Half 1 — manager 進度 → Telegram（psc-relay-hook.sh）

- [x] 1.1 RED：`tests/test_coordinator_relay_hook.py` 擴充——`PSC_SLICE_ID` 設→呼叫 reply_bridge（PATH stub 記 argv）；未設/`unknown`/空→不呼叫；reply_bridge 缺檔/失敗→hook 仍 exit 0。
- [x] 1.2 GREEN：`scripts/coordinator/psc-relay-hook.sh` 寫檔後，gate 於 `$slice != "unknown"` 才 best-effort `timeout 8 reply_bridge.py --text "$msg"`（無 `--source-user-id`），`|| true` 不影響 agent。（review I-1：加 `timeout`。）
- [x] 1.3 `bash -n` 通過，relay 測試全綠（6 案，含 empty-slice m-1）。

## 2. Half 2 — codex/copilot 互動回程（psc-bro-return.py，turn-scoped）

- [x] 2.1 RED→GREEN：turn-scoped 四案（first-bro→local 不送、first-bro→別 user 送新 user、first-local→bro 送 bro、無 marker 不送）。
- [x] 2.2 回覆來源案——copilot 經 read_copilot_history；codex 經 Stop payload last_assistant_message；缺 key→skip+log 不送 EMPTY_NOTICE；空→EMPTY_NOTICE；例外→exit 0+log。（review：加 `timeout=15`、sender 例外 return False、copilot 診斷 log、端到端 handle()、非字串 reply 測試。）
- [x] 2.3 GREEN：`scripts/gemma4-hooks/psc-bro-return.py`（`--platform codex|copilot`），hook always exit 0。
- [x] 2.4 10 案全綠。

## 3. 安裝接線（codex Stop / copilot agentStop）

- [x] 3.1 hook 模板：`scripts/coordinator/hooks/{codex,copilot}.json` 加 `managedBy: psc-bro-return` entry（`PYTHONPATH=${PSC_REPO_ROOT} python3 …`，保留既有 relay），+ 模板測試。
- [x] 3.2 安裝：**手動裝進 live config**（codex `~/.codex/hooks.json` Stop nested merge、copilot `~/.copilot/hooks/psc-relay.json` agentStop append；**絕對路徑**因互動 session 無 `${PSC_REPO_ROOT}`；保留 `psc-coordinator-relay`/`paulsha-memory`；已備份）。**自動化（install 腳本 + 三家一致 abspath/${PSC_REPO_ROOT}）整包歸 [#128]**。
- [x] 3.3 install 自動化測試 → 隨 #128（本次無 install 腳本可測；live 裝以結構驗證 + e2e 送代替）。

## 4. Verify / docs / 收尾

- [x] 4.1 全量 `pytest tests/` → 610 passed（僅 2 個既有 Stage11 env-flaky，無新 regression）；#120 相關 46 passed。
- [x] 4.2 docs（R-18）：本 change 的 design spec + openspec proposal/design/specs 即 docs（`docs/superpowers/specs/2026-06-30-…` + `openspec/changes/relay-hook-telegram/`）；README 無被本變更推翻的敘述，故不動 README。
- [ ] 4.3 openspec archive（phase 9）+ policy gate + finishing（phase 10，本地）+ codex adversarial（phase 11）。
- live 驗證：`reply_bridge --dry-run` binding 解析 OK；合成 codex Stop event → 實際安裝指令 e2e exit 0、log 無新增 → 已送 Telegram（待 operator 人工確認收件）。
