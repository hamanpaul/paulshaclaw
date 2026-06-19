# Persona 派工護欄 — 三角色契約整合進自主開發 pipeline 設計

> 日期：2026-06-18 ｜ 狀態：草案（待覆審）｜ 分支：`feature/persona-dispatch-guardrail`（待開）
> 前置脈絡：Stage 4 persona contract（`paulshaclaw/persona/`，現為孤島 library）；CLAUDE.md `[multi_agent_devflow]` / `[scope_violation]`（目前僅文字規則）

## 1. 背景與問題

Stage 4 persona 模組（414 LOC、測試 11/11 全過）已實作一套**以 lifecycle phase 為基礎的 RBAC 契約 + 護欄引擎**：

- `contract.py`：`PERSONA_CATALOG`（寫死的 manager/builder/reviewer）＋ `is_phase_allowed` ＋ `validate_handoff_message`
- `guardrail.py`：`evaluate_filesystem(role, path)` / `evaluate_tool(role, tool)`
- `context.py`：`build_persona_context(role, overlay)`（含 `instruction_append` / `tool_allowlist_additions` / `memory_loadout`）
- `shadow.py`：`run_shadow_validation(...)`（跑全部檢查但**只觀察不強制**）

**問題：整合度為零。** `from paulshaclaw.persona` 在 package 與測試外 0 命中；core/bot/lifecycle/monitor/cockpit 皆不引用。catalog 寫死在 Python（README 宣稱的 `personas.yaml` 不存在），且其 `write_paths`/`allowed_tools` 與實際開發流程對不上（manager 掛 `coordinator.dispatch` 但 coordinator 是 stub；builder 缺 `openspec/changes/archive/**`）。persona 是一座**被測試過但從未通電的孤島**。

本設計把 persona 接成 CLAUDE.md `multi_agent_devflow` / `scope_violation` 的**強制機制**，落地在以下這條「人類只在 brainstorm 介入」的自主開發 pipeline。

## 2. 目標與非目標

**目標**

- 把 persona 從孤島 library 變成**派工護欄**：在派工、PR、merge 三點約束「誰能在哪個 phase、寫哪些路徑、用哪些工具」並驗證角色交接。
- catalog 由寫死 Python 改為 config-driven `personas.yaml`，三角色（manager/builder/reviewer）重定義以對齊實際 pipeline。
- 強制採 **shadow→enforce** canary 式上線（沿用 Stage 2 promoter forward-only canary 同套路）。
- 整個整合**只動 paulshaclaw 一個 repo，零外部依賴**（不依賴 skill 安裝、不改 paulsha-conventions）。

**非目標（明確不做）**

- ❌ 在 paulsha-conventions 加 paulshaclaw 專用 rule。conventions 維持通用/shareable。
- ❌ 整包搬 coordinator skill（2224 LOC，含 provider-routing/relay/cron）。只自建本流程所需的 minimal CLI。
- ❌ 追版 conventions pin（1.0.2→1.0.4+，會啟用 R-21 secret-scan/R-22 doc-reference）。屬正交衛生工作，另案小 PR，不綁本設計。
- ❌ 即時 wrapper 攔截 copilot 的每個工具呼叫（過度工程；`--yolo` 本質難即時攔截，改以 PR diff 後驗為主）。

## 3. 目標 pipeline

人類唯一介入點在 (1) brainstorm；(2)~(6) 為自主流程。`① ② ③` = persona 護欄三個 touch point。

```
 (1) brainstorm ──── 人類唯一介入
       │  [manager]
       ▼
 (2) spec: openspec-propose + writing-plans
       │   ① persona: 發 builder 契約 render 進 PROMPT + 驗 handoff(manager→builder)
       ▼
 (3) copilot --model gpt-5.4 --yolo -p   ◄─── builder, ONE-SHOT, 不回頭
        ├ using-git-worktrees
        ├ TDD / subagent-driven
        ├ requesting-code-review（自審，仍是 builder）
        └ openspec-archive
        ✗ 不再 commit/push/PR；於 worktree branch local commit、不 push
       │  [manager 接手]
       ▼
 (4) manager: policy check + push branch + 寫/commit handoff manifest + 開 PR（code 已由 copilot local commit）
       │   ② persona gate(workflow側,軟): git diff main...<branch> 逐檔 evaluate_filesystem
       │     ├ 越界/policy fail ─► manager 派 fixer(builder契約,非copilot) 修 ─┐
       │     └ pass ─► 開 PR                                                   │
       ▼                                                                       │
 (5) adversarial-review (reviewer) 檢視 PR                                     │
       │     ├ 有問題 ─► manager 派 fixer 修 ───────────────────────────────────┤
       │     └ clean                                                           │
       ▼                                                                       │
 [CI] persona-scope.yml ② 硬後盾 ──► 擋 merge ◄────────── fixer 一樣過 ①②──────┘
       │   ③ persona: merge 前 handoff/policy 終檢  [manager]
       ▼
 (6) merge → main → pull
```

**並行 fan-out**：brainstorm 產 task list 後，manager 對每個「就緒」的 task 各開一個 worktree+pane 跑上面整條 pipeline（見 §9），彼此隔離、並行，不 serial 逐 task 審。

## 4. 角色契約 v2（`personas.yaml`）

把 `PERSONA_CATALOG` 從 `contract.py` 抽到 config，新增 loader（沿用既有 `validate_persona_schema`）。schema 對齊現有 `PersonaContract` 欄位，外加全域 `enforcement` 旗標。

```yaml
version: 1
enforcement: shadow          # shadow | enforce（全域；可被個別 role 的 enforcement 覆寫）
roles:
  manager:
    version: "2.0.0"
    summary: 編排 lifecycle、派工、policy/commit/push/PR、merge、fix 派工、task triage
    allowed_phases: ALL       # 沿用 lifecycle.schema.PHASES 全集
    write_paths: ["docs/**", "openspec/**", "lifecycle.yaml", "runtime/handoff/**"]
    allowed_tools: ["coordinator.dispatch", "coordinator.handoff", "git", "gh", "openspec", "python -m unittest"]
  builder:
    version: "2.0.0"
    summary: 在 bounded scope 內實作 build slice（copilot 首發 + fixer 後續）
    allowed_phases: ["build"]
    write_paths: ["paulshaclaw/**", "tests/**", "openspec/changes/archive/**"]
    allowed_tools: ["python -m unittest", "rg", "edit", "git add", "git commit"]   # 本地 commit 可；✗ git push / gh pr（manager 專屬）
  reviewer:
    version: "2.0.0"
    summary: adversarial 審查 artifact、記錄判決，不改 code
    allowed_phases: ["review"]
    write_paths: ["reports/review/**"]
    allowed_tools: ["python -m unittest", "rg"]            # ✗ 改 code
```

| 角色 | 扮演者 | 出現次數 |
|---|---|---|
| manager | 編排器（你的 workflow / coordinator CLI） | 全程 |
| builder | copilot(首發) ＋ fixer(非 copilot) | copilot×1；fixer×0..N |
| reviewer | adversarial-review agent | 1..N |

phases 沿用 `paulshaclaw.lifecycle.schema.PHASES`，三角色 phase 對應與現行 catalog 一致（manager 全 phase、builder=build、reviewer=review）。

## 5. 強制點 ①②③ + shadow

reuse 現有函式，不重寫判定邏輯。

- **① 派工（軟、進場）**：`build_persona_context(role)` 算出契約 → render 成 PROMPT 開頭約束段注入 copilot；`validate_handoff_message(manifest)` 驗工單合法，不合法不派工。**不擋寫入**（`--yolo` 無法即時攔），只設規矩 + 驗信封。
- **② PR diff（硬、驗收）**：copilot local commit 後，`git diff --name-only main...<branch>` 逐檔餵 `evaluate_filesystem(from_role, path)`；加角色不變式（reviewer 的 diff 不可含 code 編輯、builder 須帶測試）；下一棒 `validate_handoff_message`。**workflow 側軟擋**（驅動 fix 迴圈）＋ **CI 硬擋**（§8）。
- **③ merge 前（manager）**：handoff/policy 終檢。
- **shadow→enforce**：`enforcement: shadow` 時 `persona.gate` 只輸出 verdict（reuse `run_shadow_validation` 形狀）、exit 0；調 contract 至零誤殺後翻 `enforce`，違規 exit 非零。

新增薄 CLI：

```
python -m paulshaclaw.persona.gate \
    --role <from_role> --base main --head <branch> --manifest runtime/handoff/<slice_id>.json
# 輸出 JSON verdict；enforce 模式違規→exit 1，shadow→恆 exit 0（僅記錄）
```

## 6. handoff manifest（角色身分載體，一物兩用）

manager 開 PR 時於 `runtime/handoff/<slice_id>.json` 寫一份 handoff message：

```json
{
  "from_role": "builder",
  "to_role": "reviewer",
  "phase": "review",
  "gate_status": "passed",
  "slice_id": "persona-phase0-loader",
  "summary": "...",
  "artifact_refs": ["<PR url / branch>"],
  "created_at": "2026-06-18T00:00:00+08:00",
  "base": "main",
  "head": "feature/..."
}
```

- 滿足 `validate_handoff_message` 的 `_REQUIRED_HANDOFF_FIELDS`。
- CI（§8）讀 `from_role` → 知道「此 PR 由 builder 產」→ 以 builder scope 查 diff。
- 路徑 `runtime/handoff/**` 屬 manager write scope（§4）；diff 中此檔以 manager 身分判定，code diff 以 `from_role` 判定。

## 7. minimal coordinator CLI（`paulshaclaw/coordinator/`，自建）

把 `core/daemon.py` 的 `LocalCoordinator`（現為 counter stub）補成真 job 管理，提供 CLI。reuse 既有零件：

| 需要 | reuse | 補 |
|---|---|---|
| 送命令進 pane | `daemon._send_to_pane` | — |
| 建 worktree | `scripts/using-git-worktrees.sh` | — |
| config seam | `core/config.py: CoordinatorSettings` | — |
| job 追蹤/狀態 | — | job registry（狀態檔，例 `~/.agents/coordinator/jobs.json`） |
| CLI 入口 | — | `dispatch` / `jobs` / `stat` |
| 並行 fan-out | — | registry 多筆（pane+worktree 天然隔離） |
| 完成偵測 | — | branch 出現新 commit / pane idle |

```
python -m paulshaclaw.coordinator dispatch --task <id> --persona builder [--spec <path>]
python -m paulshaclaw.coordinator jobs
python -m paulshaclaw.coordinator stat <job_id>
```

copilot 啟動 = 經 registry 記一筆 job → `_send_to_pane` 送 `copilot --model gpt-5.4 --yolo -p "<契約+PROMPT>"`。**fallback**：若監督 copilot 取結構化結果太難，只把 custom-skills 的 `copilot_sdk_orchestrator.mjs` 單支搬入，其餘照自建（不整包搬 skill）。

## 8. 自建硬後盾（`persona-scope.yml` + `persona.gate`）

- paulshaclaw 自建 `.github/workflows/persona-scope.yml`：`on: pull_request` → 取 PR diff + 讀 manifest `from_role` → 跑 `python -m paulshaclaw.persona.gate`。
- 設為 main 的 **required status check**（repo branch protection；非 conventions 事務）。
- 模式跟 `personas.yaml` 的 `enforcement`：shadow=僅 annotate、enforce=violation 時 fail。
- 豁免：自管 label `policy-exempt:persona-scope`（gate 內部判讀，與 conventions R-rule 框架平行、不相依）。

> in-loop 的 pre-push 軟 ②（§5，在 dispatch 迴圈內快回饋）conventions 永遠做不到（它只在 PR 時跑），故一定自建。

## 9. manager fan-out + autonomy gate

- brainstorm 產 task list 後，manager 掃 `docs/superpowers/specs/*.md` 的 frontmatter：

```yaml
---
dispatch: auto            # auto = manager 可自主派工；hold（預設）= 等人類
slice_id: ...
plan: docs/superpowers/plans/<...>-plan.md
---
```

- 挑 `dispatch: auto` 且有對應 plan 的 task → 各開 worktree+pane **並行** fan-out（每個跑 §3 單任務 pipeline）。其餘維持 `hold` 等人類在 brainstorm 補。
- manager 的 triage/讀 spec 行為本身受治理（只讀、寫限 manager scope）。

## 10. 設計原則：persona ≠ agent

`builder` 首發由 copilot 扮演、修正時由別的 agent（fixer）扮演，但**都綁同一份 builder 契約**。契約綁角色、不綁哪支程式 → fixer 換任何 agent 都自動被 ②/CI 同一套規則治理。這是 hybrid 強制撐得起來的根因，也讓「copilot one-shot」與「fix 由非 copilot 做」自然成立。

## 11. 分階段交付

| Phase | 內容 | 獨立驗收 |
|---|---|---|
| **0 基礎** | catalog→`personas.yaml` ＋ 3 角色 v2 重定義 ＋ loader（reuse `validate_persona_schema`）。**無行為改變** | schema 驗證測試；既有 persona 測試全綠 |
| 1 shadow | handoff manifest ＋ ① contract render ＋ ② diff gate（shadow）＋ `persona.gate` CLI | 跑一個真 PR，gate 輸出 verdict、恆放行 |
| 2 coordinator CLI | §7 自建 dispatch/jobs/stat（可與 1 並行） | dispatch 一個 task 進 pane+worktree、jobs/stat 可查 |
| 3 硬擋 | `persona-scope.yml` required check → shadow→enforce 翻牌 | 故意越界 PR 被擋；exemption label 可放行 |
| 4 fan-out | frontmatter `dispatch:auto` ＋ manager triage ＋ 並行 | 多 task 並行各自 merge |

**第一個實作計畫鎖 Phase 0**：純結構搬移 + config 化，零行為改變、解鎖其餘階段、風險最低。

## 12. 測試策略

- **Phase 0**：`personas.yaml` round-trip（load→`validate_persona_schema` ok）；3 角色 write_paths/tools 對 fixture 路徑的 `evaluate_filesystem` 期望值；既有 11 persona 測試不回歸。
- **Phase 1**：`persona.gate` 對「合法 diff／越界 diff／reviewer 改 code／builder 無測試」四類 fixture 的 verdict；shadow 模式恆 exit 0。
- **Phase 2**：coordinator dispatch 用 fake pane-sender / temp git repo，驗 worktree 建立、registry 記錄、完成偵測。
- **Phase 3**：CI workflow 以 act/本機模擬 PR diff + manifest，驗 enforce fail / shadow pass / exemption。
- **Phase 4**：frontmatter `dispatch:auto` 篩選邏輯；多 job 並行 registry 無互相污染。

## 13. 風險與待驗

- **copilot 完成偵測**：`--yolo` 跑完的可靠訊號（branch commit vs pane idle vs sentinel）需 Phase 2 實測選定；未定前 fallback 為 sentinel 檔。
- **fixer 身分**：fix 由「非 copilot」的哪種 agent 執行（Claude Code subagent？）待定；對 persona 無影響（同 builder 契約），但 coordinator 啟動指令要支援多種 executor。
- **manifest 信任**：CI 讀 manifest 的 `from_role` 決定 scope；惡意改 manifest 降權的風險由「manifest 路徑屬 manager scope、改它即越界」緩解。
- **lifecycle PHASES 對齊**：v2 角色 phase 須與 `lifecycle.schema.PHASES` 實際值一致，Phase 0 實作時核對。

## 14. 決策紀錄（brainstorm 收斂）

1. **應用目標** = 多 agent 派工護欄（非 PreToolUse hook / operator 切換 / memory loadout）。
2. **強制方式** = hybrid ①(prompt 注入,軟) + ②(PR diff,硬)，shadow 先行。即時 wrapper 攔截否決（過度工程）。
3. **pipeline 形狀** = copilot one-shot 不回頭；`policy/commit/push/PR` 抽到 manager；fix 由 manager 另派 fixer（非 copilot）；一個 lifecycle copilot 只出現一次；copilot 於 worktree branch local commit、不 push（②對 `git diff main...<branch>`）。
4. **角色** = manager/builder/reviewer 三者全治理。
5. **dispatch 機制** = 自建 minimal coordinator CLI（否決整包搬 skill）。
6. **硬後盾** = 自建 `persona-scope.yml`（否決在 conventions 加專用 rule；conventions 維持通用，追版屬另案）。
7. **autonomy 訊號** = superpowers spec frontmatter `dispatch: auto`，預設 `hold`。
