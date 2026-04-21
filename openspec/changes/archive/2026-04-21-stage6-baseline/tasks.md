> Stage 6 baseline 為 reverse-record change：Stage 6 實作已透過 cherry-pick 收斂到 main。下列任務為反向檢核清單。

## 1. Approval gate baseline

- [x] 1.1 `ops_companion.py` 定義 `ship-command/git-push/deploy-command/package-install/remote-operation`
- [x] 1.2 `/ship` 無 approval 時回傳 `interactive-approval`
- [x] 1.3 `package-install` 覆蓋 `install/get/add`（含 npm/pnpm/yarn add）

## 2. Redaction / classification baseline

- [x] 2.1 覆蓋 bearer token / password assignment / github token 三類
- [x] 2.2 redaction 結果保留 `rule_hits` 與 `classifications`

## 3. Append-only audit baseline

- [x] 3.1 具 `GENESIS` + `previous_hash/entry_hash` 鏈結
- [x] 3.2 篡改可被 `verify()` 偵測並回報 `broken_index`
- [x] 3.3 deny/approve 都透過 `record_approval_decision(...)` 寫入 audit

## 4. Test evidence

- [x] 4.1 `python3 -m unittest tests.test_ops_companion_security` 通過
- [x] 4.2 `python3 -m unittest discover -s tests` 通過
- [x] 4.3 Stage 6 evidence 與 review 文件存在且可追溯

## 5. Archive readiness

- [x] 5.1 新增 `openspec/specs/stage6-security-governance/spec.md`
- [x] 5.2 建立 `openspec/changes/archive/2026-04-21-stage6-baseline/` 反向記錄
- [x] 5.3 shared sync-back gate 文案維持通用，不回退 Stage 0 規範
