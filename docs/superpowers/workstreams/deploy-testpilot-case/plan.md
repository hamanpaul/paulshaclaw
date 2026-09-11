---
work_item: deploy-testpilot-case
---
# deploy-testpilot-case / plan

## Scope
見 hamanpaul/paulshaclaw#324：只做 test case（RED），不修 bug。

## Steps
依 #324「建議佈局」與「驗收」；細部由 cortex planner 產出正式 plan。

## Relevant files
`testpilot/`（新）、`.github/workflows/tests.yml`、README／docs。

## Verification
`testpilot list-cases paulshaclaw_deploy`；TC-1 RED report；`testpilot/tests/` 綠；`./scripts/preflight-tests.sh` 綠。

## Decisions
plugin 為獨立子專案，不讓 operator shell wheel 依賴 testpilot-core。
