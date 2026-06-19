# stage4-persona-contract / plan

## Scope

- Stage: 4
- 目標: 建立 persona contract / handoff / guardrail 基線
- 先決依賴: Stage 3 baseline
- In scope: `paulshaclaw/persona/`、`openspec/specs/stage4/`
- Out of scope: Stage 3 lifecycle 核心檔、Stage 6 安全引擎

## Steps

### Phase 1: Contract schema
1. 定義 personas.yaml 與最小角色集合。

### Phase 2: Handoff/Guardrail
1. 建立 handoff message schema。
2. 建立 filesystem/tool guardrail 最小版本。

### Phase 3: 驗證
1. 建立 persona scope / handoff / guardrail 測試。
2. 建立 shadow-run 驗證流程。

## Relevant files

- `openspec/specs/stage4/`
- `paulshaclaw/persona/`
- `docs/research/04.stage4-persona-role-catalog-handoff-guardrails-research.md`

## Verification

1. persona allowed_phases 可正確限制提交者。
2. handoff schema 可被 coordinator route。
3. guardrail 可拒絕越界工具與路徑。

## Decisions

- 先做 manager/builder/reviewer 三角色，其他角色後補。
