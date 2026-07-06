# G5 Hook 安裝自動化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> **實作者：gpt5.3-codex**。分支 `feature/128-g5-hook-install`，worktree。**depends_on: p2-usability-phase0**（Python hooks 走 `paulshaclaw.config.paths` facade——P2 PR-B merge 前本件 Task 3 會缺依賴，先做 Task 1/2）。
> 依據：`openspec/changes/g5-hook-install/`＋`docs/superpowers/specs/2026-07-06-g5-hook-install-design.md`。

**Goal:** install 一鍵冪等裝好全部 hooks；`--verify` 抓壞語法/缺註冊/缺 env/stale；hook 零硬編碼路徑。

**Architecture:** 複製清單集中宣告 → install 冪等覆蓋＋settings reconcile → verify 四檢（語法/註冊/env 存在/sha256 stale）→ abspath lint（shell=`${PSC_REPO_ROOT}`、Python=facade）。

**錨點**：`install.sh`（repo 根；hooks 複製與 reconcile 段以檔內為準定位）、`paulshaclaw/coordinator/launcher.py:179`（PSC_REPO_ROOT 注入既例）、`scripts/coordinator/hooks/`（hook 模板家）、deploy 三分 env split（`~/.agents/core/runtime/*.env`＋`~/.config/paulshaclaw/*.secret.env`）。

---

### Task 1: 清單集中＋冪等

**Files:** Modify `install.sh`；Test `tests/test_install_hooks.py`（新，假 $HOME subprocess 跑 install hooks 段）

- [ ] **Step 1: 失敗測試**

```python
def test_install_hooks_idempotent(tmp_home):
    r1 = run_install(tmp_home)          # 首跑：檔案就位、settings 註冊
    snap = snapshot(tmp_home)           # (路徑, sha256, settings json) 快照
    r2 = run_install(tmp_home)          # 二跑
    assert r1.returncode == r2.returncode == 0
    assert snapshot(tmp_home) == snap   # 零變更、無重複註冊
```

- [ ] **Step 2: RED → Step 3:** hooks 清單抽成單一 bash 陣列（含 P0-1 warn hook 落點；每檔 `install -m 700`）；reconcile 冪等（既有函式沿用補測試）；GREEN → **Commit**

### Task 2: --verify 四檢

**Files:** Modify `install.sh`（--verify 分支，可實作為呼叫 `scripts/verify_install.py` 便於測試）；Test `tests/test_install_verify.py`

- [ ] **Step 1: 失敗測試**：完好部署→0；四壞態 fixture 各一（py hook 壞語法／settings 缺註冊／必要 env 檔缺／repo↔部署 sha256 不符）→非零且 stderr 指名壞點；env 檢查輸出不含值。
- [ ] **Step 2: RED → Step 3:** verify 實作：`py_compile`／`bash -n`；settings JSON 掃註冊項；env/secret 存在性（沿 deploy split 清單，與 G3 per-service 宣告共用）；sha256 比對列 stale 清單。GREEN → **Commit**

### Task 3: abspath 一致性（**依賴 P2 facade merge**）

**Files:** Modify 既有 hooks 檔（shell→`${PSC_REPO_ROOT}`；Python→`from paulshaclaw.config import paths`）；verify 加 lint；Test lint fixture

- [ ] **Step 1: RED**：植入 `/home/` 字面之 fixture hook → verify 非零指名；hooks 範圍 `Path.home()` 直呼（facade 外）→ 同。
- [ ] **Step 2: 實作**：逐 hook 機械替換（**不改業務邏輯**）；lint 進 verify。GREEN。
- [ ] **Step 3:** **重部署收尾**：`install.sh --skip-venv` 同步已改 hooks → `--verify` 綠（複製坑閉環）→ **Commit**

### Task 4: 收尾

- [ ] 4.1 乾淨環境（假 $HOME）e2e：install → verify 綠
- [ ] 4.2 全套件綠；PR body `Closes #128`

---

**Self-review**：spec 三 requirement（冪等/verify/零硬編碼）↔ Task 1/2/3；stale 偵測與 env 不印值皆有測試；無 TBD。
