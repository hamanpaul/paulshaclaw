# stage7-deploy-three-plane / plan

## Scope

- Stage: 7
- 目標: 落地 core/state/secret 三分部署流程
- 先決依賴: Stage 1 最小可跑版
- In scope: `paulshaclaw/deploy/`、`paulshaclaw/config/`、`openspec/specs/stage7/`
- Out of scope: Stage1~6 執行邏輯重構

## Steps

### Phase 1: Install baseline
1. 建立 install/upgrade/uninstall 命令骨架。
2. 建立 template rename 規則。

### Phase 2: Permission/Secret
1. 建立 state/secret 權限檢查。
2. 定義 secret install 互動流程。

### Phase 3: 驗證
1. 建立 fresh install/upgrade/uninstall 測試。
2. 建立 rollback 與還原驗證。

## Relevant files

- `openspec/specs/stage7/`
- `paulshaclaw/deploy/`
- `paulshaclaw/config/`
- `docs/ops/recovery.md`

## Verification

1. fresh box 安裝可完成。
2. upgrade 不覆寫 state/secret。
3. uninstall 只移除 core 與 service unit。
4. 權限檢查可拒絕不安全設定。

## Decisions

- Stage 7 嚴格遵守三分部署，不混入 runtime memory 內容。
