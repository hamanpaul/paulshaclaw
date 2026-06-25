## 1. usage.py 純函式

- [ ] 1.1 RED：`test_usage.py` — extract_offered 抽 (id,title)；extract_cited 認 `[[sl-id]]`/裸 sl-id 且過濾非 offered；extract_matched 認 ≥8 字標題、排除短標題與已 cited；畸形輸入回空集合。watch fail。
- [ ] 1.2 GREEN：`paulshaclaw/memory/usage.py` 三純函式。
- [ ] 1.3 確認 1.1 全綠。

## 2. SessionStart offered + 引用前言（共用）

- [ ] 2.1 RED：測 `_wakeup_common` 算出 brief 後寫 `runtime/wakeup/<tool>__<sid>.json`（offered id+title）且 brief 帶引用前言；brief 空時不加前言不寫檔。watch fail。
- [ ] 2.2 GREEN：`paulshaclaw/memory/hooks/_wakeup_common.py` 加引用前言常數 + offered 抽取與原子寫入（best-effort）。
- [ ] 2.3 確認 2.1 全綠、既有 wakeup 行為無回歸。

## 3. claude SessionEnd used + ledger

- [ ] 3.1 RED：測 claude SessionEnd 給 offered 檔 + 假 transcript（assistant 引用 + user 文字）→ 寫含 offered id 陣列的 memory_usage event；缺 offered/transcript → 不寫不報錯。watch fail。
- [ ] 3.2 GREEN：`paulshaclaw/memory/hooks/claude_session_end.py` 加 usage 擷取（讀 offered、掃 assistant-only transcript、append ledger，best-effort）。
- [ ] 3.3 確認 3.1 全綠。

## 4. usage 查詢 CLI

- [ ] 4.1 RED：`test_memory_usage_cli.py` — 聚合樣本 ledger → per-slice offered/cited/matched/last_used + 彙總；offered-but-unused 計入 never-used；wakeup 檔不存在仍正確；`--since` 過濾。watch fail。
- [ ] 4.2 GREEN：`paulshaclaw/memory/cli.py` 加 `memory usage`（僅讀 ledger 聚合）。
- [ ] 4.3 確認 4.1 全綠。

## 5. 驗證與收尾

- [ ] 5.1 memory 相關 pytest 全綠（含新增三組），無回歸。
- [ ] 5.2 requesting-code-review；修 finding 後 re-review。
- [ ] 5.3 openspec archive；conventional commit；push；開 PR（Refs #148 + policy-exempt:issue-link，因 #148 為追蹤 issue 不關閉）。
