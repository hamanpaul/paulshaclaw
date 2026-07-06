# G4 complete_tick Idempotency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> **實作者：gpt5.3-codex**。分支 `feature/132-g4-complete-tick-idempotency`，worktree。測試：`python3 -m pytest tests/test_coordinator_manager.py -q`。
> 依據：`openspec/changes/g4-complete-tick-idempotency/`＋`docs/superpowers/specs/2026-07-06-g4-complete-tick-idempotency-design.md`。

**Goal:** requeue 後新 run 結果能落地；同 run 真冪等；消費端（`default_is_satisfied`）零改。

**Architecture:** manifest 加 `job_id`；冪等由「檔存在即 skip」改三態（同 job skip／異 job overwrite／壞檔 overwrite）。

**錨點**：`paulshaclaw/coordinator/manager.py:55`（complete_tick）＋迴圈內 `manifest_path.is_file(): continue`（病灶行）；`handoff.write_manifest` 呼叫點；`autonomy.default_is_satisfied`（消費端，不動）。

---

### Task 1: 三態冪等（TDD）

**Files:** Modify `paulshaclaw/coordinator/manager.py`；Test `tests/test_coordinator_manager.py`

- [ ] **Step 1: 失敗測試**（沿檔內既有 complete_tick 測試 fixture 慣例）

```python
def test_same_job_rescan_is_noop(tmp_path, ...):
    # 首輪寫入後記 mtime；同 job 再跑 complete_tick → manifest 內容與 mtime 不變

def test_requeue_overwrites_with_new_run(tmp_path, ...):
    # job A(failed) 寫 manifest → registry 加同 slice job B(done) → complete_tick
    m = json.loads((hdir / "s1.json").read_text())
    assert m["job_id"] == "job-B" and m["gate_status"] == "passed"
    assert autonomy.default_is_satisfied("s1", handoff_dir=str(hdir)) is True

def test_legacy_manifest_upgraded(tmp_path, ...):
    # 預置無 job_id 的舊格式 manifest → 新 terminal job → overwrite 為含 job_id 新格式

def test_corrupt_manifest_overwritten(tmp_path, ...):
    # 預置壞 JSON manifest → 不 raise、overwrite
```

- [ ] **Step 2: RED**（現行 `is_file() → continue` 使 2/3/4 全 FAIL）
- [ ] **Step 3: 實作**（病灶行替換）

```python
            manifest_path = hdir / f"{slice_id}.json"
            existing = contract_read(manifest_path)   # 用既有 read helper；壞檔回 None
            if isinstance(existing, dict) and existing.get("job_id") == job_id:
                continue  # 真冪等：同 run 已寫過
            # 異 job_id / 舊格式 / 壞檔 → 新 run 勝，落到下方重算重寫
```

  並在 `handoff.write_manifest(...)` payload 加 `"job_id": job_id`。
- [ ] **Step 4: GREEN → Commit** `fix(coordinator): complete_tick manifest 冪等改 job_id 三態（requeue 可重入，#132）`

### Task 2: 異常雙 terminal 釘住＋觀測

**Files:** 同上

- [ ] **Step 1: RED**：同 slice 兩 job 同輪 terminal → 後掃者勝＋log warning `same-slice concurrent terminals`；released 觀測 failed→passed 正確反映。
- [ ] **Step 2: 實作**（迴圈內偵測同輪已寫過同 slice → warning）＋GREEN。
- [ ] **Step 3:** 既有 complete_tick 測試零回歸（released/_is_safe_slice_id）→ **Commit**

### Task 3: 收尾

- [ ] 3.1 全套件綠（`python3 -m pytest tests/ -q`）
- [ ] 3.2 PR body `Closes #132`；design 註記「不變量防線在 G1 already-active guard」交叉引用

---

**Self-review**：spec 四 scenario ↔ Task 1 四測試＋Task 2；消費端零改由 requeue 測試間接驗證；無 TBD。
