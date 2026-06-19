## Why

目前 Stage7 只存在 `openspec/specs/stage7/README.md` placeholder，缺少可驗收 Requirement/Scenario，因此三分部署（core/state/secret）相關交付無法透過 OpenSpec 追溯。

## What Changes

- 建立 `stage7-baseline` OpenSpec change artifacts：`proposal.md`、`design.md`、`tasks.md`、`specs/stage7/spec.md`
- 補齊 Stage7 canonical spec，納入：
  - install/upgrade/uninstall 命令骨架
  - template 清單與 rename 規則
  - state/secret 權限 fail-closed 檢查
  - secret install 最小互動流程
  - rollback checkpoints 與還原策略
- 明確 Stage7 只交付 baseline，未進入真實 installer 寫檔/啟停階段
- 無 BREAKING 變更

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `stage7`: 從 placeholder 升級為可驗收三分部署規格。

## Impact

- **OpenSpec change artifacts**
  - `openspec/changes/stage7-baseline/proposal.md`
  - `openspec/changes/stage7-baseline/design.md`
  - `openspec/changes/stage7-baseline/tasks.md`
  - `openspec/changes/stage7-baseline/specs/stage7/spec.md`
- **Canonical Stage7 spec**
  - `openspec/specs/stage7/spec.md`
- **驗證入口**
  - `python3 -m unittest tests.test_stage7_deploy_three_plane -v`
  - `openspec validate stage7-baseline --strict`
