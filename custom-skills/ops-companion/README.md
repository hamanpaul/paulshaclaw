# custom-skills/ops-companion

## 角色

`ops-companion` 是 Stage 6 的安全治理 sync-back 目標，承接下列 contract：

1. 高風險動作 approval gate
2. 敏感輸入 redaction / classification
3. append-only audit trail（含 `record_approval_decision(...)` 封裝）

## sync-back gate

回寫 `custom-skills/ops-companion` 前，至少要滿足：

1. 已通過 Stage 6 測試。
2. 已保存測試證據到 `docs/superpowers/workstreams/stage6-ops-companion-security/evidence/`。
3. `/ship` approval flow、redaction、audit 三類規則都有對應驗證。

## 本輪落地來源

- 規格：`openspec/specs/stage6/README.md`
- 實作：`paulshaclaw/security/ops_companion.py`
- 測試：`tests/test_ops_companion_security.py`
