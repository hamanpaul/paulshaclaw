## ADDED Requirements

### Requirement: Stage7 three-plane deployment baseline

Stage7 MUST 提供 `install`/`upgrade`/`uninstall` 命令骨架，輸出包含 templates、steps、rollback checkpoints/actions 的 deployment plan，並維持 `core/state/secret` 三分邊界。

#### Scenario: Stage7 CLI plan output is verifiable

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage7_deploy_three_plane.DeployCliTests -v`
- **THEN** 三個子命令 MUST 成功輸出 JSON plan 且包含 rollback checkpoints

### Requirement: Stage7 permission and secret-install baseline

Stage7 MUST 對 `state`/`secret` 權限採 fail-closed，並提供 secret install 最小互動流程（含權限確認與 checkpoint）。

#### Scenario: Unsafe permission or missing ack is denied

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage7_deploy_three_plane.PermissionPolicyTests tests.test_stage7_deploy_three_plane.SecretInstallFlowTests -v`
- **THEN** 不安全 mode 或未確認 `0700/0600` 權限 MUST 被拒絕，合法流程 MUST 產出 `secret-preflight` 與 `secret-installed`

### Requirement: Stage7 evidence and scope boundary

Stage7 MUST 保留 red/green/final TDD 證據於 `docs/superpowers/workstreams/stage7-deploy-three-plane/evidence/`，且 MUST NOT 修改 Stage5 專屬 `docs/ops/recovery.md`。

#### Scenario: Evidence exists and stage scope is respected

- **WHEN** 審查者檢查 Stage7 workstream 檔案與 git diff
- **THEN** evidence 檔案 MUST 存在，且 `docs/ops/recovery.md` 不在 Stage7 變更集合中
