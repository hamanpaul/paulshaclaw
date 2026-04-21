# stage7-deploy-three-plane / review

## Scope

- `paulshaclaw/deploy/__init__.py`
- `paulshaclaw/deploy/__main__.py`
- `paulshaclaw/deploy/planner.py`
- `paulshaclaw/deploy/templates/`
- `tests/test_stage7_deploy_three_plane.py`
- `openspec/specs/stage7/spec.md`
- `docs/superpowers/workstreams/stage7-deploy-three-plane/`

## 規格符合度

| 項目 | 結果 | 備註 |
|---|---|---|
| install/upgrade/uninstall 命令骨架 | 通過 | `python -m paulshaclaw.deploy <cmd>` 輸出 JSON plan |
| template 檔清單與 rename 規則 | 通過 | 四個 template 檔覆蓋 core/state/secret，支援 `__INSTANCE__` + `.tmpl` 移除 |
| state/secret 權限檢查 | 通過 | `state` fail-closed 拒絕 group writable/other，`secret` 限 owner-only |
| secret install 互動步驟 | 通過 | 最小三步驟，未確認 `0700/0600` 即拒絕 |
| rollback 還原策略與檢查點 | 通過 | 三個命令皆有 checkpoint，upgrade/uninstall 保留 state/secret |
| TDD 證據保留 | 通過 | red/green/final output 與摘要皆已保存 |
| Stage5 邊界 | 通過 | 未修改 `docs/ops/recovery.md` |

## 測試與驗證

執行命令：

```bash
python3 -m unittest tests.test_stage7_deploy_three_plane -v
python3 -m unittest discover -s tests
```

結果摘要：

- `20260421-red-unittest.txt`：缺 `paulshaclaw.deploy` package，Red 成立
- `20260421-green-unittest.txt`：Stage7 9 tests 全通過
- `20260421-final-unittest-discover.txt`：全量 47 tests 全通過

## 自我 Code Review 結論

- Verdict: `approve with noted follow-up`
- 結論：本次變更以最小 diff 建立 Stage7 baseline，API 與 CLI 契約已可驗證，且未侵入既有 stage 模組。
- 我特別檢查了 `upgrade` / `uninstall` 計畫，確認其 rollback action 只標示保留 `state` / `secret`，沒有引入錯誤刪除行為。

## 尚存風險

1. 目前 `deploy` CLI 僅輸出 plan，尚未執行真實檔案複製、owner/group 設定與 systemd 操作。
2. 權限檢查目前只驗證 mode，不含實際檔案擁有者、ACL、symlink 與 realpath 逃逸檢查。
3. secret install 僅驗證互動步驟與 checkpoint 摘要，尚未整合 Stage 6 audit/approval 與真正 secret material bootstrap。

## 後續建議

1. 若要落地真實 installer，先補 filesystem transaction 與 checkpoint artifact 目錄。
2. 將 secret install flow 接到 Stage 6 approval/audit，避免高風險來源未留痕。
3. 補充 owner/group 與 symlink hardening 測試，再考慮擴到實體部署。
