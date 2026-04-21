# stage7-deploy-three-plane / plan

## Scope

- Stage: 7
- 目標: 落地 core/state/secret 三分部署 baseline
- 先決依賴: Stage 1 最小可跑版、Stage 6 security baseline
- In scope: `paulshaclaw/deploy/`、`tests/test_stage7_deploy_three_plane.py`、`openspec/specs/stage7/spec.md`、`docs/superpowers/workstreams/stage7-deploy-three-plane/`
- Out of scope: 真正執行系統安裝、副作用式部署、Stage5 recovery 文件調整

## Steps

### Phase 1: TDD Red
1. 新增 Stage7 單元測試，先鎖定三分部署 API/CLI 契約。
2. 執行 `python3 -m unittest tests.test_stage7_deploy_three_plane -v` 並保存失敗輸出。

### Phase 2: TDD Green
1. 新增 `paulshaclaw/deploy/` package 與 template placeholders。
2. 落地 install/upgrade/uninstall plan、rename 規則、權限檢查、secret install 流程、rollback baseline。
3. 重跑 Stage7 測試確認轉綠。

### Phase 3: 文件與回歸
1. 補齊 `openspec/specs/stage7/spec.md` 與 workstream `task/todo/review`。
2. 執行 `python3 -m unittest discover -s tests` 並保存 final evidence。
3. 自我 review 與風險盤點，確認未觸碰 `docs/ops/recovery.md`。

## Relevant files

- `paulshaclaw/deploy/`
- `tests/test_stage7_deploy_three_plane.py`
- `openspec/specs/stage7/spec.md`
- `docs/superpowers/workstreams/stage7-deploy-three-plane/task.md`
- `docs/superpowers/workstreams/stage7-deploy-three-plane/todo.md`
- `docs/superpowers/workstreams/stage7-deploy-three-plane/review.md`
- `docs/superpowers/workstreams/stage7-deploy-three-plane/evidence/`

## Verification

1. `python3 -m unittest tests.test_stage7_deploy_three_plane -v` 先失敗後通過。
2. `python3 -m unittest discover -s tests` 全量通過。
3. `upgrade` / `uninstall` plan 明確保留 state/secret。
4. 權限檢查拒絕不安全的 state/secret mode。

## Decisions

- Stage 7 僅建立可驗證的 plan 與 guardrail，不在此階段實作真實部署副作用。
- secret install 僅保留最小互動步驟與 checkpoint 摘要，實際 secret material 拉取留待後續 stage 延伸。
