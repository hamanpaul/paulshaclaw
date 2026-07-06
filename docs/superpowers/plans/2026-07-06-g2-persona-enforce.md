# G2 Persona Enforce 翻牌 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> **實作者：gpt5.3-codex**。分支 `feature/124-g2-persona-enforce`，worktree。**depends_on: g1-coordinator-adapter**（試點需真 dispatch 流量；程式碼層無 import 依賴，可先行開發、驗收等 G1）。
> 依據：`openspec/changes/g2-persona-enforce/`＋`docs/superpowers/specs/2026-07-06-g2-persona-enforce-design.md`（審查修正：繞過面關閉）。

**Goal:** builder 先 enforce；違規 PR exit 1；省略 manifest 不再是繞過。

**Architecture:** personas.yaml per-persona override → scope_ci PR-bound manifest（branch↔slice）→ enforce 三路判定（有 manifest 依 verdict／無 manifest 依 governed-paths 交集／label 豁免）。

**錨點**：`persona/scope_ci.py:32-42`（find_latest_manifest 待棄）、`:42-122`（main 全 shadow 路徑）、`persona/personas.yaml:2`、`.github/workflows/persona-scope.yml:4-5,33-34`、`persona/gate.py`（compute_changed_paths 既有）。

---

### Task 1: 設定模型 per-persona override

**Files:** Modify `paulshaclaw/persona/personas.yaml`、loader（`persona/loader.py`）；Test `tests/test_persona_loader*.py`

- [ ] **Step 1: 失敗測試**

```python
def test_effective_enforcement_override():
    cfg = load_personas(FIXTURE_WITH_BUILDER_ENFORCE)
    assert cfg.effective_enforcement("builder") == "enforce"
    assert cfg.effective_enforcement("manager") == "shadow"   # 繼承全域

def test_unknown_enforcement_value_failsafe(caplog):
    cfg = load_personas(FIXTURE_WITH_TYPO)
    assert cfg.effective_enforcement("builder") == "shadow"
    assert any("unknown enforcement" in r.message for r in caplog.records)
```

- [ ] **Step 2: RED → Step 3:** loader 加 `effective_enforcement(role)`（role override → 全域 → "shadow"）；personas.yaml `roles.builder.enforcement: enforce`；GREEN → **Commit**

### Task 2: PR-bound manifest

**Files:** Modify `paulshaclaw/persona/scope_ci.py`；Test `tests/test_persona_scope_ci.py`

- [ ] **Step 1: 失敗測試**：head branch `feature/s1-xxx` 且存在 `runtime/handoff/s1.json` → 取用；存在較新的無關 `s2.json` 而無 `s1.json` → 視同無 manifest（**不得**取 s2）；多筆匹配 → 視同無。
- [ ] **Step 2: RED → Step 3:** 新 `find_pr_bound_manifest(head_branch, repo_root)`：對 handoff/*.json 以 `slice_id in head_branch`（完整 token 匹配，避免子字串誤中）取唯一者；`main()` 改用之，`find_latest_manifest` 保留但 deprecated 註記；GREEN → **Commit**

### Task 3: enforce 判定三路

**Files:** Modify `scope_ci.py` main；Test 同檔

- [ ] **Step 1: 失敗測試**（各態）：enforce＋違規→1；enforce＋乾淨→0；enforce＋無 manifest＋變更∩governed≠∅→1；enforce＋無 manifest＋無交集→0；enforce＋catalog 壞→1；`policy-exempt:persona-scope` label（經 env `PR_LABELS` 傳入，沿 workflow env 慣例）→0；shadow 全路徑零回歸。
- [ ] **Step 2: RED → Step 3: 實作**：governed paths＝enforce personas 的 `write_paths` 聯集（fnmatch pattern，用 `gate.compute_changed_paths(base, head)` 取變更集）；verdict `mode` 如實填 `"enforce"`；exit code 依判定。
- [ ] **Step 4: GREEN → Commit** `feat(persona): enforce 模式三路判定＋PR-bound manifest＋governed-paths fail-closed`

### Task 4: workflow 與 runbook

**Files:** Modify `.github/workflows/persona-scope.yml`；Create `docs/ops/persona-enforce-rollout.md`

- [ ] **Step 1:** workflow 註記更新（exit code 依 personas.yaml；移除「恆 exit 0」「MUST NOT required」改為「required 翻牌見 runbook」）；傳 `PR_LABELS` env。
- [ ] **Step 2:** runbook：試點 ≥1 週 → 誤傷記錄於 #124 → owner 設 branch protection required 的 `gh api` 步驟。
- [ ] **Step 3:** 全套件綠 → **Commit**；PR body `Closes #124`。

---

**Self-review**：spec 三 requirement（override/PR-bound/fail-closed）↔ Task 1/2/3；label 豁免、governed 聯集皆有測試；無 TBD。
