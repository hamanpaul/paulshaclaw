# stage6-ops-companion-security / plan

## Scope

- Stage: 6
- 目標: 以 `ops-companion` 建立 approval/redaction/audit 治理
- 先決依賴: Stage 0 命名 baseline + Stage 1 action path
- In scope: `paulshaclaw/security/`、`openspec/specs/stage6/`
- Out of scope: Stage1 core workflow 重構、Stage2 memory pipeline 重構

## Steps

### Phase 1: Approval gate
1. 對 `git push/deploy/package install/remote op` 建立統一 gate。

### Phase 2: Redaction/Audit
1. 建立 redaction 與 classification 規則。
2. 建立 append-only audit trail。

### Phase 3: 安全驗證
1. 建立 approval flow 測試。
2. 建立 redaction fuzz 與 audit 驗證。

## Relevant files

- `openspec/specs/stage6/`
- `paulshaclaw/security/`
- `custom-skills/ops-companion/`
- `tests/test_ops_companion_security.py`
- `openspec/specs/stage0/tool-matrix.md`

## Verification

1. 高風險命令無 approval 必拒絕。
2. redaction 可命中常見敏感字串規則。
3. audit trail 具 append-only 特性且可追溯 actor。

## Decisions

- `ops-companion` 最終需回寫 `custom-skills/ops-companion`，回寫前必須通過 Stage 6 測試。
- Stage 7 只 consume Stage 6 security check 結果，不直接改寫 Stage 6 規則。
