# P0 De-ident 止血 + 長效機制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **實作者：gpt5.3-codex**（Codex CLI worker）。跨 repo：Task 1–2 在 `~/prj_pri/paulsha-conventions`，Task 3–6 在 `~/prj_pri/paulshaclaw`；各 repo 各開 feature branch＋worktree，不得在 main 工作。
> **紅線**：任何字面禁詞不得出現在 code、commit message、PR、CI log；只用類別代稱與 `#201` 引用。測試 fixture 一律用中性假詞（`vendor-a`、`git.example.com`、`prj_ext`）。

**Goal:** 清乾淨公開 repo 的識別資訊殘留，並讓修復後的上游 R-21 成為常備 CI gate（零新 job、零流程摩擦）。

**Architecture:** 三層防禦——上游 R-21（visibility 綁定＋輸出遮蔽）為 CI 正主；字面 marker 走 secret env／本機檔通道；authoring-time warn hook 左移攔截。工作序鎖死：上游修復→本機 dry-run→清理→pin bump→hook。

**Tech Stack:** Python 3.10+（policy_check 引擎、hook 腳本）、GitHub Actions reusable workflow、bash。

**依據**：`openspec/changes/p0-deident-mechanism/`（proposal/design/specs/tasks）＋ `docs/superpowers/specs/2026-07-06-p0-deident-mechanism-design.md`＋ issue #201、上游 #45。

---

### Task 1: 上游 R-21 visibility 綁定＋嚴重度分層（repo: paulsha-conventions）

**Files:**
- Modify: `policy_check/rules/r21_secret_scan.py:93-102`（tier 逃逸分支）
- Test: `tests/`（沿 repo 既有 rule 測試慣例新增 fixture 測試）

- [ ] **Step 1: 讀現行邏輯確認錨點**

Run: `sed -n '85,135p' policy_check/rules/r21_secret_scan.py`
Expected: 看到 `if tier != "shareable": return RuleResult(... Status.PASS ...)`（#45 引文一致）。

- [ ] **Step 2: 寫失敗測試（public+work 必須掃、不得 PASS-not-applicable）**

```python
def test_public_repo_with_work_tier_is_scanned(tmp_path):
    # repo 假裝 public：ctx.visibility 由新參數/偵測注入（見 Step 4 設計）
    repo = _make_repo(tmp_path, files={"a.md": "/home/someuser/secret-path\n"})
    ctx = _ctx(repo, config={"tier": "work"}, visibility="public")
    result = R21SecretScan().run(ctx)
    assert result.status is Status.FAIL          # 結構樣式（/home/<user>/）→ FAIL
    assert "someuser" not in result.message       # 輸出遮蔽：不得含命中原文

def test_private_repo_with_work_tier_warns_not_blocks(tmp_path):
    repo = _make_repo(tmp_path, files={"a.md": "/home/someuser/secret-path\n"})
    ctx = _ctx(repo, config={"tier": "work"}, visibility="private")
    result = R21SecretScan().run(ctx)
    assert result.status is Status.WARN
```

- [ ] **Step 3: 跑測試看它 fail**（`python3 -m pytest tests/ -k r21 -v`；Expected: FAIL——現行直接 PASS）
- [ ] **Step 4: 實作**——tier 分支改為：`visibility == "public"` 時一律續掃（tier 只豁免 private→WARN 降級）；visibility 來源 = ctx 新欄位（reusable workflow 傳入 `${{ github.event.repository.visibility }}`，本機 CLI 加 `--visibility` 參數、預設 `private` 保守）；結構/憑證命中 public → FAIL、字面 marker public+非shareable → WARN；`result.message` 只含規則代號＋檔案路徑＋計數。
- [ ] **Step 5: 跑測試 GREEN；跑全套 rule 測試零回歸**
- [ ] **Step 6: Commit**（`fix(R-21): visibility 綁定與嚴重度分層——public repo 不得以 tier 逃逸`）

### Task 2: 上游 marker env 擴充點＋release（repo: paulsha-conventions）

**Files:**
- Modify: `policy_check/rules/_secret_scan_config.py`（`resolve_markers`）
- Modify: `.github/workflows/reusable-policy-check.yml`（傳遞 visibility＋secret env）

- [ ] **Step 1: 失敗測試**

```python
def test_markers_extend_from_env(monkeypatch):
    monkeypatch.setenv("PSC_SECRET_SCAN_EXTRA_MARKERS", "vendor-a,git.example.com")
    markers = resolve_markers({})
    assert "vendor-a" in markers and "git.example.com" in markers

def test_env_absent_is_noop(monkeypatch):
    monkeypatch.delenv("PSC_SECRET_SCAN_EXTRA_MARKERS", raising=False)
    assert resolve_markers({}) == resolve_markers({})  # 穩定、不報錯
```

- [ ] **Step 2: RED → 實作**——`resolve_markers` 尾端疊加 `os.environ.get("PSC_SECRET_SCAN_EXTRA_MARKERS","")` 逗號分詞（strip、lower、去空）；extend-only，`public_names` 減法語意不變。
- [ ] **Step 3: reusable workflow**：job env 接 `PSC_SECRET_SCAN_EXTRA_MARKERS: ${{ secrets.PSC_SECRET_SCAN_EXTRA_MARKERS }}`；步驟輸出沿用遮蔽訊息。GREEN 後 commit。
- [ ] **Step 4: 依 repo 升版 SOP release**（版本號＋RELEASES.md 記 **release commit SHA**——注意上游 #42 的坑：勿記 PR merge commit）；PR body `Closes #45`。

### Task 3: 本機 dry-run 盤點（repo: paulshaclaw，先私下、不進 CI）

- [ ] **Step 1**: 以 Task 2 release 的引擎版本本機跑 `python3 -m policy_check --repo . --visibility public`（本機 env 設字面表；輸出遮蔽模式）。
- [ ] **Step 2**: 核對命中檔清單 == #201 逐檔清單（12 檔）。多出 → 先補列 #201 再續行；少於 → 檢查 env 字面表是否齊。**此步輸出不得貼進任何公開面**（issue/PR 只寫「N 檔一致」）。

### Task 4: Stage A 清理（repo: paulshaclaw）

**Files:**
- Modify: `paulshaclaw/memory/instruction_corpus.py:86`、`scripts/start.sh:224`
- Modify: `paulshaclaw/memory/tests/test_rekey.py:374-392`、`paulshaclaw/memory/tests/test_start_sh_dream_flags.py:39`
- Modify: #201 清單所列 docs/ 3 檔＋openspec archive 5 檔（字面→佔位，其餘逐字不動）

- [ ] **Step 1: 失敗測試（env 供給語意）**

```python
def test_extra_corpus_root_from_env(monkeypatch, tmp_path):
    extra = tmp_path / "extra"; extra.mkdir()
    monkeypatch.setenv("PSC_EXTRA_CORPUS_ROOT", str(extra))
    roots = default_instruction_roots(home=tmp_path)   # 現有函式名以檔內為準，錨點=instruction_corpus.py:86
    assert extra in roots

def test_extra_corpus_root_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("PSC_EXTRA_CORPUS_ROOT", raising=False)
    roots = default_instruction_roots(home=tmp_path)
    assert all("prj_" not in p.name or p.name == "prj_pri" for p in roots)  # 不再硬編第 2 root
```

- [ ] **Step 2: RED → 實作**：`instruction_corpus.py:86` 的 `home / "<第2root字面>"` 改為讀 `PSC_EXTRA_CORPUS_ROOT`（未設→不加入）；`start.sh:224` 對應改 `${PSC_EXTRA_CORPUS_ROOT:+--instruction-root "$PSC_EXTRA_CORPUS_ROOT"}`；`test_start_sh_dream_flags.py:39` 斷言改 env 形式。
- [ ] **Step 3: fixture 改中性名**：`test_rekey.py` 四處字面 vendor 詞→`vendor-a`（斷言同步改；測試語意=rekey 遷移不變）。
- [ ] **Step 4: 文件替換**：#201 表列 docs 3 檔＋openspec archive 5 檔——字面值→`vendor-a`／`git.example.com`／`prj_ext`；diff 只允許替換行。
- [ ] **Step 5: GREEN**（`python3 -m pytest paulshaclaw/memory/tests/ -q` 全綠）→ Commit（訊息用類別代稱，例：`fix(deident): tracked 檔識別資訊改中性佔位＋corpus root env 化（#201 Stage A）`）。

### Task 5: 安全驗證器＋歸零證明（repo: paulshaclaw）

**Files:**
- Create: `scripts/deident_verify.py`
- Test: `tests/test_deident_verify.py`

- [ ] **Step 1: 失敗測試**

```python
def test_verifier_never_prints_matched_text(tmp_path, capsys):
    f = tmp_path / "x.md"; f.write_text("token vendor-a here\n")
    rc = run_verify(root=tmp_path, markers=["vendor-a"])
    out = capsys.readouterr().out
    assert rc == 1 and "vendor-a here" not in out and "x.md" in out and "M001" in out

def test_verifier_structural_only_when_no_marker_file(tmp_path, capsys):
    f = tmp_path / "y.md"; f.write_text("/home/someuser/private\n")
    rc = run_verify(root=tmp_path, markers=None)   # 字面表缺席→降級
    assert rc == 1 and "degraded" in capsys.readouterr().out
```

- [ ] **Step 2: RED → 實作**：markers 來源＝`--markers-file`（預設 `~/.config/paulshaclaw/deident-markers.txt`）或 `PSC_SECRET_SCAN_EXTRA_MARKERS`；結構 regex＝`/home/[A-Za-z0-9_]+/`、`-----BEGIN [A-Z ]*PRIVATE KEY-----`、內網樣式 FQDN（非 example.com/github.com allowlist）；輸出僅 `M<序號> <path> ×<count>`；掃 `git ls-files` 範圍、排除 `ref/`。
- [ ] **Step 3: GREEN → 對全 repo 跑歸零**：`python3 scripts/deident_verify.py` Expected: `0 hits`（Task 4 之後）。輸出（遮蔽版）貼 #201 當證據。Commit。

### Task 6: pin bump＋authoring hook（repo: paulshaclaw）

**Files:**
- Modify: `.github/workflows/policy-check.yml`（uses＋policy_engine_ref 同 SHA→Task 2 release）
- Create: `paulshaclaw/memory/hooks/deident_warn_hook.py`＋install.sh 複製清單＋settings 接線（PostToolUse matcher Write|Edit）
- Test: `tests/test_deident_warn_hook.py`

- [ ] **Step 1**: pin bump（本機先以新引擎跑 policy_check 零 fail 才推——CLAUDE.md 升版 SOP）；repo settings 設 secret `PSC_SECRET_SCAN_EXTRA_MARKERS`（值只進 GitHub secret，不落檔）。
- [ ] **Step 2: hook TDD**：測試——含結構樣式的 tool_input → stdout 出 warn JSON（`decision: undefined`、警告訊息含遮蔽代號）且 exit 0；字面表缺席→僅結構、不報錯。實作沿 `_shortlist_common.py` 讀寫慣例；**warn-only 永不 block**。
- [ ] **Step 3**: install.sh 複製清單＋Claude settings reconcile 加 PostToolUse(Write|Edit)；跑 `install.sh --skip-venv` 部署（複製坑：改 repo 檔不會自動生效）。GREEN → Commit。
- [ ] **Step 4: 收尾驗證**：PR 觸發 Policy Check——R-21 實掃且綠；#201 Stage A checklist 勾銷。**不 merge**（交 owner）。

---

**Self-review**：spec 4 requirement ↔ Task 4/5（歸零＋驗證器）、Task 1/2/6（gate）、Task 6（hook）覆蓋；無 TBD；env 名 `PSC_EXTRA_CORPUS_ROOT`／`PSC_SECRET_SCAN_EXTRA_MARKERS` 全篇一致。
