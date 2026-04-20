# Stage 6 Spec: `ops-companion` security governance

## Scope

- 以 `ops-companion` 作為 Stage 6 的統一安全治理介面。
- 高風險動作一律先過 approval gate，再決定是否執行。
- 所有敏感輸入先過 redaction/classification，再進入紀錄或回報。
- 稽核採 append-only audit trail，必須可追 actor、action、target 與前一筆雜湊。

## Implementation surface

- 實作：`paulshaclaw/security/ops_companion.py`
- 測試：`tests/test_ops_companion_security.py`
- sync-back 目標：`custom-skills/ops-companion/`
- gate→audit 封裝：`record_approval_decision(...)`

## Approval gate

### High-risk command families

| rule_id | 命令族群 | 預設動作 |
|---|---|---|
| `ship-command` | `/ship ...` | 拒絕直接執行，要求 `interactive-approval` |
| `git-push` | `git push ...` | 拒絕直接執行，要求 explicit approval |
| `deploy-command` | `deploy ...`、`kubectl apply`、`helm upgrade` | 拒絕直接執行，要求 explicit approval |
| `package-install` | `pip install`、`npm install`、`apt-get install` 等 | 拒絕直接執行，要求 explicit approval |
| `remote-operation` | `ssh`、`scp`、`rsync`、`curl | sh` | 拒絕直接執行，要求 explicit approval |

### `/ship` 互動流程

1. 先將 `/ship` 判為 `ship-command`。
2. 未取得 approval 前，一律回傳 `required_action=interactive-approval`。
3. 只有 approval 明確成立時，才允許往下執行 ship。
4. deny/approve 結果都必須透過 `record_approval_decision(...)` 寫入 audit trail。

## Redaction / classification

| rule_id | 命中樣式 | classification |
|---|---|---|
| `bearer-token` | `Authorization: Bearer ...` | `credential`, `token` |
| `password-assignment` | `password=...` | `credential` |
| `github-token` | `ghp_...`、`github_pat_...` | `credential`, `token` |

規則要求：

1. 不可將原始敏感值寫回 redacted text。
2. 每次命中都要保留 `rule_hits` 與 `classifications`，供 audit/report 使用。
3. Stage 7 只 consume 安全檢查結果，不直接改寫 Stage 6 規則。

## Append-only audit trail

每筆 audit entry 至少包含：

- `actor`
- `action`
- `target`
- `approved`
- `classifications`
- `occurred_at`
- `previous_hash`
- `entry_hash`

驗證規則：

1. 第一筆 entry 的 `previous_hash` 固定為 `GENESIS`。
2. 後續 entry 的 `previous_hash` 必須等於前一筆 `entry_hash`。
3. 任一筆內容被篡改時，`verify()` 必須回報失敗與 `broken_index`。

## Verification

執行：

```bash
python3 -m unittest tests.test_ops_companion_security
```

預期：

1. `git push`、`/ship`、deploy/package install/remote op 在無 approval 時被拒絕。
2. redaction 能遮罩常見 token/password 形態，並輸出分類結果。
3. audit trail 可驗證 hash chain，且可偵測竄改。
